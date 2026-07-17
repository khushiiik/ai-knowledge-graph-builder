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
* **Options Considered**: Fixed-size character splitter, Semantic splitter, Paragraph-based splitter, RecursiveCharacterTextSplitter
* **Chosen Option**: LangChain's `RecursiveCharacterTextSplitter` (chunk size 500, overlap 100).
* **Rationale**: 
  * **Why Recursive/Fixed-size over Paragraph Chunking**: Paragraph chunking splits text solely by structural delimiters (like double newlines `\n\n`). While this preserves paragraph boundaries, it results in highly inconsistent chunk sizes. Some paragraphs are excessively long (exceeding token limits), while others are too short to hold sufficient context. `RecursiveCharacterTextSplitter` provides a hybrid, smart fixed-size approach that splits recursively on a list of characters (`\n\n`, `\n`, ` `, `""`), ensuring chunks remain close to the target size (500 characters) while retaining structural layout and avoiding database storage bloating.
  * **Why Recursive/Fixed-size over Semantic Chunking**: Semantic splitters determine chunk boundaries by calculating sentence-level embeddings and finding points where similarity falls below a threshold. This is computationally expensive, requires calling an embedding model repeatedly for every single sentence boundary during ingestion, increases API/compute latency, and is highly sensitive to similarity threshold settings. Recursive splitting is extremely fast, fully local, and runs in linear time.
  * **Overlap Size Selection (100 characters)**: We chose an overlap of 100 characters (approximately 15-20 words, or a full medium-length sentence). This size is sufficient to preserve context (like pronouns, subjects, or transition words) across boundaries, preventing context fragmentation when parsing dense text documents. It strikes a balance between keeping adjacent context linked and avoiding excessive index inflation or repetitive retrieval results.
* **Trade-offs**: 
  * Relies on heuristic-based splitting rather than true semantic coherence detection.
  * **At Scale (10,000+ users)**: Yes. Simple recursive splitting scales linearly in CPU time and keeps ingestion throughput high.

---

## 7. Embedding Model

* **Decision Title**: Embedding Model Selection
* **Options Considered**: API-based models (e.g. OpenAI `text-embedding-3-small` / `text-embedding-3-large`), Self-hosted models (e.g. HuggingFace sentence-transformers like `all-MiniLM-L6-v2` or `bge-large-en-v1.5`), Online Gemini Embeddings
* **Chosen Option**: Online Gemini Embeddings (`models/gemini-embedding-001`) with 3072 dimensions.
* **Rationale**:
  * **Cost**: Gemini Embeddings offer a highly generous free tier and low pay-as-you-go pricing compared to OpenAI's equivalent API models, significantly reducing operational costs during development and production.
  * **Latency**: Provides extremely low response times (sub-100ms) by utilizing Google's globally optimized, serverless infrastructure.
  * **Quality**: High-quality semantic representations across multiple domains with 3072-dimensional output, providing high vector resolution and precise similarity searches.
  * **Self-hosted vs API**: 
    * *Self-hosted models* (like HuggingFace transformers) require loading massive neural network weights into RAM/VRAM, making our Docker containers heavy (multiple gigabytes of image size) and increasing server cost.
    * *API-based models* (like Gemini) keep the application container extremely lightweight, require zero local GPU hardware, and scale dynamically without compute bottlenecks.
* **Trade-offs**:
  * Requires constant internet connectivity and relies on external API availability and key management.
  * **At Scale (10,000+ users)**: Yes. Utilizing an online API model scales seamlessly without hosting and hardware scaling overhead.

---

## 8. NER / Relationship Extraction

* **Decision Title**: NER & Relation Extraction Strategy
* **Options Considered**: Rule-based / Statistical (spaCy), Fine-tuned Model (e.g. REBEL, SpanMarker), Prompt-based LLM Extraction
* **Chosen Option**: Prompt-based LLM Extraction (structured JSON output via Ollama / Groq).
* **Rationale**:
  * **Rule-based (spaCy)**:
    * *Pros*: Extremely high throughput, sub-millisecond execution, runs completely offline, zero token cost.
    - *Cons*: Extremely rigid. spaCy models are trained on specific pre-defined entity sets (e.g., PERSON, ORG, LOC) and cannot easily adapt to arbitrary open-domain entities. Furthermore, extracting relationships requires building custom dependency parsers or training a second model, which yields poor accuracy for complex, unstructured texts.
  * **Fine-tuned models**:
    * *Pros*: Faster than LLMs and reasonably accurate for standard relations.
    * *Cons*: Lacks schema flexibility. Requires hosting a separate dedicated model, and does not generalize well to general user-uploaded documents with diverse domain vocabulary.
  * **LLM-based extraction**:
    * *Pros*: Maximum flexibility. LLM prompting allows zero-shot extraction of arbitrary entities and open-domain relationships in a single pass. It easily grasps complex semantic contexts and outputs well-structured JSON formats.
    * *Cons*: Higher processing latency and token cost, plus the risk of invalid JSON generation from smaller models.
  * **Justification**: Since the application is an open-domain Knowledge Graph builder, the flexibility to parse any document type (e.g., medical, financial, legal) without custom model training makes LLM-based extraction the most robust choice.
