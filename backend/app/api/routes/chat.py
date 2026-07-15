import json
import uuid
import os
import re
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from app.core.exceptions import ConversationNotFoundException
from sqlalchemy.orm import Session
from sqlalchemy import func
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.dependencies import get_db, get_current_active_user, SessionLocal
from app.models.user import User as UserModel
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.schemas.chat import AskRequest, AskResponse, ConversationOut, MessageOut
from app.llm.providers.factory import get_llm_provider
from app.pipeline.pipeline_runner import get_tenant_retriever
from app.models.document import Document as DocumentModel
from app.llm.prompts.chat_prompt import build_chat_messages
from app.retrieval.semantic_search import retrieve_chunks, build_context_block
from app.retrieval.graph_search import graph_search
from app.retrieval.fusion import reciprocal_rank_fusion

router = APIRouter(prefix="/chat", tags=["chat"])


def normalize_text(text: str) -> str:
    """Normalize filenames and questions for matching."""
    text = text.lower()
    text = re.sub(r"\.[a-z0-9]+$", "", text)
    text = re.sub(r"[_\-\.\,\!\?\(\)\[\]\{\}]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify_intent(question: str) -> str:
    """Classify the user's question intent using rule-based heuristics."""
    q = question.lower().strip().strip("?.!")
    
    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "yo"}
    if q in greetings:
        return "greeting"
        
    list_keywords = ["list", "show", "what are", "which are", "display"]
    doc_keywords = ["documents", "files", "pdfs", "csvs", "uploads", "uploaded files", "uploaded documents"]
    if any(lk in q for lk in list_keywords) and any(dk in q for dk in doc_keywords):
        return "document_list"
    if "how many" in q and any(dk in q for dk in doc_keywords):
        return "document_count"
        
    focus_keywords = ["active", "focus", "focused", "selected", "current"]
    if any(fk in q for fk in focus_keywords) and any(dk in q for dk in doc_keywords + ["file", "document"]):
        return "document_focus"

    return "knowledge_query"


def _get_or_create_conversation(
    db: Session, user: UserModel, conversation_id: Optional[uuid.UUID]
) -> Conversation:
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if not conversation:
            raise ConversationNotFoundException()
        return conversation

    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation



