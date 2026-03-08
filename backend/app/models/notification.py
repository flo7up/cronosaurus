"""
Pydantic models for the cross-agent notification / alert system.
"""

from pydantic import BaseModel, Field
from typing import Optional


class NotificationCreate(BaseModel):
    """Payload when creating a notification (from an agent tool call)."""
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=2000)
    level: str = Field(
        default="info",
        pattern=r"^(info|success|warning|error)$",
    )
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None


class NotificationResponse(BaseModel):
    """Notification returned from the API."""
    id: str
    user_id: str
    title: str
    body: str
    level: str  # info | success | warning | error
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    read: bool = False
    created_at: str  # ISO-8601


class NotificationPreferences(BaseModel):
    """User's notification delivery preferences."""
    delivery: str = Field(
        default="all",
        pattern=r"^(all|in_app|none)$",
        description="all = in-app + email, in_app = bell only, none = muted",
    )
