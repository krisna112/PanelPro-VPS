"""Notification channel endpoints (webhook / Telegram / SMTP)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from panelpro.api.deps import api_ok, require_role
from panelpro.constants import NOTIFY_EVENTS
from panelpro.core import notify
from panelpro.core.database import get_db
from panelpro.core.errors import PanelError
from panelpro.models.tables import NotifyChannel

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class ChannelBody(BaseModel):
    name: str
    type: str
    config: dict = {}
    events: list[str] = []
    enabled: bool = True


@router.get("/events")
def events(ctx=Depends(require_role("admin"))):
    return api_ok(NOTIFY_EVENTS)


@router.get("/channels")
def channels(db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    rows = db.query(NotifyChannel).order_by(NotifyChannel.created_at.desc()).all()
    return api_ok(
        [
            {
                "id": r.id,
                "name": r.name,
                "type": r.type,
                "config": r.config,
                "events": r.events,
                "enabled": r.enabled,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@router.post("/channels")
def create_channel(body: ChannelBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    if body.type not in ("webhook", "telegram", "smtp"):
        raise PanelError(f"Unknown channel type: {body.type}", 400)
    row = NotifyChannel(name=body.name[:100], type=body.type, config=body.config,
                        events=body.events, enabled=body.enabled)
    db.add(row)
    db.commit()
    return api_ok({"id": row.id, "name": row.name})


@router.post("/channels/{channel_id}/update")
def update_channel(channel_id: int, body: ChannelBody, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not row:
        raise PanelError("Channel not found.", 404)
    row.name = body.name[:100]
    row.type = body.type
    row.config = body.config
    row.events = body.events
    row.enabled = body.enabled
    db.commit()
    return api_ok({"updated": row.id})


@router.post("/channels/{channel_id}/delete")
def delete_channel(channel_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not row:
        raise PanelError("Channel not found.", 404)
    db.delete(row)
    db.commit()
    return api_ok({"deleted": row.name})


@router.post("/channels/{channel_id}/test")
def test_channel(channel_id: int, db: Session = Depends(get_db), ctx=Depends(require_role("admin"))):
    row = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not row:
        raise PanelError("Channel not found.", 404)
    ok, message = notify.test_channel(row)
    if not ok:
        raise PanelError(f"Test failed: {message}", 400)
    return api_ok({"tested": True})
