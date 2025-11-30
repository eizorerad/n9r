"""Chat schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.chat import MessageRole
from app.schemas.common import BaseSchema


class ChatThreadCreate(BaseModel):
    """Chat thread creation request."""

    context_file: str | None = None
    context_issue_id: UUID | None = None
    initial_message: str


class ChatMessageResponse(BaseSchema):
    """Chat message response."""

    id: UUID
    role: MessageRole
    content: str
    created_at: datetime


class ChatThreadResponse(BaseSchema):
    """Chat thread response."""

    id: UUID
    context_file: str | None = None
    context_issue_id: UUID | None = None
    messages_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime


class ChatThreadDetail(BaseSchema):
    """Chat thread detail with messages."""

    id: UUID
    context_file: str | None = None
    context_issue_id: UUID | None = None
    messages: list[ChatMessageResponse] = []
    created_at: datetime


class ChatMessageCreate(BaseModel):
    """Chat message creation request."""

    content: str


class ChatMessageDone(BaseModel):
    """Chat message completion event."""

    message_id: UUID
    tokens_used: int
