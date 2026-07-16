import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.api.routes.auth import router as auth_router
from app.api.routes.document import router as documents_router
from app.api.routes.chat import router as chat_router
from app.api.routes.chart import router as chart_router
from app.models.user import Base
from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.chunk import Chunk
from app.dependencies import engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    # Add document_id column to conversations table if it doesn't exist
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                ALTER TABLE conversations 
                ADD COLUMN IF NOT EXISTS document_id UUID REFERENCES documents(id) ON DELETE SET NULL;
            """
                )
            )
        logger.info("Database tables initialized successfully and alter table checked.")
    except Exception as e:
        logger.error(f"Error checking/adding document_id column: {str(e)}")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend service for the AI Knowledge Graph Builder.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(chart_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to AI Knowledge Graph Builder API",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "status": "online",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
