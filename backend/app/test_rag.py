import requests
import time

BASE_URL = "http://localhost:8001"

def test_rag_flow():
    print("--- STARTING RAG FLOW INTEGRATION TEST ---")
    
    # 1. Register a new unique test user
    email = f"raguser_{int(time.time())}@example.com"
    password = "testpassword"
    print(f"Registering user: {email}...")
    
    res = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "full_name": "RAG Test User",
        "password": password
    })
    assert res.status_code == 201, f"Register failed: {res.text}"
    print("User registered successfully.")

    # 2. Login to get the Bearer Token
    print("Logging in...")
    res = requests.post(f"{BASE_URL}/auth/token", json={
        "email": email,
        "password": password
    })
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful. Token obtained.")

    # 3. Create a unique content text file
    file_content = "Antigravity is a premium AI coding assistant designed and created by the Google DeepMind team."
    filename = "assistant_info.txt"
    with open(filename, "w") as f:
        f.write(file_content)
    print(f"Created file: {filename} with content: '{file_content}'")

    # 4. Upload file (triggers Qdrant indexing)
    print("Uploading file to trigger RAG indexing...")
    with open(filename, "rb") as f:
        res = requests.post(
            f"{BASE_URL}/documents/upload",
            headers=headers,
            files={"file": (filename, f, "text/plain")}
        )
    
    if res.status_code != 201:
        print(f"Upload failed: {res.text}")
        return

    doc_data = res.json()
    print("Upload and Indexing completed. Document details:")
    print(f"  ID: {doc_data['id']}")
    print(f"  Status: {doc_data['status']}")
    print(f"  Checksum: {doc_data['checksum']}")
    
    # 5. Query /chat/ask (should retrieve the facts from Qdrant and answer)
    question = "Who designed and created the Antigravity assistant?"
    print(f"Asking LLM: '{question}'...")
    
    import json
    res = requests.post(f"{BASE_URL}/chat/ask", headers=headers, json={
        "question": question
    }, stream=True)
    
    assert res.status_code == 200, f"Chat failed: {res.text}"
    print("\n--- LLM ANSWER (STREAMING) ---")
    for line in res.iter_lines():
        if line:
            decoded_line = line.decode("utf-8")
            if decoded_line.startswith("data: "):
                try:
                    data = json.loads(decoded_line[6:])
                    if "token" in data:
                        print(data["token"], end="", flush=True)
                except Exception:
                    pass
    print("\n------------------------------\n")

if __name__ == "__main__":
    test_rag_flow()
