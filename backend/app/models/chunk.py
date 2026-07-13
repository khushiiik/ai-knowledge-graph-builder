import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.user import Base

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    source_filename = Column(String, nullable=False)
    page_section = Column(String, nullable=True)
    qdrant_point_id = Column(String, nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", backref="chunks")
    user = relationship("User", backref="chunks")
