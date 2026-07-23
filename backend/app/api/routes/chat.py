import json
import uuid
import os
import re
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.exceptions import ConversationNotFoundException, EmptyQuestionException
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

AGREEMENT_WORDS = (
    "yes",
    "y",
    "yeah",
    "yep",
    "sure",
    "correct",
    "agree",
    "okay",
    "ok",
    "yes please",
)


def normalize_text(text: str) -> str:
    """Normalize text for document matching."""
    text_lower = text.lower()
    text_without_extension = re.sub(r"\.[a-z0-9]+$", "", text_lower)
    text_with_spaces = re.sub(
        r"[_\-\.\,\!\?\(\)\[\]\{\}]+", " ", text_without_extension
    )
    text_normalized_whitespace = re.sub(r"\s+", " ", text_with_spaces)
    return text_normalized_whitespace.strip()


def clean_doc_name(name: str) -> str:
    """Clean document filename to find base keywords."""
    base_name = re.sub(r"\.[a-z0-9]+$", "", name.lower())
    base_name = re.sub(r"[\(\[\-_]?\s*\d+\s*[\)\]]?", " ", base_name)
    base_name = re.sub(r"\bcopy\b", " ", base_name)
    base_name = re.sub(r"[_\-\.\,\!\?\(\)\[\]\{\}]+", " ", base_name)
    return re.sub(r"\s+", " ", base_name).strip()


def classify_intent(question: str) -> str:
    """Classify the user's intent based on keywords."""
    question_lower = question.lower().strip().strip("?.!")

    if question_lower in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "greetings",
        "yo",
    }:
        return "greeting"

    list_keywords = ["list", "show", "what are", "which are", "display"]
    document_keywords = [
        "documents",
        "files",
        "pdfs",
        "csvs",
        "uploads",
        "uploaded files",
        "uploaded documents",
    ]

    has_list_keyword = False
    for list_keyword in list_keywords:
        if list_keyword in question_lower:
            has_list_keyword = True
            break

    has_document_keyword = False
    for document_keyword in document_keywords:
        if document_keyword in question_lower:
            has_document_keyword = True
            break

    if has_list_keyword and has_document_keyword:
        return "document_list"

    if "how many" in question_lower and has_document_keyword:
        return "document_count"

    focus_keywords = ["active", "focus", "focused", "selected", "current"]
    has_focus_keyword = False
    for focus_keyword in focus_keywords:
        if focus_keyword in question_lower:
            has_focus_keyword = True
            break

    document_and_file_keywords = document_keywords + ["file", "document"]
    has_doc_or_file_keyword = False
    for keyword in document_and_file_keywords:
        if keyword in question_lower:
            has_doc_or_file_keyword = True
            break

    if has_focus_keyword and has_doc_or_file_keyword:
        return "document_focus"

    return "knowledge_query"


def _get_or_create_conversation(
    db: Session, user: UserModel, conversation_id: Optional[uuid.UUID]
) -> Conversation:
    """Finds an existing conversation for the tenant user or creates a new one."""
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


def fuzzy_replace(text: str, target: str, replacement: str) -> str:
    """Performs fuzzy matching to replace a target phrase inside a query."""
    import difflib

    # Try exact case-insensitive replacement first
    pattern = re.compile(re.escape(target), re.IGNORECASE)
    if pattern.search(text):
        return pattern.sub(replacement, text)

    # Slide a window to find the closest match for the target
    target_words = []
    for word in target.split():
        if len(word) > 1:
            target_words.append(word)

    if not target_words:
        return text

    text_words = text.split()
    best_ratio = 0.0
    best_start_idx = -1
    best_end_idx = -1

    num_target_words = len(target_words)
    min_window_size = max(1, num_target_words - 2)
    max_window_size = num_target_words + 3

    for window_size in range(min_window_size, max_window_size):
        for index in range(len(text_words) - window_size + 1):
            window_string = " ".join(text_words[index : index + window_size])
            ratio = difflib.SequenceMatcher(
                None, target.lower(), window_string.lower()
            ).ratio()
            if ratio > best_ratio and ratio > 0.5:
                best_ratio = ratio
                best_start_idx = index
                best_end_idx = index + window_size

    if best_start_idx != -1:
        replaced = (
            text_words[:best_start_idx] + [replacement] + text_words[best_end_idx:]
        )
        return " ".join(replaced)

    return text


