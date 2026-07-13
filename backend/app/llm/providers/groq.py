from langchain_community.chat_models import ChatOpenAI
from app.config import settings

class GroqProvider:
    """
    Online LLM provider using Groq API via LangChain's OpenAI-compatible ChatOpenAI model.
    """
    def __init__(self):
        # Extract model name (e.g., 'llama-3.3-70b-versatile' from 'groq/llama-3.3-70b-versatile')
        model_name = settings.GEMINI_MODEL.replace("groq/", "")
        self.llm = ChatOpenAI(
            openai_api_base="https://api.groq.com/openai/v1",
            openai_api_key=settings.GROQ_API_KEY,
            model_name=model_name
        )

    def ask(self, question: str) -> str:
        """
        Sends a single question to the Groq model and returns the string response.
        """
        response = self.llm.invoke(question)
        return str(response.content)

    def stream(self, messages: list[tuple[str, str]]):
        """
        Streams the model's reply for a (role, content) message list, yielding
        plain text chunks as they arrive.
        """
        for chunk in self.llm.stream(messages):
            if chunk.content:
                yield chunk.content
