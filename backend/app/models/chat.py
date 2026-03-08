from pydantic import BaseModel
from typing import Optional


# Available chat models (not embedding models)
AVAILABLE_MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "model-router",
    "gpt-5-mini",
    "gpt-5-chat",
    "gpt-5-nano",
]

DEFAULT_MODEL = "gpt-4.1-mini"


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    model: str


class MessageResponse(BaseModel):
    role: str
    content: str