* **Trade-offs**:
  * Slower and more resource-intensive than standard spaCy rule/statistical extraction.
  * **At Scale (10,000+ users)**: Yes. In a high-scale deployment, extraction jobs are offloaded to asynchronous Celery workers running a lightweight LLM pool, keeping the API response times low.

---

## 9. LLM for Generation

* **Decision Title**: LLM Selection for Generation
* **Options Considered**: Cloud APIs (e.g. OpenAI GPT-4o, Anthropic Claude), Local deployment (e.g. Ollama with Llama 3 (8B) or Mixtral (8x7B)), Local Qwen 2.5 (3B)
* **Chosen Option**: Online API deployment via **Groq** running the **Llama 3.3 (70B) model** (`llama-3.3-70b-versatile`), with a fallback/offline developer configuration to local **Ollama** running the **Qwen 2.5 (3B)** model.
* **Rationale**:
  * **GPT-4o (Cloud API)**:
    * *Cost*: High (pay-per-token model, expensive for long conversations or large retrieval inputs).
    * *Context Window*: 128k tokens.
    * *Quality*: State-of-the-art reasoning and synthesis.
    * *Privacy*: Fails our strict tenant isolation guidelines as user-uploaded document contents are sent to external OpenAI servers.
    * *Latency*: Network dependent (typically 1.5 - 3 seconds).
  * **Llama 3.3 (70B) via Groq**:
    * *Cost*: Extremely low pay-per-token API cost compared to GPT-4o or Claude, making it highly feasible for high-frequency extraction and chat cycles.
    * *Context Window*: 128k tokens, allowing large contextual inputs from fused vector and graph databases.
    * *Quality*: Outstanding reasoning and logical capabilities, comparable to GPT-4o, especially when adhering to strict JSON structures for relation extraction.
    * *Privacy*: External API calls via TLS to Groq API.
    * *Latency*: Sub-second response times thanks to Groq's high-speed inference engine (LPU architecture).
  * **Qwen 2.5 (3B) (Self-hosted via Ollama)**:
    * *Cost*: Zero (fully local execution).
    * *Context Window*: 32k tokens.
    * *Quality*: Decent synthesis, but has reduced reasoning/JSON-syntax correctness compared to a 70B model.
    * *Privacy*: 100% private; all prompts and data remain on the local machine (perfect for local development and offline environments).
    * *Latency*: Very fast local CPU/GPU inference with a small memory footprint (~2GB RAM).
  * **Justification**: Groq's Llama 3.3 (70B) serves as the primary high-quality deployment LLM, delivering state-of-the-art reasoning speeds at low API costs, while Ollama with Qwen 2.5 (3B) is supported as a fully offline/private developer alternative.
* **Trade-offs**:
  * Relying on Groq API requires managing API keys and network connectivity.
  * **At Scale (10,000+ users)**: For production setups, Groq API scales automatically to handle concurrent requests without hardware provisioning, while local Ollama remains a development/private deployment feature.

---

## 10. Result Fusion Strategy

* **Decision Title**: Result Fusion (Graph + Vector) Strategy
* **Options Considered**: Reciprocal Rank Fusion (RRF), Simple Concatenation, LLM-based Re-ranker (e.g. Cross-Encoders)
* **Chosen Option**: Reciprocal Rank Fusion (RRF) with constant `k=60`.
* **Rationale**:
  * **Simple Concatenation**:
    * *Pros*: Trivial to implement.
    * *Cons*: Merely merges results from vector search and graph search in arbitrary order. It does not evaluate context relevance, potentially diluting context quality and pushing crucial information out of the LLM's attention window.
  * **LLM-based Re-ranker**:
    * *Pros*: Highest precision in identifying the most relevant chunks.
    * *Cons*: Adds a significant latency penalty (an extra LLM call to score each retrieval candidate) and increases API token costs.
  * **Reciprocal Rank Fusion (RRF)**:
    * *Pros*:
      * *Distribution Independent*: Graph match counts (discrete numbers) and vector similarities (cosine similarities) are on completely different scales. Standard normalization methods fail to combine them. RRF evaluates only the relative ranks of document candidates, bypassing normalization issues.
      - *Parameter Free*: Standardizes on the constant $k=60$, delivering robust performance without needing validation set tuning.
      - *High Performance*: Runs in constant $O(N \log N)$ sorting complexity, introducing negligible latency overhead.
