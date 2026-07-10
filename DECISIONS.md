# Architecture Decision Records (ADR)

This file documents the major technical decisions made in the AI Knowledge Graph Builder project, detailing the options considered, choices made, rationales, and trade-offs.

---

## 1. Backend Web Framework

* **Decision Title**: Backend Web Framework Selection
* **Options Considered**: Flask, Django, FastAPI
* **Chosen Option**: FastAPI
* **Rationale**: 
  * **Performance & Async**: FastAPI has native support for asynchronous programming (`async/await`), which is crucial for handling concurrent I/O-bound operations (such as making API calls to LLMs and databases).
  * **Auto-generated Docs**: Automatically generates interactive OpenAPI docs (`/docs` and `/redoc`) from Pydantic types, reducing documentation overhead.
  * **Developer Experience**: Leverages Pydantic for request validation, settings configuration, and serialization, ensuring strong typing and type checking.
* **Trade-offs**: 
  * FastAPI is a micro-framework, meaning it does not provide an out-of-the-box admin panel or ORM (like Django). We must manually configure database connections and migration tools.
  * **At Scale (10,000+ users)**: Yes, would keep the same choice. FastAPI handles high concurrency efficiently with low resource footprint.

---

## 2. Relational Database (Structured Metadata)

* **Decision Title**: Relational Database for Metadata Storage
* **Options Considered**: SQLite, MySQL, PostgreSQL
* **Chosen Option**: PostgreSQL (v16)
* **Rationale**:
  * **Data Integrity**: Offers robust ACID compliance, transaction safety, and support for complex relational schemas.
  * **Extensibility**: Features powerful extensions (like PostGIS or pgvector) should we need vector operations or geospatial tracking in the future.
  * **Production Standard**: Widely supported by Python libraries (`psycopg2`, `SQLAlchemy`) and orchestration pipelines.
* **Trade-offs**:
  * Higher resource footprint and operational complexity compared to SQLite.
  * **At Scale (10,000+ users)**: Yes, PostgreSQL is highly scalable and handles millions of rows effortlessly with proper indexing.

---

## 3. Graph Database (Knowledge Graph Network)

* **Decision Title**: Graph Database Selection
* **Options Considered**: ArangoDB, Amazon Neptune, Neo4j
* **Chosen Option**: Neo4j (v5 Community)
* **Rationale**:
  * **Cypher Query Language**: Cypher is the industry-standard query language for graphs, making it much easier to write entity traversal queries.
  * **Maturity**: Well-maintained Python driver, extensive documentation, and native APOC plugin support for complex graph algorithms.
  * **Query Latency**: Highly optimized for index-free adjacency graph traversals compared to multi-model databases like ArangoDB.
* **Trade-offs**:
  * The Community edition has limitations regarding multi-database clustering.
  * Neo4j can be RAM-intensive, requiring JVM heap tuning.
  * **At Scale (10,000+ users)**: Yes. For a system at scale, we would shift to the Neo4j Enterprise edition or cloud hosted AuraDB, but the codebase and queries would remain the same.

---

## 4. Vector Database (Similarity Search)

* **Decision Title**: Vector Database Selection
* **Options Considered**: pgvector, Milvus, Qdrant
* **Chosen Option**: Qdrant (Latest)
* **Rationale**:
  * **Pure Vector DB performance**: Written in Rust, highly performant, and has a very small memory footprint compared to Milvus.
  * **Rich Filtering**: Supports payload filtering, allowing us to combine vector queries with structured metadata filtering in a single request.
  * **Usability**: Offers a very intuitive Python client (`qdrant-client`) and built-in health endpoints out of the box.
* **Trade-offs**:
  * Operating Qdrant as a separate service introduces another component to maintain (compared to using `pgvector` inside Postgres).
  * **At Scale (10,000+ users)**: Yes, Qdrant scales horizontally with a distributed cluster setup, making it ideal for large-scale operations.

---

## 5. Caching & Message Broker