def _resolve_suggestion_agreement(question: str, history: List[tuple]) -> str:
    """Updates the query if the user states agreement with a spelling correction suggestion."""
    question_clean = question.lower().strip().rstrip(".!?")
    is_agreement = question_clean in AGREEMENT_WORDS

    if not (is_agreement and history):
        return question

    last_assistant_msg = None
    for role, text in reversed(history):
        if role in ("ai", "assistant"):
            last_assistant_msg = text
            break

    if last_assistant_msg:
        # Match both terms in double quotes from: "term1" is not available. Did you mean "term2"?
        matches = re.findall(r'"([^"]+)"', last_assistant_msg)
        if len(matches) >= 2:
            missing_term = matches[0]
            suggested_term = matches[1]

            # Find the last user query in history
            last_user_query = None
            for role, text in reversed(history):
                if role in ("human", "user"):
                    text_clean = text.lower().strip().rstrip(".!?")
                    if text_clean not in AGREEMENT_WORDS:
                        last_user_query = text
                        break

            if last_user_query:
                corrected_query = fuzzy_replace(
                    last_user_query, missing_term, suggested_term
                )
                logger.info(
                    f"User agreed to suggestion. Corrected query from '{last_user_query}' to '{corrected_query}'"
                )
                return corrected_query

    return question


def _auto_generate_conversation_title(
    db: Session, conversation: Conversation, question: str
) -> None:
    """Generates an initial conversation summary title if it is a new session."""
    if conversation.title is not None and not conversation.title.startswith(
        "New Semantic Session"
    ):
        return

    try:
        title_prompt = [
            (
                "system",
                "Generate a short, concise 3-to-5 word title summarizing the user's question. Do not use quotes or markdown. Return only the title text.",
            ),
            ("human", question),
        ]
        provider = get_llm_provider()
        generated = provider.llm.invoke(title_prompt)
        cleaned_title = str(generated.content).replace('"', "").replace("'", "").strip()
        conversation.title = cleaned_title[:80]
    except Exception:
        conversation.title = question[:80]

    db.commit()


def _find_matching_document(
    documents: List[DocumentModel], question: str
) -> Optional[DocumentModel]:
    """Scans uploaded files to locate a document matching text in the user query."""
    normalized_question = normalize_text(question)
    cleaned_question = clean_doc_name(question)
    sorted_docs = sorted(
        documents, key=lambda doc: len(doc.original_filename), reverse=True
    )

    for doc in sorted_docs:
        normalized_name = normalize_text(doc.original_filename)
        cleaned_name = clean_doc_name(doc.original_filename)

        if (normalized_name in normalized_question) or (
            cleaned_name and cleaned_name in cleaned_question
        ):
            return doc

        cleaned_words = []
        for word in cleaned_name.split():
            if len(word) > 2:
                cleaned_words.append(word)

        if cleaned_words:
            matched_count = 0
            cleaned_question_words = cleaned_question.split()
            for word in cleaned_words:
                if word in cleaned_question_words:
                    matched_count += 1

            if matched_count / len(cleaned_words) >= 0.5:
                return doc

    return None


