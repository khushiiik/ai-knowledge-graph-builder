from app.config import settings

def get_llm_provider():
    """
    Factory function to instantiate and return the correct LLM provider.
    Defaults to OllamaProvider if GEMINI_MODEL does not target Groq.
    """
    if settings.GEMINI_MODEL.startswith("groq/") and settings.GROQ_API_KEY:
        from app.llm.providers.groq import GroqProvider
        return GroqProvider()
    
    try:
        from app.llm.providers.ollama import OllamaProvider
        return OllamaProvider()
    except ImportError:
        raise ImportError(
            "langchain-ollama is not installed. Since GEMINI_MODEL is not set to a groq/ model, "
            "please install langchain-ollama or configure GEMINI_MODEL=groq/... in your .env"
        )
