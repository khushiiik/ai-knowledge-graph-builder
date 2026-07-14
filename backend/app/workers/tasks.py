import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.workers.celery_app import celery_app
from app.dependencies import SessionLocal
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.document import Document, DocumentStatus
from app.pipeline.pipeline_runner import ingest_document_to_qdrant

@celery_app.task(
    bind=True,
    name="app.workers.tasks.ingest_document_task",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5}
)
def ingest_document_task(self, job_id_str: str, document_id_str: str, file_path: str, mime_type: str, tenant_id: int):
    db: Session = SessionLocal()
    job_id = uuid.UUID(job_id_str)
    document_id = uuid.UUID(document_id_str)
    
    try:
        # Run ingestion pipeline (which updates ProcessingJob step/progress details)
        ingest_document_to_qdrant(
            db=db,
            document_id=document_id,
            file_path=file_path,
            mime_type=mime_type,
            tenant_id=tenant_id,
            job_id=job_id
        )
        
        # Update Document and Job status to completed
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.READY.value
            doc.processed_at = func.now()
        
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.status = ProcessingJobStatus.COMPLETED.value
            job.progress = 100
            job.current_step = "Completed"
            job.finished_at = func.now()
            
        db.commit()
        
    except Exception as e:
        db.rollback()
        # If we have retries left, raise the exception to let Celery retry
        if self.request.retries < self.max_retries:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.current_step = f"Retrying (Attempt {self.request.retries + 1}/{self.max_retries})"
                db.commit()
            db.close()
            raise e

        import traceback
        traceback.print_exc()
        
        # Update Document and Job status to failed when all retries are exhausted
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.FAILED.value
            
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.status = ProcessingJobStatus.FAILED.value
            job.error_message = str(e)
            job.finished_at = func.now()
            
        db.commit()
    finally:
        db.close()