* **Trade-offs**:
  * Evaluates rankings rather than absolute relevance scores.
  * **At Scale (10,000+ users)**: Yes. RRF is computationally efficient and scales to large query loads effortlessly.

---

## 11. Task Queue Choice

* **Decision Title**: Task Queue Framework Selection
* **Options Considered**: Celery + Redis, FastAPI BackgroundTasks, ARQ
* **Chosen Option**: Celery with Redis broker and PostgreSQL backend.
* **Rationale**:
  * **Decoupled Workers**: Offloads heavy text extraction, embedding, and graph ingestion processes from the main API thread, keeping request latencies low.
  * **Reliability**: Supports task persistence, monitoring via Flower, and automatic retries (bind=True, up to 3 retries) on ingestion failures.
* **Trade-offs**:
  * Introduces extra infrastructure dependencies (Celery, Redis broker).
  * **At Scale (10,000+ users)**: Yes. Celery easily scales out horizontally by adding more worker replicas to consume from the task queue.

---

## 12. Tool Dispatch Pattern

* **Decision Title**: Tool Dispatch Pattern Selection
* **Options Considered**: Function calling, ReAct prompting, Custom router
* **Chosen Option**: Custom rule-based router and prompt orchestration.
* **Rationale**:
  * **Predictable Flow**: Bypasses the latency and cost of LLM function-calling loops by executing deterministic ingestion and retrieval pipelines directly.
  * **Performance**: Yields responses instantly with minimal prompt setup overhead.
* **Trade-offs**:
  * Less dynamic in choosing arbitrary execution steps on the fly.
  * **At Scale (10,000+ users)**: Yes. Custom rule-based dispatching scales efficiently and eliminates the risks of LLM tool hallucination.

---

### 13. CSV / Structured Data Ingestion Strategy

* **Decision Title**: Lazy Indexing and Pandas-First Ingestion for Structured Data (CSVs/Excel)
* **Options Considered**: Immediate row-by-row vector embedding, Block-row chunking, Lazy/conditional indexing with Pandas-first execution
* **Chosen Option**: Lazy/conditional indexing and Pandas-first execution (Pandas for deterministic tasks, LLM/Embeddings only for semantic lookup)
* **Rationale**:
  * **Structured vs Unstructured**: CSV/Excel files are structured datasets, not unstructured text paragraphs. Ingesting and embedding every row immediately wastes compute, storage, and API token limits.
  * **Deterministic Operations**: Standard analytical requests (statistics, filters, grouping, row counts) are resolved locally and deterministically using Pandas in Python, requiring zero tokens or embedding calls.
  * **Interactive Visualizations (Plotly)**: Visualizations are generated in-memory using Plotly and serialized directly to JSON format. The figures are streamed using Server-Sent Events (SSE) and stored in the database `sources` column, avoiding local disk writes.
  * **Metadata Profiling on Ingestion**: Upon upload, the backend profiles spreadsheets using Pandas, generating a versioned JSON metadata profile (detailing row/column counts, columns, data types, statistical ranges, text columns, and supported capabilities). This profile is stored directly in a JSONB `dataset_profile` column on the `Document` model.
  * **Asynchronous/Threshold-Based Lazy Indexing**: If a user submits a semantic search query against a spreadsheet, the system evaluates the file's size:
    * If the spreadsheet has **less than 1,000 rows**, lazy indexing runs synchronously in the request thread (completes under 3 seconds).
    * If the spreadsheet has **1,000 or more rows**, it sets the `embedding_status` to `PROCESSING`, triggers `lazy_index_spreadsheet_task` inside Celery to embed and index the long-text columns in row groups of 50 asynchronously, and returns a friendly waiting message to the user.
  * **Robust Executor Validation**: The [spreadsheet_tool.py](file:///c:/Users/KHUSHI/OneDrive/Desktop/brainerhub/Projects/ai_knowledge_graph_builder/backend/app/tools/spreadsheet_tool.py) maps columns case-insensitively to prevent typos from the LLM, and enforces type validation checks (e.g. verifying columns are numeric prior to running math aggregations).
* **Trade-offs**:
  * Triggers background task execution dynamically on the first semantic search.
  * **At Scale (10,000+ users)**: Yes. Eliminates token costs and vector DB index bloating for large sheets that are only queried for charts or metrics.