def _extract_schema_info_from_profile(doc: DocumentModel) -> Optional[str]:
    """Generates CSV/Excel structural schema text from the document profile."""
    if doc.file_type.lower() not in ("csv", "xlsx", "xls"):
        return None

    if not doc.dataset_profile:
        return get_csv_schema_info(doc)

    try:
        profile_dict = doc.dataset_profile
        schema_lines = [
            f"Row count: {profile_dict.get('row_count')}",
            f"Column count: {profile_dict.get('column_count')}",
            "Columns:",
        ]
        for column in profile_dict.get("columns", []):
            schema_lines.append(
                f"  - {column.get('name')} ({column.get('type')}, role: {column.get('role')})"
            )

        statistics = profile_dict.get("statistics")
        if statistics:
            schema_lines.append("Column Statistics:")
            for col_name, stats in statistics.items():
                schema_lines.append(
                    f"  - {col_name}: min={stats.get('min')}, max={stats.get('max')}, mean={stats.get('mean')}"
                )

        supports = profile_dict.get("supports")
        if supports:
            schema_lines.append("Capabilities:")
            for capability, val in supports.items():
                schema_lines.append(f"  - {capability}: {val}")

        return "\n".join(schema_lines)
    except Exception:
        return get_csv_schema_info(doc)


def _handle_no_documents_response(
    conversation_id_str: str, conversation_id: uuid.UUID
) -> StreamingResponse:
    """Stream response returned when user has zero uploaded documents."""

    def no_docs_stream():
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
        reply = (
            "No active documents found in your knowledge base. Please upload a document "
            "(PDF, CSV, TXT, etc.) first so I can process and map out your knowledge graph."
        )
        yield f"data: {json.dumps({'token': reply})}\n\n"

        session = SessionLocal()
        try:
            session.add(
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=reply,
                )
            )
            session.commit()
        finally:
            session.close()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(no_docs_stream(), media_type="text/event-stream")


def _handle_simple_intents_response(
    intent: str,
    documents: List[DocumentModel],
    conversation: Conversation,
    conversation_id_str: str,
    conversation_id: uuid.UUID,
) -> StreamingResponse:
    """Stream response for basic intents (greetings, file counting/listings, focused files)."""

    def simple_stream():
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
        if intent == "greeting":
            reply = (
                "Hello! I am Vectra AI, your Knowledge Graph Builder assistant. Ask me questions "
                "about your uploaded documents or upload files to ingest into the database."
            )
        elif intent == "document_list":
            if not documents:
                reply = "You don't have any uploaded documents yet."
            else:
                file_list = "\n".join(f"- {doc.original_filename}" for doc in documents)
                reply = f"You have the following documents uploaded:\n{file_list}"
        elif intent == "document_count":
            reply = f"You currently have {len(documents)} document(s) uploaded."
        elif intent == "document_focus":
            focused_name = None
            if conversation.document_id:
                focused_doc = None
                for document in documents:
                    if document.id == conversation.document_id:
                        focused_doc = document
                        break
                if focused_doc:
                    focused_name = focused_doc.original_filename
            reply = (
                f"The currently focused document is: **{focused_name}**"
                if focused_name
                else "No document is currently focused. Ask a question about a specific document or select one."
            )
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
                )
            )
            session.commit()
        finally:
            session.close()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(simple_stream(), media_type="text/event-stream")


def _handle_ambiguous_document_response(
    documents: List[DocumentModel], conversation_id_str: str, conversation_id: uuid.UUID
) -> StreamingResponse:
    """Stream clarification response prompt when query refers to ambiguous 'document'."""
    file_list_str = "\n".join(f"- {doc.original_filename}" for doc in documents)
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
                )
            )
            session.commit()
        finally:
            session.close()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(clarification_stream(), media_type="text/event-stream")


def _handle_csv_export_response(
    question: str,
    conversation_id: uuid.UUID,
    conversation_id_str: str,
    document_id: Optional[uuid.UUID],
    user_id: int,
) -> StreamingResponse:
    """Stream CSV/Excel tabular extraction tool routing execution response."""

    def csv_export_stream():
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"

        db_session = SessionLocal()
        try:
            doc_id = document_id
            question_lower = question.lower()
            if "excel" in question_lower or "xlsx" in question_lower:
                export_format = "excel"
            else:
                export_format = "csv"

            result = ToolRouter.execute(
                tool_name="spreadsheet_export",
                arguments={
                    "document_id": str(doc_id) if doc_id else "<document_id>",
                    "query": question,
                    "format": export_format,
                },
                db=db_session,
                user_id=user_id,
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

            source_data = [
                {
                    "type": "download",
                    "downloadUrl": download_url,
                    "downloadFilename": download_filename,
                }
            ]

            db_session.add(
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=reply,
                    sources=source_data,
                )
            )
            db_session.commit()
        except Exception as error:
            logger.error(f"CSV Export stream error: {str(error)}")
            err_msg = f"Failed to generate CSV file: {str(error)}"
            yield f"data: {json.dumps({'token': err_msg})}\n\n"
            db_session.add(
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=err_msg,
                )
            )
            db_session.commit()
        finally:
            db_session.close()

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(csv_export_stream(), media_type="text/event-stream")


