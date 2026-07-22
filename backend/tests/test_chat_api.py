import pytest
import uuid
from fastapi import status
from unittest.mock import patch, MagicMock

def test_empty_question_returns_400(client, auth_headers):
    payload = {"question": "", "conversation_id": None}
    res = client.post("/chat/ask", json=payload, headers=auth_headers)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot be empty" in res.json()["detail"]

def test_invalid_conversation_id_returns_404(client, auth_headers):
    random_uuid = str(uuid.uuid4())
    payload = {"question": "Hello", "conversation_id": random_uuid}
    res = client.post("/chat/ask", json=payload, headers=auth_headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND

@patch("app.api.routes.chat.classify_intent")
@patch("app.api.routes.chat.get_llm_provider")
def test_valid_question_returns_streaming_response(mock_provider, mock_intent, client, auth_headers):
    # Mock intent to greet
    mock_intent.return_value = "greeting"
    
    # Mock LLM response
    mock_llm = MagicMock()
    mock_llm.stream.return_value = ["Hello", " user"]
    mock_provider.return_value = mock_llm
    
    payload = {"question": "hello", "conversation_id": None}
    res = client.post("/chat/ask", json=payload, headers=auth_headers)
    
    assert res.status_code == status.HTTP_200_OK
    assert "text/event-stream" in res.headers["content-type"]
    
    # Read streaming body
    body = b"".join(res.iter_bytes())
    assert b"hello" in body.lower() or b"welcome" in body.lower() or b"conversation" in body.lower()

def test_conversation_crud_operations(client, auth_headers, db_session, test_user):
    from app.models.conversation import Conversation
    # Create conversation manually
    conv = Conversation(user_id=test_user.id, title="Test Topic")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)

    # Get conversation messages should return empty list
    res = client.get(f"/chat/conversations/{conv.id}/messages", headers=auth_headers)
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)

    # Delete conversation
    del_res = client.delete(f"/chat/conversations/{conv.id}", headers=auth_headers)
    assert del_res.status_code == status.HTTP_200_OK
    assert "deleted successfully" in del_res.json()["message"]
