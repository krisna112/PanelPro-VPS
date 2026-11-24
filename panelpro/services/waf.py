"""Basic nginx WAF per site: CC rate-limit zone + IP/UA blocklists.

Two files are produced per protected site:

* ``<nginx conf.d>/waf_zone_<domain>.conf`` — http-context ``limit_req_zone``
  definition (written next to the vhost in conf.d, which nginx loads at
  http level).
* ``<CFG.data_dir>/waf/site_<domain>.conf`` — server-context include:
  deny rules, user-agent block, ``limit_req`` reference.

The vhost template includes the server-context file when a WAF profile
exists.  Every generated value is strictly validated (IP whitelist,
shlex-quoted UA regexes) before it touches a config file.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from panelpro.config import CFG
from panelpro.core.errors import PanelError
from panelpro.models.tables import WafProfile

IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
# nginx regex charset for user-agent patterns — quotes/semicolons/backslash
# and braces are excluded so a pattern can never break out of its quoted
# argument or reference nginx variables.
UA_RE = re.compile(r"^[A-Za-z0-9 ._*?:^()\[\]|+/#-]{1,120}$")


def _validate_ip(ip: str) -> str:
    ip = (ip or "").strip()
    if not IP_RE.match(ip) or any(int(o) > 255 for o in ip.split(".")):
        raise PanelError(f"Invalid IP address: {ip}", 400)
    return ip


def _validate_ua(pattern: str) -> str:
    pattern = (pattern or "").strip()
    if not pattern or not UA_RE.match(pattern):
        raise PanelError(
            f"Invalid user-agent pattern: {pattern[:60]!r} "
            "(allowed: letters, digits, spaces and ._*?:^$()[]{}|+/#-)",
            400,
        )
    return pattern


def validate_profile_data(enabled: bool, cc_rpm: int, blocked_ips: list, blocked_uas: list) -> dict:
    cc_rpm = max(10, min(int(cc_rpm or 300), 60000))
    ips = [_validate_ip(ip) for ip in list(blocked_ips or [])[:500]]
    uas = [_validate_ua(ua) for ua in list(blocked_uas or [])[:200]]
    return {"enabled": bool(enabled), "cc_rpm": cc_rpm, "blocked_ips": ips, "blocked_uas": uas}


def zone_conf_path(domain: str) -> Path:
    """http-context zone file (must live in nginx conf.d)."""
    from panelpro.services import webservers

    adapter = webservers.detect_webserver("nginx")
    return Path(adapter.conf_dir) / f"waf_zone_{domain}.conf"


def site_conf_path(domain: str) -> Path:
    """server-context include file stored under the panel data dir."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", domain)
    return CFG.data_dir / "waf" / f"site_{safe}.conf"


def render_zone_conf(profile: WafProfile, domain: str) -> str:
    rate = f"{max(int(profile.cc_rpm or 300), 10)}r/m"
    zone = re.sub(r"[^A-Za-z0-9._-]", "_", domain)
    return (
        f"# PanelPro WAF zone for {domain} — generated, do not edit\n"
        f"limit_req_zone $binary_remote_addr zone=ppwaf_{zone}:10m rate={rate};\n"
    )


def render_site_conf(profile: WafProfile, domain: str) -> str:
    zone = re.sub(r"[^A-Za-z0-9._-]", "_", domain)
    lines = [f"# PanelPro WAF rules for {domain} — generated, do not edit"]
    for ip in profile.blocked_ips or []:
        lines.append(f"deny {ip};")
    for ua in profile.blocked_uas or []:
        quoted = shlex.quote(ua)
        lines.append(f'if ($http_user_agent ~* {quoted}) {{ return 403; }}')
    lines.append(f"limit_req zone=ppwaf_{zone} burst=60 nodelay;")
    return "\n".join(lines) + "\n"


def write_profile(profile: WafProfile | None, domain: str, zone_path: Path, site_path: Path) -> dict:
    """Write the files referenced by the site's nginx rules."""
    from panelpro.services import webservers

    enabled = profile is not None and profile.enabled
    if enabled:
        site_path.parent.mkdir(parents=True, exist_ok=True)
        webservers.write_config(zone_path, render_zone_conf(profile, domain).encode("utf-8"))
        webservers.write_config(site_path, render_site_conf(profile, domain).encode("utf-8"))
    else:
        zone_path.unlink(missing_ok=True)
        site_path.unlink(missing_ok=True)
    return {"zone_conf": str(zone_path), "site_conf": str(site_path), "enabled": enabled}


def profile_payload(profile: WafProfile) -> dict:
    return {
        "id": profile.id,
        "site_id": profile.site_id,
        "enabled": profile.enabled,
        "cc_rpm": profile.cc_rpm,
        "blocked_ips": profile.blocked_ips,
        "blocked_uas": profile.blocked_uas,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
