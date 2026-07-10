from fastapi import APIRouter, Depends, status
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.dependencies import get_current_active_user
from app.models.user import User as UserModel
from app.schemas.chat import AskRequest, AskResponse
from app.llm.providers.ollama import OllamaProvider
from app.pipeline.pipeline_runner import get_tenant_retriever

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/ask", response_model=AskResponse, status_code=status.HTTP_200_OK)
def ask_question(
    payload: AskRequest,
    current_user: UserModel = Depends(get_current_active_user)
) -> AskResponse:
    """
    RAG Endpoint:
    1. Retrieves relevant text chunks from Qdrant, filtered by current user's tenant_id.
    2. Constructs a context-infused prompt.
    3. Queries Ollama and returns the generated answer.
    """
    provider = OllamaProvider()
    
    try:
        # Retrieve context from Qdrant
        retriever = get_tenant_retriever(tenant_id=current_user.id, limit=3)
        docs = retriever.invoke(payload.question)
        context = "\n\n---\n\n".join(doc.page_content for doc in docs)
    except Exception:
        # Fallback in case vector store has no documents or is uninitialized
        context = ""

    # Build standard RAG prompt
    rag_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer based ONLY on the context provided.\n"
                   "If the answer isn't in the context, say \"I don't have information about that.\"\n\n"
                   "Context:\n{context}"),
        ("human", "{question}"),
    ])

    # Run LangChain RAG pipeline
    chain = rag_prompt | provider.llm | StrOutputParser()
    answer = chain.invoke({"context": context, "question": payload.question})

    return AskResponse(answer=answer)
