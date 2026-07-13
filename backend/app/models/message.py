from enum import Enum
import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.user import Base


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    """A single turn in a conversation. Either a user question or an assistant reply."""

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)

    # For assistant messages only: which document chunks were retrieved from Qdrant
    # to ground this answer, e.g. [{"source": "policy.pdf"}, ...]. Kept as plain JSON
    # instead of a separate chunks table -- it's just provenance, not queried on its own.
    sources = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    conversation = relationship("Conversation", back_populates="messages")
