from typing import List, Tuple

SYSTEM_TEMPLATE = (
    "You are a helpful assistant. Answer the user's question using the context "
    "below, which was retrieved from their uploaded documents.\n"
    "The user has the following documents uploaded in their workspace: {uploaded_files_list}\n"
    "Current document in focus: {document_in_focus}\n\n"
    "If the answer isn't in the context or documents list, say \"I don't have information about that.\"\n\n"
    "Context:\n{context}"
)


def build_chat_messages(
    context: str,
    question: str,
    uploaded_files_list: List[str] = None,
    document_in_focus: str = None
) -> List[Tuple[str, str]]:
    """Builds a (role, content) message list ready to hand to the LLM."""
    files_str = ", ".join(uploaded_files_list) if uploaded_files_list else "None"
    focus_str = document_in_focus if document_in_focus else "All documents"

    return [
        (
            "system",
            SYSTEM_TEMPLATE.format(
                context=context or "No relevant context found.",
                uploaded_files_list=files_str,
                document_in_focus=focus_str,
            ),
        ),
        ("human", question),
    ]