def _handle_lazy_indexing_for_spreadsheet(
    db: Session,
    doc: DocumentModel,
    question: str,
    user_id: int,
    conversation_id: uuid.UUID,
    conversation_id_str: str,
) -> Optional[StreamingResponse]:
    """Validates and triggers background semantic indexing for spreadsheets if requested."""
    if doc.file_type.lower() not in ("csv", "xlsx", "xls"):
        return None

    question_lower = question.lower()
    semantic_keywords = (
        "find",
        "search",
        "similar",
        "comment",
        "incident",
        "feedback",
        "complaint",
        "mention",
        "discuss",
    )

    is_semantic_query = False
    for keyword in semantic_keywords:
        if keyword in question_lower:
            is_semantic_query = True
            break

    if not is_semantic_query:
        return None

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
                reply = (
                    f"I am building the semantic index for this spreadsheet in the background (dataset size: {row_count} rows). "
                    "Please repeat your request in a few seconds once it is ready."
                )
                yield f"data: {json.dumps({'token': reply})}\n\n"

                session = SessionLocal()
                try:
                    session.add(
                        Message(
                            conversation_id=conversation_id,
                            role=MessageRole.ASSISTANT.value,
                            content=reply,
                        )
                    )
                    session.commit()
                finally:
                    session.close()
                yield "event: done\ndata: {}\n\n"

            return StreamingResponse(
                bg_indexing_stream(), media_type="text/event-stream"
            )

    elif doc.embedding_status == "PROCESSING":

        def waiting_stream():
            yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"
            reply = (
                "The semantic index is currently being built in the background. "
                "Please wait a few moments and try your query again."
            )
            yield f"data: {json.dumps({'token': reply})}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(waiting_stream(), media_type="text/event-stream")

    return None


