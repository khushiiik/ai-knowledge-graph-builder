import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.workers.celery_app import celery_app
from app.dependencies import SessionLocal
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.document import Document, DocumentStatus
from app.pipeline.pipeline_runner import ingest_document_to_qdrant, run_lazy_indexing


@celery_app.task(
    bind=True,
    name="app.workers.tasks.ingest_document_task",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
)
def ingest_document_task(
    self,
    job_id_str: str,
    document_id_str: str,
    file_path: str,
    mime_type: str,
    tenant_id: int,
):
    db_session: Session = SessionLocal()
    job_id = uuid.UUID(job_id_str)
    document_id = uuid.UUID(document_id_str)

    try:
        # Run ingestion pipeline (which updates ProcessingJob step/progress details)
        ingest_document_to_qdrant(
            db=db_session,
            document_id=document_id,
            file_path=file_path,
            mime_type=mime_type,
            tenant_id=tenant_id,
            job_id=job_id,
        )

        # Update Document and Job status to completed
        document = db_session.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status = DocumentStatus.READY.value
            document.processed_at = func.now()

        processing_job = (
            db_session.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        )
        if processing_job:
            processing_job.status = ProcessingJobStatus.COMPLETED.value
            processing_job.progress = 100
            processing_job.current_step = "Completed"
            processing_job.finished_at = func.now()

        db_session.commit()

    except Exception as error:
        db_session.rollback()
        # If we have retries left, raise the exception to let Celery retry
        if self.request.retries < self.max_retries:
            processing_job = (
                db_session.query(ProcessingJob)
                .filter(ProcessingJob.id == job_id)
                .first()
            )
            if processing_job:
                processing_job.current_step = (
                    f"Retrying (Attempt {self.request.retries + 1}/{self.max_retries})"
                )
                db_session.commit()
            db_session.close()
            raise error

        import traceback

        traceback.print_exc()

        # Update Document and Job status to failed when all retries are exhausted
        document = db_session.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status = DocumentStatus.FAILED.value

        processing_job = (
            db_session.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        )
        if processing_job:
            processing_job.status = ProcessingJobStatus.FAILED.value
            processing_job.error_message = str(error)
            processing_job.finished_at = func.now()

        db_session.commit()
    finally:
        db_session.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.lazy_index_spreadsheet_task",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 5},
)
def lazy_index_spreadsheet_task(self, document_id_str: str, tenant_id: int):
    db_session: Session = SessionLocal()
    document_id = uuid.UUID(document_id_str)
    try:
        run_lazy_indexing(db_session, document_id, tenant_id)
    except Exception as error:
        db_session.rollback()
        if self.request.retries >= self.max_retries:
            document = (
                db_session.query(Document).filter(Document.id == document_id).first()
            )
            if document:
                document.embedding_status = "FAILED"
                db_session.commit()
        raise error
    finally:
        db_session.close()
