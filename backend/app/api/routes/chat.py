import json
import uuid
import os
import re
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.exceptions import ConversationNotFoundException
from app.dependencies import get_db, get_current_active_user, SessionLocal
from app.models.user import User as UserModel
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.document import Document as DocumentModel
from app.schemas.chat import AskRequest, AskResponse, ConversationOut, MessageOut
from app.llm.providers.factory import get_llm_provider
from app.pipeline.pipeline_runner import run_lazy_indexing
from app.llm.prompts.chat_prompt import build_chat_messages
from app.retrieval.semantic_search import retrieve_chunks, build_context_block
from app.retrieval.graph_search import graph_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.api.services.document_service import get_csv_schema_info
from app.workers.tasks import lazy_index_spreadsheet_task
from app.tools.router import ToolRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\.[a-z0-9]+$", "", text)
    text = re.sub(r"[_\-\.\,\!\?\(\)\[\]\{\}]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_doc_name(name: str) -> str:
    base = re.sub(r"\.[a-z0-9]+$", "", name.lower())
    base = re.sub(r"[\(\[\-_]?\s*\d+\s*[\)\]]?", " ", base)
    base = re.sub(r"\bcopy\b", " ", base)
    base = re.sub(r"[_\-\.\,\!\?\(\)\[\]\{\}]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()



def classify_intent(question: str) -> str:
    q = question.lower().strip().strip("?.!")
    
    if q in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "yo"}:
        return "greeting"
        
    list_keywords = ["list", "show", "what are", "which are", "display"]
    doc_keywords = ["documents", "files", "pdfs", "csvs", "uploads", "uploaded files", "uploaded documents"]
    if any(lk in q for lk in list_keywords) and any(dk in q for dk in doc_keywords):
        return "document_list"
    if "how many" in q and any(dk in q for dk in doc_keywords):
        return "document_count"
        
    if any(fk in q for fk in ["active", "focus", "focused", "selected", "current"]) and any(dk in q for dk in doc_keywords + ["file", "document"]):
        return "document_focus"

    return "knowledge_query"


def _get_or_create_conversation(db: Session, user: UserModel, conversation_id: Optional[uuid.UUID]) -> Conversation:
    if conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id, 
            Conversation.user_id == user.id
        ).first()
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
    conversation = _get_or_create_conversation(db, current_user, payload.conversation_id)

    db_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .all()
    )
    db_messages.reverse()
    history = [("human" if msg.role == "user" else "ai", msg.content) for msg in db_messages]

    db.add(Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=payload.question))
    
    if conversation.title is None or conversation.title.startswith("New Semantic Session"):
        try:
            title_prompt = [
                ("system", "Generate a short, concise 3-to-5 word title summarizing the user's question. Do not use quotes or markdown. Return only the title text."),
                ("human", payload.question),
            ]
            provider = get_llm_provider()
            generated = provider.llm.invoke(title_prompt)
            conversation.title = str(generated.content).replace('"', '').replace("'", "").strip()[:80]
        except Exception:
            conversation.title = payload.question[:80]
            
    db.commit()

    conversation_id = conversation.id
    conversation_id_str = str(conversation_id)
    user_id = current_user.id

    docs = db.query(DocumentModel).filter(
        DocumentModel.user_id == user_id,
        DocumentModel.deleted_at.is_(None)
    ).all()

    intent = classify_intent(payload.question)

    if not docs and intent != "greeting":
        def no_docs_stream():
            yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
            reply = "No active documents found in your knowledge base. Please upload a document (PDF, CSV, TXT, etc.) first so I can process and map out your knowledge graph."
            yield f"data: {json.dumps({'token': reply})}\n\n"
            
            session = SessionLocal()
            try:
                session.add(Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT.value, content=reply))
                session.commit()
            finally:
                session.close()
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(no_docs_stream(), media_type="text/event-stream")
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
                reply = f"The currently focused document is: **{focused_name}**" if focused_name else "No document is currently focused. Ask a question about a specific document or select one."
            else:
                reply = "I'm ready to help. What would you like to know?"
                
            yield f"data: {json.dumps({'token': reply})}\n\n"
            
            session = SessionLocal()
            try:
                session.add(Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT.value, content=reply))
                session.commit()
            finally:
                session.close()
            yield "event: done\ndata: {}\n\n"
            
        return StreamingResponse(simple_stream(), media_type="text/event-stream")

    matched_doc = None
    normalized_question = normalize_text(payload.question)
    cleaned_question = clean_doc_name(payload.question)
    sorted_docs = sorted(docs, key=lambda d: len(d.original_filename), reverse=True)
    for doc in sorted_docs:
        norm_name = normalize_text(doc.original_filename)
        clean_name = clean_doc_name(doc.original_filename)
        if (norm_name in normalized_question) or (clean_name and clean_name in cleaned_question):
            matched_doc = doc
            break

        clean_words = [w for w in clean_name.split() if len(w) > 2]
        if clean_words:
            matched_count = sum(1 for w in clean_words if w in cleaned_question.split())
            if matched_count / len(clean_words) >= 0.5:
                matched_doc = doc
                break


    if matched_doc:
        conversation.document_id = matched_doc.id
        db.commit()

    if not conversation.document_id and len(docs) == 1:
        conversation.document_id = docs[0].id
        db.commit()

    is_ambiguous_doc_query = bool(re.search(
        r'\b(this|the|that|my|your|uploaded)?\s*(document|file|pdf|csv|xlsx|excel|spreadsheet|sheet|docx)\b', 
        payload.question.lower()
    ))

    # Explicit CSV / Excel export intent detection
    is_export_requested = any(k in payload.question.lower() for k in [
        "csv", "excel", "spreadsheet", "export", "download csv", "make csv", 
        "create csv", "provide csv", "generate csv", "give me csv", "give csv", "provide me csv", "tabular"
    ])

    if not conversation.document_id and len(docs) > 1 and is_ambiguous_doc_query and not is_export_requested:
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
                session.add(Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT.value, content=clarification_msg))
                session.commit()
            finally:
                session.close()
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(clarification_stream(), media_type="text/event-stream")

    if is_export_requested:
        def csv_export_stream():
            yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
            
            db_session = SessionLocal()
            try:
                doc_id = conversation.document_id
                fmt = "excel" if ("excel" in payload.question.lower() or "xlsx" in payload.question.lower()) else "csv"
                result = ToolRouter.execute(
                    tool_name="spreadsheet_export",
                    arguments={
                        "document_id": str(doc_id) if doc_id else "<document_id>",
                        "query": payload.question,
                        "format": fmt
                    },
                    db=db_session,
                    user_id=user_id
                )
                
                download_url = result.get("download_url")
                download_filename = result.get("filename", "exported_data.csv")
                record_count = result.get("record_count", 0)
                
                reply = (
                    f"I have successfully extracted {record_count} structured record(s) from your document based on your request. "
                    f"You can download the file here: [Download {download_filename}]({download_url})"
                )
                
                yield f"data: {json.dumps({'token': reply})}\n\n"
                yield f"event: download\ndata: {json.dumps({'downloadUrl': download_url, 'downloadFilename': download_filename})}\n\n"
                
                source_data = [{
                    "type": "download",
                    "downloadUrl": download_url,
                    "downloadFilename": download_filename
                }]
                
                db_session.add(Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=reply,
                    sources=source_data
                ))
                db_session.commit()
            except Exception as e:
                logger.error(f"CSV Export stream error: {str(e)}")
                err_msg = f"Failed to generate CSV file: {str(e)}"
                yield f"data: {json.dumps({'token': err_msg})}\n\n"
                db_session.add(Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=err_msg
                ))
                db_session.commit()
            finally:
                db_session.close()
                
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(csv_export_stream(), media_type="text/event-stream")

    source_file = None
    document_in_focus = None
    schema_info = None
    active_doc_id = None
    
    if conversation.document_id:
        doc = db.query(DocumentModel).filter(
            DocumentModel.id == conversation.document_id,
            DocumentModel.user_id == user_id
        ).first()
        if doc:
            source_file = doc.stored_filename
            document_in_focus = doc.original_filename
            active_doc_id = str(doc.id)
            if doc.file_type.lower() in ('csv', 'xlsx', 'xls'):
                if doc.dataset_profile:
                    try:
                        profile_dict = doc.dataset_profile
                        schema_lines = [
                            f"Row count: {profile_dict.get('row_count')}",
                            f"Column count: {profile_dict.get('column_count')}",
                            "Columns:"
                        ]
                        for c in profile_dict.get('columns', []):
                            schema_lines.append(f"  - {c.get('name')} ({c.get('type')}, role: {c.get('role')})")
                        if profile_dict.get('statistics'):
                            schema_lines.append("Column Statistics:")
                            for col, stats in profile_dict['statistics'].items():
                                schema_lines.append(f"  - {col}: min={stats.get('min')}, max={stats.get('max')}, mean={stats.get('mean')}")
                        if profile_dict.get('supports'):
                            schema_lines.append("Capabilities:")
                            for cap, val in profile_dict['supports'].items():
                                schema_lines.append(f"  - {cap}: {val}")
                        schema_info = "\n".join(schema_lines)
                    except Exception:
                        schema_info = get_csv_schema_info(doc)
                else:
                    schema_info = get_csv_schema_info(doc)

    uploaded_files_list = [d.original_filename for d in docs]
    
    if conversation.document_id:
        doc = db.query(DocumentModel).filter(
            DocumentModel.id == conversation.document_id,
            DocumentModel.user_id == user_id
        ).first()
        if doc and doc.file_type.lower() in ('csv', 'xlsx', 'xls'):
            is_semantic_query = any(w in payload.question.lower() for w in ('find', 'search', 'similar', 'comment', 'incident', 'feedback', 'complaint', 'mention', 'discuss'))
            if is_semantic_query:
                if doc.embedding_status == "NOT_STARTED":
                    profile = doc.dataset_profile or {}
                    row_count = profile.get("row_count", 0)
                    
                    if row_count < 1000:
                        run_lazy_indexing(db, doc.id, user_id)
                    else:
                        doc.embedding_status = "PROCESSING"
                        db.commit()
                        lazy_index_spreadsheet_task.delay(str(doc.id), user_id)
                        
                        def bg_indexing_stream():
                            yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
                            reply = f"I am building the semantic index for this spreadsheet in the background (dataset size: {row_count} rows). Please repeat your request in a few seconds once it is ready."
                            yield f"data: {json.dumps({'token': reply})}\n\n"
                            
                            session = SessionLocal()
                            try:
                                session.add(Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT.value, content=reply))
                                session.commit()
                            finally:
                                session.close()
                            yield "event: done\ndata: {}\n\n"
                            
                        return StreamingResponse(bg_indexing_stream(), media_type="text/event-stream")
                        
                elif doc.embedding_status == "PROCESSING":
                    def waiting_stream():
                        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
                        reply = "The semantic index is currently being built in the background. Please wait a few moments and try your query again."
                        yield f"data: {json.dumps({'token': reply})}\n\n"
                        yield "event: done\ndata: {}\n\n"
                    return StreamingResponse(waiting_stream(), media_type="text/event-stream")

    is_comprehensive_query = any(w in payload.question.lower() for w in (
        'list', 'all', 'every', 'who', 'show', 'filter', 'employee', 'project',
        'summary', 'directory', 'table', 'report', 'detail', 'complete', 'name',
        'item', 'give me', 'provide', 'bring', 'find all', 'count', 'tenure', 'years',
        'working', 'department', 'position', 'location'
    ))

    sem_limit = 25 if is_comprehensive_query else 10
    top_fused = 25 if is_comprehensive_query else 10

    semantic_chunks = retrieve_chunks(payload.question, tenant_id=user_id, limit=sem_limit, source_file=source_file)
    graph_facts = graph_search(payload.question, tenant_id=user_id, limit=15, source_file=source_file)
    chunks = reciprocal_rank_fusion([semantic_chunks, graph_facts], top_n=top_fused)


    context = build_context_block(chunks)
    messages = build_chat_messages(
        context,
        payload.question,
        history=history,
        uploaded_files_list=uploaded_files_list,
        document_in_focus=document_in_focus,
        document_id=active_doc_id,
        schema_info=schema_info
    )

    provider = get_llm_provider()

    def event_stream():
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"

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

        clean_answer = full_answer.strip()
        if clean_answer.startswith("```"):
            lines = clean_answer.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_answer = "\n".join(lines).strip()

        is_tool_call = False
        tool_figure = None
        tool_error = None
        tool_name = None
        synthesized_reply = None
        
        try:
            json_match = re.search(r"\{[\s\S]*\}", clean_answer)

            parsed = None
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except Exception:
                    pass
            if isinstance(parsed, dict) and parsed.get("type") == "tool":
                is_tool_call = True
                tool_name = parsed.get("tool")
                tool_args = parsed.get("arguments", {})
                
                db_session = SessionLocal()
                try:
                    result = ToolRouter.execute(
                        tool_name=tool_name,
                        arguments=tool_args,
                        db=db_session,
                        user_id=user_id
                    )
                    if tool_name == "chart_generator":
                        tool_figure = result.get("figure")
                    elif tool_name == "spreadsheet_query":
                        query_result = result.get("result", "No result returned")
                        synthesis_prompt = [
                            ("system", "You are a helpful data analyst. Convert the raw Pandas query result into a clear, concise conversational explanation for the user. Do not explain the code, just state the facts and results."),
                            ("human", f"User question: {payload.question}\nRaw Pandas query result:\n{query_result}")
                        ]
                        synthesis_response = provider.llm.invoke(synthesis_prompt)
                        synthesized_reply = str(synthesis_response.content).strip()
                        yield f"data: {json.dumps({'token': f'\\n\\n**Analysis Result:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "spreadsheet_export":
                        download_url = result.get("download_url")
                        download_filename = result.get("filename", "exported_data.csv")
                        record_count = result.get("record_count", 0)
                        reply = f"I have successfully extracted {record_count} structured record(s) based on your request. You can download the file here: [Download {download_filename}]({download_url})"
                        synthesized_reply = reply
                        yield f"data: {json.dumps({'token': f'\\n\\n{synthesized_reply}'})}\n\n"
                        yield f"event: download\ndata: {json.dumps({'downloadUrl': download_url, 'downloadFilename': download_filename})}\n\n"
                    elif tool_name == "timeline_generator":
                        timeline_events = result.get("events", [])
                        reply = f"I have successfully generated a timeline with {len(timeline_events)} event(s) from the document."
                        synthesized_reply = reply
                        yield f"data: {json.dumps({'token': f'\\n\\n{synthesized_reply}'})}\n\n"
                        yield f"event: timeline\ndata: {json.dumps({'events': timeline_events})}\n\n"
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {str(e)}")
                    tool_error = str(e)
                    if tool_name == "spreadsheet_query":
                        synthesized_reply = f"Failed to execute spreadsheet query: {str(e)}"
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "spreadsheet_export":
                        synthesized_reply = f"Failed to execute spreadsheet export: {str(e)}"
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "timeline_generator":
                        synthesized_reply = f"Failed to generate timeline: {str(e)}"
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                finally:
                    db_session.close()
        except json.JSONDecodeError:
            pass

        session = SessionLocal()
        try:
            if is_tool_call:
                if tool_name == "chart_generator" and tool_figure:
                    content_to_save = f"Generated {tool_name} chart."
                    yield f"event: chart\ndata: {json.dumps({'figure': tool_figure})}\n\n"
                    if not source_data:
                        source_data = []
                    source_data.append({
                        "type": "chart",
                        "figure": tool_figure
                    })
                elif tool_name == "timeline_generator" and 'timeline_events' in locals() and timeline_events:
                    content_to_save = f"Generated timeline with {len(timeline_events)} events."
                    if not source_data:
                        source_data = []
                    source_data.append({
                        "type": "timeline",
                        "events": timeline_events
                    })
                elif tool_name in ("spreadsheet_query", "spreadsheet_export") and synthesized_reply:
                    content_to_save = synthesized_reply
                    if tool_name == "spreadsheet_export" and 'result' in locals() and isinstance(result, dict) and result.get("download_url"):
                        if not source_data:
                            source_data = []
                        source_data.append({
                            "type": "download",
                            "downloadUrl": result.get("download_url"),
                            "downloadFilename": result.get("filename", "exported_data.csv")
                        })

                else:
                    content_to_save = f"Failed to execute tool '{tool_name}': {tool_error}"
                    if tool_name not in ("spreadsheet_query", "spreadsheet_export", "timeline_generator"):
                        yield f"data: {json.dumps({'token': f'\\n*Error: {content_to_save}*'})}\n\n"
            else:
                content_to_save = full_answer

            session.add(
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=content_to_save,
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