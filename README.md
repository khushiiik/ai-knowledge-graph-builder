# AI Knowledge Graph Builder Scaffolding

This project provides a pre-configured boilerplate scaffolding for building an AI-powered Knowledge Graph application. It integrates relational data storage, graph networks, vector embeddings, caching, and a FastAPI-based backend.

## Project Structure

```text
ai-knowledge-graph-builder/
├── docker-compose.yml       # Orchestrates postgres, neo4j, qdrant, redis, & backend
├── .env.example             # Configuration templates
├── README.md                # Project documentation and guidelines
└── backend/
    ├── Dockerfile           # Backend container definition
    ├── requirements.txt     # Python dependencies
    └── app/
        ├── main.py          # FastAPI application server with service health checks
        └── config.py        # Settings configuration loader (Pydantic Settings)
```

## Technologies & Ports

| Service | Technology | Internal Port | External Port | Purpose |
|---|---|---|---|---|
| **backend** | FastAPI (Python) | 8000 | 8000 | Core REST API backend application |
| **postgres** | PostgreSQL 16 | 5432 | 5432 | Relational structured metadata storage |
| **neo4j** | Neo4j 5 (Community) | 7474, 7687 | 7474, 7687 | Graph network storage for entities and relations |
| **qdrant** | Qdrant Vector DB | 6333, 6334 | 6333, 6334 | Vector similarity search engine for text embeddings |
| **redis** | Redis 7 | 6379 | 6379 | In-memory cache and task/message broker |

---

## Quick Start (Docker Compose)

### 1. Copy Environment Settings
Clone/download this project and duplicate `.env.example` into a new `.env` file in the root directory:
```bash
cp .env.example .env
```

### 2. Launch Services
Run the following command to build and launch all containers:
```bash
docker compose up --build
```
This command builds the backend application and pulls/starts all database services. The backend will wait for all database containers to report healthy before starting.

### 3. Verify Health Check
Open your browser or run a API query to verify that the backend is running and communicating properly with all database services:
* **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **System Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

A successful query to `/health` should return:
```json
{
  "status": "healthy",
  "services": {
    "postgres": {
      "status": "healthy",
      "version": "PostgreSQL 16..."
    },
    "neo4j": {
      "status": "healthy"
    },
    "qdrant": {
      "status": "healthy",
      "collections_count": 0
    },
    "redis": {
      "status": "healthy"
    }
  }
}
```

---

## Local Development (Without Docker Compose)

If you prefer to run only the databases via Docker, and execute the backend code directly on your local system:

### 1. Start Databases Only
```bash
docker compose up postgres neo4j qdrant redis
```

### 2. Configure Local .env
Create `.env` using localhost values (refer to `.env.example`). Since the databases are exposed on host ports, the default connections in `config.py` should map automatically.

### 3. Setup Backend Environment
Create a virtual environment and install requirements:
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 4. Run Backend Server
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Visit [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) to confirm your local server connects successfully to the running containers.
