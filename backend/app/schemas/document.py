from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.models.document import DocumentStatus


class DocumentBase(BaseModel):
    original_filename: str
    stored_filename: str
    storage_path: str
    file_type: str
    mime_type: str
    file_size: int
    checksum: str | None = None
    status: DocumentStatus = DocumentStatus.UPLOADING


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    original_filename: str | None = None
    stored_filename: str | None = None
    storage_path: str | None = None
    file_type: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    checksum: str | None = None
    status: DocumentStatus | None = None
    processed_at: datetime | None = None
    deleted_at: datetime | None = None


class DocumentRead(DocumentBase):
    id: UUID
    user_id: int
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None
    deleted_at: datetime | None = None
    progress: int | None = None
    current_step: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}
