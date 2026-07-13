import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    # Omit to start a new conversation; pass an existing id to continue one.
    conversation_id: Optional[uuid.UUID] = None


class AskResponse(BaseModel):
    answer: str
    conversation_id: uuid.UUID


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
