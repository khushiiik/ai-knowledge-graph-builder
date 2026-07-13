import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_active_user, SessionLocal
from app.models.user import User as UserModel
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.schemas.chat import AskRequest, ConversationOut, MessageOut
from app.llm.providers.factory import get_llm_provider
from app.llm.prompts.chat_prompt import build_chat_messages
from app.retrieval.semantic_search import retrieve_chunks, build_context_block

router = APIRouter(prefix="/chat", tags=["chat"])


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
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
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

    db.add(Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=payload.question))
    if conversation.title is None:
        conversation.title = payload.question[:80]
    db.commit()

    # Extract primitive values before the request-scoped session closes
    conversation_id = conversation.id
    conversation_id_str = str(conversation_id)

    # 1. Fetch active documents for this user
    from app.models.document import Document as DocumentModel
    docs = db.query(DocumentModel).filter(
        DocumentModel.user_id == current_user.id,
        DocumentModel.deleted_at.is_(None)
    ).all()

    # 2. Check if a document is mentioned in the query (updates conversation document focus)
    import os
    matched_doc = None
    sorted_docs = sorted(docs, key=lambda d: len(d.original_filename), reverse=True)
    for doc in sorted_docs:
        no_ext = os.path.splitext(doc.original_filename)[0]
        if (doc.original_filename.lower() in payload.question.lower()) or \
           (len(no_ext) > 3 and no_ext.lower() in payload.question.lower()):
            matched_doc = doc
            break

    if matched_doc:
        conversation.document_id = matched_doc.id
        db.commit()

    # 3. Determine active document filter
    source_file = None
    document_in_focus = None
    if conversation.document_id:
        doc = db.query(DocumentModel).filter(DocumentModel.id == conversation.document_id).first()
        if doc:
            source_file = doc.stored_filename
            document_in_focus = doc.original_filename

    # 4. Build list of uploaded files to provide system template context
    uploaded_files_list = [d.original_filename for d in docs]

    # 5. Retrieve chunks and construct LLM prompts
    chunks = retrieve_chunks(payload.question, tenant_id=current_user.id, limit=4, source_file=source_file)
    context = build_context_block(chunks)
    messages = build_chat_messages(
        context,
        payload.question,
        uploaded_files_list=uploaded_files_list,
        document_in_focus=document_in_focus
    )

    provider = get_llm_provider()

    def event_stream():
        # First event tells the client which conversation this reply belongs to
        # (important the very first time, when no conversation_id was sent yet).
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"

        full_answer = ""
        try:
            for token in provider.stream(messages):
                full_answer += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            return

        # Use a fresh session here rather than the request-scoped `db` above --
        # that one belongs to the request lifecycle and may already be torn
        # down by the time this generator finishes streaming to the client.
        session = SessionLocal()
        try:
            session.add(
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=full_answer,
                    sources=[{"source": c["source"]} for c in chunks] or None,
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation.messages