* **Decision Title**: Cache and Message Broker Selection
* **Options Considered**: RabbitMQ, Redis
* **Chosen Option**: Redis (v7)
* **Rationale**:
  * **Versatility**: Redis functions as an in-memory key-value cache, a message broker, and a database, all in one package.
  * **Performance**: Sub-millisecond latency for quick configuration caching or rate-limiting data.
  * **Low Overhead**: Extremely simple setup, highly compatible with Python task queues.
* **Trade-offs**:
  * Redis holds all data in RAM; if memory runs out, it evicts keys or crashes unless configured with persistency rules.
  * **At Scale (10,000+ users)**: Yes, Redis Cluster easily handles millions of operations per second.

---

## 6. Chunking Strategy

* **Decision Title**: Chunking Strategy Selection
* **Options Considered**: Fixed-size window chunking, Semantic chunking
* **Chosen Option**: *Pending Implementation*
* **Rationale**: This feature is not yet present in the active codebase. 
* **Trade-offs**: N/A

---

## 7. Embedding Model

* **Decision Title**: Embedding Model Selection
* **Options Considered**: API-based models (e.g. OpenAI `text-embedding-3-small`), Self-hosted models (e.g. HuggingFace sentence-transformers)
* **Chosen Option**: *Pending Implementation*
* **Rationale**: This feature is not yet present in the active codebase.
* **Trade-offs**: N/A

---

## 8. NER / Relationship Extraction

* **Decision Title**: NER & Relation Extraction Strategy
* **Options Considered**: spaCy, Fine-tuned LLM, Prompt-based LLM Extraction
* **Chosen Option**: *Pending Implementation*
* **Rationale**: This feature is not yet present in the active codebase.
* **Trade-offs**: N/A

---

## 9. LLM for Generation

* **Decision Title**: LLM Selection for Generation
* **Options Considered**: Cloud API (e.g. OpenAI GPT-4o, Anthropic Claude), Local deployment (e.g. Ollama, Llama 3, Qwen 2.5)
* **Chosen Option**: Local deployment via **Ollama** running the **Qwen 2.5 (3B)** model.
* **Rationale**:
  * **Data Privacy & Isolation**: Keeps all user prompts and knowledge graph data local, ensuring compliance with our strict tenant isolation strategies.
  * **No API Costs**: Eliminates pay-per-token API fees, allowing infinite loops of development, testing, and retrieval generation.
  * **Highly Lightweight**: The 3B parameter model has a low memory footprint (approx. 2.0 GB VRAM/RAM), making it viable to run concurrently with Qdrant, Neo4j, and Postgres on standard development hardware.
* **Trade-offs**:
  * **Cognitive Capacity**: A 3B model has reduced reasoning power, syntax correctness, and long-context performance compared to a 7B, 14B, or GPT-4o level model.
  * **At Scale (10,000+ users)**: For 10,000+ users, we would deploy a scalable inference server like vLLM on dedicated GPU cloud nodes, or switch to a private deployment of a larger model (e.g., Qwen 72B). For our current local deployment, Docker-managed Ollama is the best choice.

---

## 10. Result Fusion Strategy

* **Decision Title**: Result Fusion (Graph + Vector) Strategy
* **Options Considered**: Reciprocal Rank Fusion (RRF), Weighted Merge, Re-ranker
* **Chosen Option**: *Pending Implementation*
* **Rationale**: This feature is not yet present in the active codebase.
* **Trade-offs**: N/A

---

## 11. Task Queue Choice

* **Decision Title**: Task Queue Framework Selection
* **Options Considered**: Celery + Redis, FastAPI BackgroundTasks, ARQ
* **Chosen Option**: *Pending Implementation* (Redis is provisioned in the orchestration layer, but the Python backend framework implementation is pending)
* **Rationale**: This feature is not yet present in the active codebase.
* **Trade-offs**: N/A

---

## 12. Tool Dispatch Pattern

* **Decision Title**: Tool Dispatch Pattern Selection
* **Options Considered**: Function calling, ReAct prompting, Custom router
* **Chosen Option**: *Pending Implementation*
* **Rationale**: This feature is not yet present in the active codebase.
* **Trade-offs**: N/A