def _stream_llm_rag_response(
    question: str,
    conversation_id: uuid.UUID,
    conversation_id_str: str,
    user_id: int,
    chunks: List[dict],
    messages: List[tuple],
) -> StreamingResponse:
    """Retrieves token streams from LLM provider, executes matched tools, and commits message sources."""
    provider = get_llm_provider()

    def event_stream():
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': conversation_id_str})}\n\n"

        source_data = []
        for chunk in chunks:
            source_data.append(
                {
                    "text": chunk.get("text"),
                    "source": chunk.get("source"),
                    "page": chunk.get("page"),
                    "type": chunk.get("type", "semantic"),
                }
            )
        yield f"event: sources\ndata: {json.dumps({'sources': source_data})}\n\n"

        full_answer = ""
        try:
            for token in provider.stream(messages):
                full_answer += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as error:
            logger.error(f"LLM streaming exception: {error}")
            err_msg = f"\n\n**Error:** {str(error)}"
            yield f"data: {json.dumps({'token': err_msg})}\n\n"
            yield f"event: error\ndata: {json.dumps({'error': str(error)})}\n\n"
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

        # Pre-initialize variables checked in saving block to prevent NameError issues
        timeline_events = None
        comp_data = None
        graph_data = None
        result = None

        try:
            json_match = re.search(r"\{[\s\S]*\}", clean_answer)

            parsed_tool = None
            if json_match:
                try:
                    parsed_tool = json.loads(json_match.group(0))
                except Exception:
                    pass

            if isinstance(parsed_tool, dict) and parsed_tool.get("type") == "tool":
                is_tool_call = True
                tool_name = parsed_tool.get("tool")
                tool_args = parsed_tool.get("arguments", {})

                db_session = SessionLocal()
                try:
                    result = ToolRouter.execute(
                        tool_name=tool_name,
                        arguments=tool_args,
                        db=db_session,
                        user_id=user_id,
                    )
                    if tool_name == "chart_generator":
                        tool_figure = result.get("figure")
                    elif tool_name == "spreadsheet_query":
                        query_result = result.get("result", "No result returned")
                        synthesis_prompt = [
                            (
                                "system",
                                "You are a helpful data analyst. Convert the raw Pandas query result into a clear, "
                                "concise conversational explanation for the user. Do not explain the code, just state the facts and results.",
                            ),
                            (
                                "human",
                                f"User question: {question}\nRaw Pandas query result:\n{query_result}",
                            ),
                        ]
                        synthesis_response = provider.llm.invoke(synthesis_prompt)
                        synthesized_reply = str(synthesis_response.content).strip()
                        yield f"data: {json.dumps({'token': f'\\n\\n**Analysis Result:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "spreadsheet_export":
                        download_url = result.get("download_url")
                        download_filename = result.get("filename", "exported_data.csv")
                        record_count = result.get("record_count", 0)
                        reply = (
                            f"I have successfully extracted {record_count} structured record(s) based on your request. "
                            f"You can download the file here: [Download {download_filename}]({download_url})"
                        )
                        synthesized_reply = reply
                        yield f"data: {json.dumps({'token': f'\\n\\n{synthesized_reply}'})}\n\n"
                        yield f"event: download\ndata: {json.dumps({'downloadUrl': download_url, 'downloadFilename': download_filename})}\n\n"
                    elif tool_name == "timeline_generator":
                        timeline_events = result.get("events", [])
                        reply = f"I have successfully generated a timeline with {len(timeline_events)} event(s) from the document."
                        synthesized_reply = reply
                        yield f"data: {json.dumps({'token': f'\\n\\n{synthesized_reply}'})}\n\n"
                        yield f"event: timeline\ndata: {json.dumps({'events': timeline_events})}\n\n"
                    elif tool_name == "comparison_generator":
                        comp_data = result.get("comparison_data", {})
                        if "warning" in comp_data:
                            warning_msg = comp_data["warning"]
                            synthesized_reply = warning_msg
                            yield f"data: {json.dumps({'token': f'\\n\\n{warning_msg}'})}\n\n"
                        else:
                            rows_count = len(comp_data.get("rows", []))
                            reply = f"I have successfully generated a side-by-side comparison table with {rows_count} feature(s) compared."
                            synthesized_reply = reply
                            yield f"data: {json.dumps({'token': f'\\n\\n{synthesized_reply}'})}\n\n"
                            yield f"event: comparison\ndata: {json.dumps({'comparison_data': comp_data})}\n\n"
                    elif tool_name == "graph_generator":
                        graph_data = result.get("graph_data", {})
                        elements_count = len(graph_data.get("elements", []))
                        reply = f"I have successfully generated a knowledge graph visualization with {elements_count} element(s)."
                        synthesized_reply = reply
                        yield f"data: {json.dumps({'token': f'\\n\\n{synthesized_reply}'})}\n\n"
                        yield f"event: graph\ndata: {json.dumps({'graph_data': graph_data})}\n\n"
                except Exception as error:
                    logger.error(f"Error executing tool {tool_name}: {str(error)}")
                    tool_error = str(error)
                    if tool_name == "spreadsheet_query":
                        synthesized_reply = (
                            f"Failed to execute spreadsheet query: {str(error)}"
                        )
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "spreadsheet_export":
                        synthesized_reply = (
                            f"Failed to execute spreadsheet export: {str(error)}"
                        )
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "timeline_generator":
                        synthesized_reply = f"Failed to generate timeline: {str(error)}"
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "comparison_generator":
                        synthesized_reply = (
                            f"Failed to generate comparison table: {str(error)}"
                        )
                        yield f"data: {json.dumps({'token': f'\\n\\n**Error:**\\n{synthesized_reply}'})}\n\n"
                    elif tool_name == "graph_generator":
                        synthesized_reply = (
                            f"Failed to generate knowledge graph: {str(error)}"
                        )
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
                    source_data.append({"type": "chart", "figure": tool_figure})
                elif tool_name == "timeline_generator" and timeline_events:
                    content_to_save = (
                        f"Generated timeline with {len(timeline_events)} events."
                    )
                    if not source_data:
                        source_data = []
                    source_data.append({"type": "timeline", "events": timeline_events})
                elif tool_name == "comparison_generator" and comp_data:
                    if "warning" in comp_data:
                        content_to_save = comp_data["warning"]
                    else:
                        content_to_save = f"Generated comparison table with {len(comp_data.get('rows', []))} rows."
                        if not source_data:
                            source_data = []
                        source_data.append(
                            {"type": "comparison", "comparison_data": comp_data}
                        )
                elif tool_name == "graph_generator" and graph_data:
                    content_to_save = f"Generated knowledge graph with {len(graph_data.get('elements', []))} elements."
                    if not source_data:
                        source_data = []
                    source_data.append({"type": "graph", "graph_data": graph_data})
                elif (
                    tool_name in ("spreadsheet_query", "spreadsheet_export")
                    and synthesized_reply
                ):
                    content_to_save = synthesized_reply
                    if (
                        tool_name == "spreadsheet_export"
                        and isinstance(result, dict)
                        and result.get("download_url")
                    ):
                        if not source_data:
                            source_data = []
                        source_data.append(
                            {
                                "type": "download",
                                "downloadUrl": result.get("download_url"),
                                "downloadFilename": result.get(
                                    "filename", "exported_data.csv"
                                ),
                            }
                        )
                else:
                    content_to_save = (
                        f"Failed to execute tool '{tool_name}': {tool_error}"
                    )
                    if tool_name not in (
                        "spreadsheet_query",
                        "spreadsheet_export",
                        "timeline_generator",
                    ):
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


