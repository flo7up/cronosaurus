"""Pydantic models for the Agent entity — the first-class citizen of Cronosaurus."""

from pydantic import BaseModel, Field
from typing import Optional


# ── Request models ───────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = "New Agent"
    model: str = "gpt-4.1-mini"
    tools: list[str] = Field(default_factory=lambda: ["crypto", "stock", "email_send", "email_read", "triggers", "notifications", "tool_management"])
    email_account_id: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    email_account_id: Optional[str] = None


class AgentTriggerCreate(BaseModel):
    type: str = "regular"  # "regular" for interval-based, "gmail_push" for email push
    interval_minutes: int = Field(1, ge=1)  # only used for type=regular
    prompt: str = Field(..., min_length=1)
    description: str = ""
    filter_from: str = ""  # gmail_push: only trigger for emails from this address
    filter_subject: str = ""  # gmail_push: only trigger if subject contains this
    filter_body: str = ""  # gmail_push: only trigger if body contains this keyword
    filter_header: str = ""  # gmail_push: only trigger if any header contains this
    max_age_minutes: int = 0  # gmail_push: ignore emails older than N minutes (0 = no limit)
    filter_after_date: str = ""  # gmail_push: ignore emails before this date (ISO 8601, e.g. "2026-03-03")


class AgentTriggerUpdate(BaseModel):
    interval_minutes: Optional[int] = Field(None, ge=1)
    prompt: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    filter_from: Optional[str] = None
    filter_subject: Optional[str] = None
    filter_body: Optional[str] = None
    filter_header: Optional[str] = None
    max_age_minutes: Optional[int] = None
    filter_after_date: Optional[str] = None


class ImageAttachment(BaseModel):
    data: str  # base64-encoded image data (no data URI prefix)
    media_type: str = "image/png"  # e.g. "image/png", "image/jpeg"


class SendAgentMessageRequest(BaseModel):
    content: str
    images: list[ImageAttachment] = Field(default_factory=list)


# ── Response models ──────────────────────────────────────────────

class AgentTriggerResponse(BaseModel):
    type: str = "regular"
    interval_minutes: int = 0
    prompt: str
    description: str = ""
    active: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    created_at: str = ""
    # gmail_push fields
    filter_from: str = ""
    filter_subject: str = ""
    filter_body: str = ""
    filter_header: str = ""
    max_age_minutes: int = 0
    filter_after_date: str = ""
    last_seen_uid: int = 0


class AgentResponse(BaseModel):
    id: str
    user_id: str = "1"
    name: str
    model: str
    tools: list[str]
    email_account_id: Optional[str] = None
    thread_id: str
    foundry_agent_id: str = ""
    trigger: Optional[AgentTriggerResponse] = None
    created_at: str
    updated_at: str


class ToolStepResponse(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)
    result: Optional[dict] = None
    status: str = "completed"  # "running" | "completed" | "error"


class MessageResponse(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None
    tool_steps: Optional[list[ToolStepResponse]] = None
    images: Optional[list[dict]] = None  # [{data: str, media_type: str}]
