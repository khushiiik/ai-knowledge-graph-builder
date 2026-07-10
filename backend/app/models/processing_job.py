from enum import Enum
import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.user import Base

class ProcessingJobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ProcessingJobType(str, Enum):
    DOCUMENT_INDEXING = "DOCUMENT_INDEXING"
    DOCUMENT_DELETION = "DOCUMENT_DELETION"
    SUMMARY_GENERATION = "SUMMARY_GENERATION"
    REPORT_GENERATION = "REPORT_GENERATION"
    CHART_GENERATION = "CHART_GENERATION"
    TIMELINE_GENERATION = "TIMELINE_GENERATION"
    GRAPH_VISUALIZATION = "GRAPH_VISUALIZATION"
    EXPORT_EXCEL = "EXPORT_EXCEL"
    EXPORT_CSV = "EXPORT_CSV"

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    message_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    job_type = Column(String, nullable=False, index=True)
    status = Column(String, default=ProcessingJobStatus.QUEUED.value, nullable=False, index=True)
    progress = Column(Integer, default=0, nullable=False)
    current_step = Column(String, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(String, nullable=True)

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="processing_jobs")
    document = relationship("Document", backref="processing_jobs")
