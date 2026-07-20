import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.api.routes.auth import router as auth_router
from app.api.routes.document import router as documents_router
from app.api.routes.chat import router as chat_router
from app.api.routes.chart import router as chart_router


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up application...")
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
