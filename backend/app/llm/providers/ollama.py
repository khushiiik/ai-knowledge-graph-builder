from langchain_ollama import ChatOllama
from app.config import settings


class OllamaProvider:
    def __init__(self):
        # Configure ChatOllama using host and model settings loaded from env
        self.llm = ChatOllama(
            base_url=settings.OLLAMA_HOST, model=settings.OLLAMA_MODEL
        )

    def ask(self, question: str) -> str:
        """
        Sends a single question to the Ollama model and returns the string response.
        """
        response = self.llm.invoke(question)
        return str(response.content)

    def stream(self, messages: list[tuple[str, str]]):
        """
        Streams the model's reply for a (role, content) message list, yielding
        plain text chunks as they arrive instead of waiting for the full answer.
        """
        for chunk in self.llm.stream(messages):
            if chunk.content:
                yield chunk.content
