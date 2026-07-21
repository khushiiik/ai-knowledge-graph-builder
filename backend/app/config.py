import os
import dotenv

from pydantic_settings import BaseSettings, SettingsConfigDict


dotenv.load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Knowledge Graph Builder API"

    # PostgreSQL
    DATABASE_URL: str = (
        "postgresql://postgres:postgres_password@localhost:5432/knowledge_graph"
    )

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_password"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Ollama
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"

    # Groq (Online LLM Model)
    GEMINI_MODEL: str = "qwen2.5:3b"  # Default to local model if not set to groq
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # Hugging Face
    HUGGING_FACE_API_KEY: str | None = None

    # Pydantic Settings configuration to load from .env file
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    SECRET_KEY: str = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


settings = Settings()
