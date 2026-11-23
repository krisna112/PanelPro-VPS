"""Notification dispatch: webhook, Telegram and SMTP channels plus
resource-threshold alerts.  Failures are swallowed (logged) by design —
a broken notification channel must not break panel operations.
"""

from __future__ import annotations

import smtplib
import threading
import time
from email.message import EmailMessage

import httpx

from panelpro.core import settings_store
from panelpro.core.database import SessionLocal
from panelpro.models.tables import NotifyChannel

_alert_state: dict[str, float] = {}
_alert_lock = threading.Lock()
ALERT_COOLDOWN = 30 * 60  # seconds between repeated alerts of one kind


def send_to_channel(channel: NotifyChannel, title: str, message: str) -> tuple[bool, str]:
    ctype = channel.type
    cfg = channel.config or {}
    try:
        if ctype == "webhook":
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    cfg.get("url", ""),
                    json={"event": title, "message": message, "app": "PanelPro"},
                    headers={"Content-Type": "application/json"},
                )
            return resp.status_code < 400, f"HTTP {resp.status_code}"

        if ctype == "telegram":
            token = cfg.get("bot_token", "")
            chat_id = cfg.get("chat_id", "")
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"[PanelPro] {title}\n{message}"},
                )
            return resp.status_code < 400, f"HTTP {resp.status_code}"

        if ctype == "smtp":
            msg = EmailMessage()
            msg["Subject"] = f"[PanelPro] {title}"
            msg["From"] = cfg.get("from", "")
            msg["To"] = cfg.get("to", "")
            msg.set_content(message)
            host = cfg.get("host", "")
            port = int(cfg.get("port", 587))
            if cfg.get("ssl"):
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                if cfg.get("starttls", True):
                    server.starttls()
            if cfg.get("username"):
                server.login(cfg["username"], cfg.get("password", ""))
            server.send_message(msg)
            server.quit()
            return True, "sent"

        return False, f"unknown channel type: {ctype}"
    except Exception as exc:
        return False, str(exc)


def notify_event(event: str, title: str, message: str) -> int:
    """Send to every enabled channel subscribed to this event."""
    sent = 0
    db = SessionLocal()
    try:
        channels = db.query(NotifyChannel).filter(NotifyChannel.enabled.is_(True)).all()
        for ch in channels:
            subscribed = ch.events or []
            if "*" in subscribed or event in subscribed:
                ok, _err = send_to_channel(ch, title, message)
                if ok:
                    sent += 1
    finally:
        db.close()
    return sent


def test_channel(channel: NotifyChannel) -> tuple[bool, str]:
    return send_to_channel(channel, "Test message", "If you can read this, the channel works.")


def check_thresholds() -> None:
    """Compare the latest monitor snapshot against configured thresholds."""
    from panelpro.core import monitor as monitor_mod

    snap = monitor_mod.MONITOR.snapshot()
    now = time.time()
    disk_limit = int(settings_store.get_setting("threshold_disk", 90))
    cpu_limit = int(settings_store.get_setting("threshold_cpu", 85))

    checks = []
    if snap["disk_percent"] >= disk_limit:
        checks.append(
            ("disk_high", "Disk usage is high",
             f"Disk is at {snap['disk_percent']}% (limit {disk_limit}%).")
        )
    if snap["cpu"] >= cpu_limit:
        checks.append(
            ("cpu_high", "CPU usage is high",
             f"CPU is at {snap['cpu']}% (limit {cpu_limit}%).")
        )

    with _alert_lock:
        for event, title, message in checks:
            if now - _alert_state.get(event, 0) < ALERT_COOLDOWN:
                continue
            _alert_state[event] = now
            notify_event(event, title, message)
