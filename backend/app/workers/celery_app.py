from celery import Celery
from app.config import settings

celery_app = Celery(
    "app_workers",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC"
)