@router.post("/ask")
def ask_question(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
) -> StreamingResponse:
    """Core endpoint for asking questions, retrieving context, executing tools, and streaming replies."""
    if not payload.question or not payload.question.strip():
        raise EmptyQuestionException()

    conversation = _get_or_create_conversation(
        db, current_user, payload.conversation_id
    )

    db_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .all()
    )
    db_messages.reverse()

    history = []
    for message in db_messages:
        role = "human" if message.role == MessageRole.USER.value else "ai"
        history.append((role, message.content))

    # Handle agreement with assistant suggestions
    resolved_question = _resolve_suggestion_agreement(payload.question, history)
    payload.question = resolved_question

    # Log user message
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER.value,
            content=payload.question,
        )
    )

    # Initialize auto-generated title if needed
    _auto_generate_conversation_title(db, conversation, payload.question)

    db.commit()

    conversation_id = conversation.id
    conversation_id_str = str(conversation_id)
    user_id = current_user.id

    documents = (
        db.query(DocumentModel)
        .filter(DocumentModel.user_id == user_id, DocumentModel.deleted_at.is_(None))
        .all()
    )

    intent = classify_intent(payload.question)

    # Scenario 1: User has no documents and query is not a greeting
    if not documents and intent != "greeting":
        return _handle_no_documents_response(conversation_id_str, conversation_id)

    # Scenario 2: Simple metadata query (greetings, file listings, stats)
    if intent != "knowledge_query":
        return _handle_simple_intents_response(
            intent, documents, conversation, conversation_id_str, conversation_id
        )

    # Resolve targeted document from query keywords
    matched_doc = _find_matching_document(documents, payload.question)
    if matched_doc:
        conversation.document_id = matched_doc.id
        db.commit()

    if not conversation.document_id and len(documents) == 1:
        conversation.document_id = documents[0].id
        db.commit()

    # Ambiguity and Export check
    is_ambiguous_doc_query = bool(
        re.search(
            r"\b(this|the|that|my|your|uploaded)?\s*(document|file|pdf|csv|xlsx|excel|spreadsheet|sheet|docx)\b",
            payload.question.lower(),
        )
    )

    is_export_requested = False
    export_keywords = [
        "csv",
        "excel",
        "spreadsheet",
        "export",
        "download csv",
        "make csv",
        "create csv",
        "provide csv",
        "generate csv",
        "give me csv",
        "give csv",
        "provide me csv",
        "tabular",
    ]
    question_lower = payload.question.lower()
    for keyword in export_keywords:
        if keyword in question_lower:
            is_export_requested = True
            break

    # Scenario 3: Multiple documents exist, query references ambiguous 'document'
    if (
        not conversation.document_id
        and len(documents) > 1
        and is_ambiguous_doc_query
        and not is_export_requested
    ):
        return _handle_ambiguous_document_response(
            documents, conversation_id_str, conversation_id
        )

    # Scenario 4: Query requests explicit spreadsheet format export
    if is_export_requested:
        return _handle_csv_export_response(
            payload.question,
            conversation_id,
            conversation_id_str,
            conversation.document_id,
            user_id,
        )

    source_file = None
    document_in_focus = None
    schema_info = None
    active_doc_id = None
    focused_doc = None

    if conversation.document_id:
        for document in documents:
            if document.id == conversation.document_id:
                focused_doc = document
                break

        if focused_doc:
            source_file = focused_doc.stored_filename
            document_in_focus = focused_doc.original_filename
            active_doc_id = str(focused_doc.id)
            schema_info = _extract_schema_info_from_profile(focused_doc)

    # Scenario 5: Check and start lazy indexing of spreadsheet datasets
    if focused_doc:
        lazy_index_response = _handle_lazy_indexing_for_spreadsheet(
            db,
            focused_doc,
            payload.question,
            user_id,
            conversation_id,
            conversation_id_str,
        )
        if lazy_index_response is not None:
            return lazy_index_response

    uploaded_files_list = []
    for document in documents:
        uploaded_files_list.append(document.original_filename)

    is_comprehensive_query = False
    comprehensive_keywords = (
        "list",
        "all",
        "every",
        "who",
        "show",
        "filter",
        "employee",
        "project",
        "summary",
        "directory",
        "table",
        "report",
        "detail",
        "complete",
        "name",
        "item",
        "give me",
        "provide",
        "bring",
        "find all",
        "count",
        "tenure",
        "years",
        "working",
        "department",
        "position",
        "location",
    )
    for keyword in comprehensive_keywords:
        if keyword in question_lower:
            is_comprehensive_query = True
            break

    semantic_limit = 25 if is_comprehensive_query else 10
    top_fused = 25 if is_comprehensive_query else 10

    # Execute RAG Retrieval Pipelines
    semantic_chunks = retrieve_chunks(
        payload.question,
        tenant_id=user_id,
        limit=semantic_limit,
        source_file=source_file,
    )
    graph_facts = graph_search(
        payload.question, tenant_id=user_id, limit=15, source_file=source_file
    )
    chunks = reciprocal_rank_fusion([semantic_chunks, graph_facts], top_n=top_fused)

    context = build_context_block(chunks)
    messages = build_chat_messages(
        context,
        payload.question,
        history=history,
        uploaded_files_list=uploaded_files_list,
        document_in_focus=document_in_focus,
        document_id=active_doc_id,
        schema_info=schema_info,
    )

    # Scenario 6: Standard LLM + RAG Retrieval response stream
    return _stream_llm_rag_response(
        payload.question,
        conversation_id,
        conversation_id_str,
        user_id,
        chunks,
        messages,
    )


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Retrieve all conversations corresponding to the verified tenant user."""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.get(
    "/conversations/{conversation_id}/messages", response_model=List[MessageOut]
)
def get_conversation_messages(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Get the message history of a specific conversation, isolating tenant user access."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
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
    """Delete a conversation, isolating tenant user access."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
        .first()
    )
    if not conversation:
        raise ConversationNotFoundException()

    db.delete(conversation)
    db.commit()
    return {"message": "Conversation deleted successfully"}