@router.post("/ask")
def ask_question(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    Streaming RAG endpoint.

    1. Gets/creates the conversation and stores the user's message.
    2. Retrieves the relevant chunks previously embedded and stored in Qdrant
       (scoped to this user, so retrieval never crosses tenants).
    3. Streams the LLM's answer back token-by-token as Server-Sent Events, so
       the frontend can render it as it's generated instead of waiting.
    4. Once the stream finishes, persists the full assistant reply + which
       sources it was grounded in.
    """
    conversation = _get_or_create_conversation(db, current_user, payload.conversation_id)

    # 1. Fetch conversation history for memory before persisting current message
    db_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .all()
    )
    db_messages.reverse()
    history = []
    for msg in db_messages:
        role = "human" if msg.role == "user" else "ai"
        history.append((role, msg.content))

    # Add the current user question to the database
    db.add(Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=payload.question))
    
    # 2. LLM-based Title Generation (if None or default title is present)
    if conversation.title is None or conversation.title.startswith("New Semantic Session"):
        try:
            title_prompt = [
                (
                    "system",
                    "You are a helpful assistant. Generate a short, concise 3-to-5 word title summarizing the user's question. Do not use quotes or markdown. Return only the title text.",
                ),
                ("human", payload.question),
            ]
            provider = get_llm_provider()
            generated = provider.llm.invoke(title_prompt)
            conversation.title = str(generated.content).replace('"', '').replace("'", "").strip()[:80]
        except Exception:
            conversation.title = payload.question[:80]
            
    db.commit()

    # Extract primitive values before the request-scoped session closes
    conversation_id = conversation.id
    conversation_id_str = str(conversation_id)

    # 3. Fetch active documents for this user
    docs = db.query(DocumentModel).filter(
        DocumentModel.user_id == current_user.id,
        DocumentModel.deleted_at.is_(None)
    ).all()

    # Classify intent and route if not a knowledge query
    intent = classify_intent(payload.question)
    if intent != "knowledge_query":
        def simple_stream():
            yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
            
            if intent == "greeting":
                reply = "Hello! I am Vectra AI, your Knowledge Graph Builder assistant. Ask me questions about your uploaded documents or upload files to ingest into the database."
            elif intent == "document_list":
                if not docs:
                    reply = "You don't have any uploaded documents yet."
                else:
                    file_list = "\n".join(f"- {d.original_filename}" for d in docs)
                    reply = f"You have the following documents uploaded:\n{file_list}"
            elif intent == "document_count":
                reply = f"You currently have {len(docs)} document(s) uploaded."
            elif intent == "document_focus":
                focused_name = None
                if conversation.document_id:
                    f_doc = next((d for d in docs if d.id == conversation.document_id), None)
                    if f_doc:
                        focused_name = f_doc.original_filename
                if focused_name:
                    reply = f"The currently focused document is: **{focused_name}**"
                else:
                    reply = "No document is currently focused. Ask a question about a specific document or select one."
            else:
                reply = "I'm ready to help. What would you like to know?"
                
            yield f"data: {json.dumps({'token': reply})}\n\n"
            
            session = SessionLocal()
            try:
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        role=MessageRole.ASSISTANT.value,
                        content=reply,
                        sources=None
                    )
                )
                session.commit()
            finally:
                session.close()
                
            yield "event: done\ndata: {}\n\n"
            
        return StreamingResponse(simple_stream(), media_type="text/event-stream")

    # 4. Check if a document is explicitly mentioned in the query (updates conversation document focus)
    matched_doc = None
    normalized_question = normalize_text(payload.question)
    sorted_docs = sorted(docs, key=lambda d: len(d.original_filename), reverse=True)
    for doc in sorted_docs:
        norm_name = normalize_text(doc.original_filename)
        if (norm_name in normalized_question) or \
           (len(norm_name) > 3 and all(w in normalized_question.split() for w in norm_name.split())):
            matched_doc = doc
            break

    if matched_doc:
        conversation.document_id = matched_doc.id
        db.commit()

    # Auto-focus if only 1 document is uploaded and no focus is set
    if not conversation.document_id and len(docs) == 1:
        conversation.document_id = docs[0].id
        db.commit()

    # Check if this query is about "the document" (ambiguous)
    # Expanded to include csv, xlsx, excel, spreadsheet, docx, sheet
    is_ambiguous_doc_query = bool(re.search(
        r'\b(this|the|that|my|your|uploaded)?\s*(document|file|pdf|csv|xlsx|excel|spreadsheet|sheet|docx)\b', 
        payload.question.lower()
    ))

    # Stream clarification message if ambiguous query and multiple docs are uploaded with no focus
    if not conversation.document_id and len(docs) > 1 and is_ambiguous_doc_query:
        file_list_str = "\n".join(f"- {d.original_filename}" for d in docs)
        clarification_msg = (
            f"I see you have multiple documents uploaded. Which document are you referring to?\n\n"
            f"{file_list_str}\n\n"
            f"Please type the name of the document so I can focus on it."
        )
        
        def clarification_stream():
            yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
            yield f"data: {json.dumps({'token': clarification_msg})}\n\n"
            
            session = SessionLocal()
            try:
                session.add(
                    Message(
                        conversation_id=conversation_id,
                        role=MessageRole.ASSISTANT.value,
                        content=clarification_msg,
                        sources=None
                    )
                )
                session.commit()
            finally:
                session.close()
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(clarification_stream(), media_type="text/event-stream")

    # 5. Determine active document filter
    source_file = None
    document_in_focus = None
    if conversation.document_id:
        doc = db.query(DocumentModel).filter(DocumentModel.id == conversation.document_id).first()
        if doc:
            source_file = doc.stored_filename
            document_in_focus = doc.original_filename

    # 6. Build list of uploaded files to provide system template context
    uploaded_files_list = [d.original_filename for d in docs]

    # 7. Retrieve chunks (Qdrant) and related facts (Neo4j graph), then fuse
    semantic_chunks = retrieve_chunks(payload.question, tenant_id=current_user.id, limit=4, source_file=source_file)
    graph_facts = graph_search(payload.question, tenant_id=current_user.id, limit=5, source_file=source_file)
    chunks = reciprocal_rank_fusion([semantic_chunks, graph_facts], top_n=6)

    context = build_context_block(chunks)
    messages = build_chat_messages(
        context,
        payload.question,
        history=history,
        uploaded_files_list=uploaded_files_list,
        document_in_focus=document_in_focus
    )

    provider = get_llm_provider()

    def event_stream():
        # First event tells the client which conversation this reply belongs to
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"

        # Stream citation details at the start
        source_data = [
            {
                "text": c.get("text"),
                "source": c.get("source"),
                "page": c.get("page"),
                "type": c.get("type", "semantic")
            }
            for c in chunks
        ]
        yield f"event: sources\ndata: {json.dumps({'sources': source_data})}\n\n"

        full_answer = ""
        try:
            for token in provider.stream(messages):
                full_answer += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            return

        session = SessionLocal()
        try:
            session.add(
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=full_answer,
                    sources=source_data or None,
                )
            )
            session.commit()
        finally:
            session.close()

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut])
def get_conversation_messages(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Full message history for a conversation, oldest first -- used to re-hydrate a chat thread."""
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conversation:
        raise ConversationNotFoundException()
    return conversation.messages


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_200_OK)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Delete a conversation and all its messages."""
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conversation:
        raise ConversationNotFoundException()
    
    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted successfully"}