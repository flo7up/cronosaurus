"""
Notification API router.

Prefix: /api/notifications
"""

import logging
from fastapi import APIRouter, HTTPException

from app.services.notification_service import notification_service
from app.models.notification import NotificationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(limit: int = 50, unread_only: bool = False):
    """List recent notifications, newest first."""
    items = notification_service.list_notifications(limit=limit, unread_only=unread_only)
    return [
        NotificationResponse(
            id=n["id"],
            user_id=n["user_id"],
            title=n["title"],
            body=n["body"],
            content=n.get("content", ""),
            level=n.get("level", "info"),
            agent_id=n.get("agent_id"),
            agent_name=n.get("agent_name"),
            read=n.get("read", False),
            created_at=n["created_at"],
            images=n.get("images"),
        )
        for n in items
    ]


@router.get("/unread-count")
async def unread_count():
    """Get the number of unread notifications."""
    count = notification_service.get_unread_count()
    return {"count": count}


@router.put("/{notification_id}/read")
async def mark_read(notification_id: str):
    """Mark a notification as read."""
    result = notification_service.mark_read(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.put("/read-all")
async def mark_all_read():
    """Mark all notifications as read."""
    count = notification_service.mark_all_read()
    return {"ok": True, "count": count}


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """Delete a notification."""
    ok = notification_service.delete_notification(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.delete("")
async def clear_all():
    """Delete all notifications."""
    count = notification_service.clear_all()
    return {"ok": True, "count": count}
