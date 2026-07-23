from langchain_core.embeddings import Embeddings
from app.config import settings
from typing import List
import requests


class GeminiEmbeddings(Embeddings):
    """
    Custom LangChain-compatible embeddings model querying Google's Gemini Embeddings API.
    Provides free, fast, and serverless vector generation without local weights or libraries.
    """

    def __init__(self, api_key: str, model_name: str = "models/gemini-embedding-001"):
        self.api_key = api_key
        self.model_name = model_name
        self.url = f"https://generativelanguage.googleapis.com/v1/{self.model_name}:embedContent?key={self.api_key}"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            # ponytail: simple loop, could be batched, but safe and simple
            api_response = requests.post(
                self.url, json={"content": {"parts": [{"text": text}]}}, timeout=10
            )
            api_response.raise_for_status()
            embeddings.append(api_response.json()["embedding"]["values"])
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        api_response = requests.post(
            self.url, json={"content": {"parts": [{"text": text}]}}, timeout=10
        )
        api_response.raise_for_status()
        return api_response.json()["embedding"]["values"]


def get_embedding_model() -> GeminiEmbeddings:
    api_key = settings.GEMINI_API_KEY

    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    return GeminiEmbeddings(api_key=api_key)
