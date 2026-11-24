"""Per-site traffic statistics: parse nginx/apache combined access logs.

New lines are read incrementally (byte offsets stored in the settings
table) and aggregated into ``traffic_daily`` rows (pv/uv/bytes/spiders
plus top IPs and URLs per day).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from panelpro.models.tables import Setting, Site, TrafficDaily

# nginx/apache "combined" format:
# 1.2.3.4 - user [10/Oct/2026:13:55:36 +0700] "GET /x HTTP/1.1" 200 2326
#          "https://ref" "Mozilla/5.0 ..."
LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<url>\S+) (?P<proto>[^"]*)" '
    r'(?P<status>\d{3}) (?P<bytes>\S+)(?: "(?P<ref>[^"]*)" "(?P<ua>[^"]*)")?'
)

SPIDER_RE = re.compile(r"bot|crawler|spider|slurp|curl|wget|monitoring", re.IGNORECASE)

SPIDER_SAMPLE_LIMIT = 50  # max entries kept per top-list


def parse_line(line: str) -> dict | None:
    """Parse one combined-format access log line; None when unparseable."""
    match = LOG_RE.match(line.strip())
    if not match:
        return None
    raw_bytes = match.group("bytes")
    return {
        "ip": match.group("ip"),
        "url": match.group("url").split("?", 1)[0],
        "status": int(match.group("status")),
        "bytes": int(raw_bytes) if raw_bytes.isdigit() else 0,
        "ua": match.group("ua") or "",
        "time": match.group("time"),
    }


def _day_of(line_time: str) -> str:
    """10/Oct/2026:13:55:36 +0700 -> 2026-10-10 (naive local date)."""
    try:
        return datetime.strptime(line_time.split(" ")[0], "%d/%b/%Y:%H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def aggregate(lines: list[str]) -> dict[str, dict]:
    """Aggregate parsed log lines per day (pure helper, easy to test)."""
    days: dict[str, dict] = {}
    for line in lines:
        item = parse_line(line)
        if item is None:
            continue
        day = _day_of(item["time"]) or datetime.utcnow().strftime("%Y-%m-%d")
        bucket = days.setdefault(
            day,
            {
                "pv": 0, "bytes": 0, "errors": 0, "spiders": 0,
                "ips": Counter(), "urls": Counter(),
            },
        )
        bucket["pv"] += 1
        bucket["bytes"] += item["bytes"]
        if item["status"] >= 400:
            bucket["errors"] += 1
        if SPIDER_RE.search(item["ua"]):
            bucket["spiders"] += 1
        bucket["ips"][item["ip"]] += 1
        bucket["urls"][item["url"][:200]] += 1
    for bucket in days.values():
        bucket["uv"] = len(bucket["ips"])
        bucket["top_ips"] = dict(bucket["ips"].most_common(SPIDER_SAMPLE_LIMIT))
        bucket["top_urls"] = dict(bucket["urls"].most_common(SPIDER_SAMPLE_LIMIT))
        del bucket["ips"], bucket["urls"]
    return days


def site_log_file(site: Site) -> Path | None:
    """Best-effort access log path for a site (nginx/apache conventions)."""
    domain = site.name
    candidates = [
        Path(f"/www/wwwlogs/{domain}.log"),
        Path(f"/var/log/nginx/{domain}.access.log"),
        Path(f"/var/log/apache2/{domain}.access.log"),
        Path(f"/var/log/httpd/{domain}.access.log"),
        Path(f"/var/log/httpd/{domain}-access_log"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _collect_site(db, site: Site, today_only: bool = True) -> int:
    """Read new log content for one site and merge into daily rows."""
    log_path = site_log_file(site)
    if log_path is None:
        return 0
    offset_key = f"traffic_off:{site.id}"
    cursor = db.get(Setting, offset_key)
    offset = int(cursor.value or 0) if cursor else 0
    size = log_path.stat().st_size
    if size < offset:  # log rotated
        offset = 0
    if size == offset:
        return 0
    stored_lines = 0
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        lines = fh.readlines()
        new_offset = fh.tell()
    for day, bucket in aggregate(lines).items():
        if today_only and day < (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d"):
            continue  # skip absurdly old rotated content
        row = db.query(TrafficDaily).filter(
            TrafficDaily.site_id == site.id, TrafficDaily.date == day
        ).first()
        if row is None:
            row = TrafficDaily(site_id=site.id, date=day, pv=0, bytes_total=0, errors=0, spiders=0)
            db.add(row)
        row.pv += bucket["pv"]
        row.bytes_total += bucket["bytes"]
        row.errors += bucket["errors"]
        row.spiders += bucket["spiders"]
        merged: Counter = Counter(row.top_ips or {})
        merged.update(Counter(bucket["top_ips"]))
        row.top_ips = dict(merged.most_common(SPIDER_SAMPLE_LIMIT))
        merged_urls: Counter = Counter(row.top_urls or {})
        merged_urls.update(Counter(bucket["top_urls"]))
        row.top_urls = dict(merged_urls.most_common(SPIDER_SAMPLE_LIMIT))
        row.uv = len(merged)
        stored_lines += bucket["pv"]
    if cursor:
        cursor.value = new_offset
    else:
        db.add(Setting(key=offset_key, value=new_offset))
    db.commit()
    return stored_lines


def traffic_collect_job() -> None:
    """Scheduler entry: collect new log lines for every site."""
    from panelpro.core.database import SessionLocal
    from panelpro.services.webservers import CONFIG_LOCK

    db = SessionLocal()
    try:
        for (site_id,) in db.query(Site.id).all():
            with CONFIG_LOCK:
                try:
                    site = db.get(Site, site_id)
                    if site:
                        _collect_site(db, site)
                except Exception:
                    db.rollback()
    finally:
        db.close()


def series(db, site_id: int | None, days: int) -> dict:
    days = max(1, min(days, 90))
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = db.query(TrafficDaily).filter(TrafficDaily.date >= since)
    if site_id:
        query = query.filter(TrafficDaily.site_id == site_id)
    rows = query.order_by(TrafficDaily.date.asc()).all()
    totals = {
        "pv": sum(r.pv for r in rows),
        "uv": max((r.uv for r in rows), default=0),
        "bytes": sum(r.bytes_total for r in rows),
        "spiders": sum(r.spiders for r in rows),
        "errors": sum(r.errors for r in rows),
    }
    ip_counter: Counter = Counter()
    url_counter: Counter = Counter()
    for row in rows:
        ip_counter.update(Counter(row.top_ips or {}))
        url_counter.update(Counter(row.top_urls or {}))
    return {
        "days": days,
        "series": [
            {
                "date": r.date,
                "site_id": r.site_id,
                "pv": r.pv,
                "uv": r.uv,
                "bytes": r.bytes_total,
                "spiders": r.spiders,
                "errors": r.errors,
            }
            for r in rows
        ],
        "totals": totals,
        "top_ips": dict(ip_counter.most_common(20)),
        "top_urls": dict(url_counter.most_common(20)),
    }


def reset_site(db, site_id: int) -> None:
    """Drop collected stats for a site (used when a site is deleted)."""
    db.query(TrafficDaily).filter(TrafficDaily.site_id == site_id).delete()
    db.query(Setting).filter_by(key=f"traffic_off:{site_id}").delete()
