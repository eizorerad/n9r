"""Chat models."""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.issue import Issue
    from app.models.repository import Repository
    from app.models.user import User


class MessageRole(str, enum.Enum):
    """Chat message role."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatThread(BaseModel):
    """Chat thread model for conversations with AI."""

    __tablename__ = "chat_threads"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # Default model for this thread (provider-prefixed, e.g. "gemini/gemini-3-pro-preview")
    model: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    context_file: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    context_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="chat_threads",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="chat_threads",
    )
    context_issue: Mapped["Issue | None"] = relationship(
        "Issue",
        foreign_keys=[context_issue_id],
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatThread {self.id}>"


class ChatMessage(BaseModel):
    """Chat message model."""

    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Store as plain string to avoid Postgres enum drift across environments.
    # Valid values are enforced at the application layer via MessageRole.
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    tokens_used: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    # Git reference (branch name or commit SHA) for this message
    context_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    thread: Mapped["ChatThread"] = relationship(
        "ChatThread",
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"<ChatMessage {self.role} in {self.thread_id}>"
