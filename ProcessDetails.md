# Insight Weaver: Process Details

This document explains the internal logic of Insight Weaver step by step. It is written as an engineering deep dive for reviewers, recruiters, hackathon judges, and future contributors who want to understand how the system works beneath the UI.

## 1. High-Level System Flow

Insight Weaver is a scientific discovery pipeline. The core idea is to transform unstructured research PDFs into structured evidence that can be searched, reasoned over, visualized, compared, and converted into new hypotheses.

The full flow is:

```text
PDF / arXiv input
    -> scientific parsing
    -> metadata extraction
    -> section-aware chunking
    -> entity extraction
    -> entity relationship mapping
    -> database persistence
    -> optional Neo4j graph sync
    -> optional Chroma vector indexing
    -> GraphRAG search
    -> Gemma/Ollama reasoning
    -> hypotheses, contradictions, landscape insights, graph visualization
```

The important design decision is that the system does not send a raw PDF directly to the model and ask for a generic answer. It first builds a durable local knowledge layer. Gemma is used after evidence has been extracted and organized, which reduces hallucination risk and makes the output easier to inspect.

## 2. Runtime Components

### Frontend

The frontend is a React + Vite app. It provides:

- PDF upload
- paper library
- GraphRAG search console
- graph visualization
- hypothesis generation
- cross-paper analysis
- model status checks

In Docker, the frontend is built into static files and served by Nginx. Nginx also proxies `/api` requests to the backend service, so the browser only needs to talk to one origin.

### Backend

The backend is FastAPI. It exposes routes for:

- paper upload and status
- semantic search and GraphRAG
- knowledge graph export
- Gemma chat/model status
- hypothesis generation
- contradiction detection
- landscape analysis

The backend owns all ingestion, parsing, reasoning, model calls, and persistence.

### Ollama and Gemma

Ollama runs as a separate service. The backend connects to it using `OLLAMA_HOST`. In Docker Compose, that host is:

```text
http://ollama:11434
```

The backend never assumes that a model is already loaded. During startup, it calls the model warmup flow, checks available Ollama tags, chooses the configured Gemma model if present, and records the loaded status.

## 3. Configuration Logic

Configuration lives in `backend/core/config.py`.

The `Settings` class centralizes:

- app name
- API prefix
- CORS origins
- database URL
- Redis/Celery URLs
- Neo4j connection details
- Ollama host
- Gemma model names
- Chroma path
- upload directory

The settings object is cached with `@lru_cache`, which means the application gets one shared configuration object rather than repeatedly parsing environment variables.

The important model settings are:

```python
ollama_host = "http://localhost:11435"
gemma_reasoning_model = "gemma4:e4b"
gemma_light_model = "gemma4:e4b"
```

In Docker, Compose overrides these values:

```yaml
OLLAMA_HOST: http://ollama:11434
GEMMA_REASONING_MODEL: ${OLLAMA_MODEL:-gemma4:e4b}
GEMMA_LIGHT_MODEL: ${OLLAMA_MODEL:-gemma4:e4b}
```

This preserves local development defaults while making service-to-service Docker communication work correctly.

## 4. Application Startup Logic

The FastAPI application is created in `backend/api/main.py`.

Startup happens through a FastAPI lifespan function:

1. Initialize the database.
2. Log whether database initialization succeeded.
3. Start model warmup as a background task.
4. Continue serving routes.

The database initialization creates SQLAlchemy tables from the ORM models. If the database is unavailable, the backend still starts, but DB-dependent routes fail gracefully later. This is intentional because it allows the service to boot far enough for health checks and debugging.

Model warmup is not awaited directly during startup. It is launched with:

```python
asyncio.create_task(start_model_warmup())
```

That means the API server can come online while the model status endpoint reports whether Gemma is still loading, loaded, or failed.

## 5. Model Warmup Logic

Model warmup lives in `backend/core/model_warmup.py`.

The warmup state is stored in a module-level dictionary:

```python
_state = {
    "status": "not_started",
    "model": None,
    "message": "...",
    ...
}
```

The warmup procedure:

1. Read the configured model from settings.
2. Call Ollama `/api/tags`.
3. Collect all installed model names.
4. Prefer the configured model.
5. If the configured model is missing, try known fallbacks:
   - `gemma4:e4b`
   - `gemma4:e2b`
6. If neither is found, accept any installed model whose name starts with `gemma4`.
7. Store the selected model in `_resolved_model`.
8. Mutate the settings object so later `GemmaEngine` instances use the resolved model.
9. Mark the status as `loaded`.

This design avoids a common deployment problem: the backend may be configured for a model tag that is not installed locally. Instead of hard failing immediately, the warmup checks what Ollama actually has and picks the best available Gemma model.

If no Gemma model is found, the model status endpoint returns a failure state and suggests pulling a model.

## 6. Gemma Engine Logic

The model interface lives in `backend/core/gemma_engine.py`.

`GemmaEngine` wraps the Ollama Python client. On construction:

1. It reads settings.
2. It chooses a model name.
3. It creates an `ollama.Client`.
4. It applies timeout and host configuration.

The `generate` method performs model generation with retry logic:

- temperature defaults to `0.25`
- timeout comes from settings
- retries use exponential backoff
- optional `num_predict`, `num_ctx`, and `num_thread` are passed into Ollama options
- `keep_alive` keeps the model loaded for faster repeated calls

The model call is wrapped in Tenacity retry logic:

```python
stop_after_attempt(self.max_retries)
wait_exponential(multiplier=1, min=1, max=8)
```

That means temporary Ollama failures or model loading delays are retried before the route fails.

### Structured JSON Generation

Many scientific workflows need machine-readable outputs, not free-form text. `generate_structured` forces the model into JSON mode by appending:

```text
Respond ONLY with valid JSON. No markdown, no backticks, no preamble.
```

The parser then tries three increasingly forgiving strategies:

1. Parse the response directly as JSON.
2. Strip Markdown code fences and parse again.
3. Extract the first JSON object with a regular expression and parse that.

If all parsing attempts fail, the system raises a controlled error. Several higher-level modules catch that error and return deterministic fallbacks.

## 7. Paper Upload Logic

Paper upload is handled in `backend/api/routes/papers.py`.

The route:

```text
POST /api/v1/papers/upload
```

performs the following:

1. Validate that the uploaded file has a `.pdf` extension.
2. Create the upload directory if needed.
3. Generate a UUID-prefixed filename to avoid collisions.
4. Write the PDF to disk.
5. Create a `Paper` database row with status `pending`.
6. Commit and refresh the row so it has an ID.
7. Choose processing mode:
   - Celery if `paper_processing_mode == "celery"`
   - FastAPI background task otherwise
8. Mark the paper as `processing`.
9. Return the paper ID and task ID.

The default mode is local background processing. That is why the Docker setup does not require Redis/Celery for the primary hackathon workflow.

## 8. Paper Processing Pipeline

The core pipeline is in `backend/tasks/paper_processing.py`.

`process_paper_local` calls:

```python
asyncio.run(_process_paper_async(paper_id))
```

The async pipeline is:

1. Load the paper row from the database.
2. Mark it as `processing`.
3. Parse the PDF or arXiv paper.
4. Extract metadata.
5. Store paper-level fields.
6. Chunk the paper into retrieval units.
7. Store chunks in the database.
8. Extract scientific entities.
9. Normalize and persist entities.
10. Map paper-to-entity mentions.
11. Persist entity relationships.
12. Try to sync to Neo4j.
13. Mark the paper as `completed`.
14. Optionally index vectors in Chroma.

If any unhandled exception occurs:

1. Roll back the current transaction.
2. Mark the paper as `failed`.
3. Commit the failed status.
4. Log the traceback.

This ensures the UI can show a clear processing state instead of hanging forever.

## 9. PDF Parsing Logic

Parsing lives in `backend/ingestion/pdf_parser.py`.

The parser uses a two-stage strategy:

```python
try:
    return self._parse_with_pymupdf(pdf_path)
except Exception:
    return self._parse_with_pdfplumber(pdf_path)
```

This is robust because scientific PDFs vary widely in layout. PyMuPDF gives richer font and layout information, while pdfplumber is a fallback for text extraction.

### 9.1 PyMuPDF Parsing

PyMuPDF parsing is the preferred path.

The parser opens the document:

```python
doc = fitz.open(pdf_path)
```

It records:

- page count
- title
- authors
- section text
- abstract
- references
- parser metadata

### 9.2 Title Detection

The first page is extracted as a structured dictionary:

```python
first_page = doc[0].get_text("dict")
```

The parser walks through:

```text
blocks -> lines -> spans
```

A span is a small piece of text with font size, font name, bounding box, and content. The title heuristic is:

```python
title_span = max(
    spans with text length > 10,
    key = font size
)
```

This works because the title is usually among the largest text spans on the first page. The code also records the title's vertical coordinate (`title_y`) so author candidates can be selected below the title.

### 9.3 Author Detection

Author candidates are selected from first-page spans using:

- font size between 10 and 13
- located below the title
- text length between 3 and 160
- first eight candidates only

The logic is intentionally heuristic. Scientific PDFs do not have a universal author markup standard. This approach captures common academic layouts without requiring external metadata.

### 9.4 Section Detection

The parser has a dictionary of known scientific headers:

```python
known_headers = {
    "abstract": "abstract",
    "introduction": "introduction",
    "related work": "related_work",
    "methods": "methods",
    "results": "results",
    ...
}
```

For every line in every page:

1. Join span text into a line.
2. Find the maximum font size in the line.
3. Check whether any span font contains `bold`.
4. Normalize the line:
   - lowercase
   - strip punctuation
   - remove numeric prefixes such as `1`, `2.1`, `3.4.2`
5. Test whether the normalized line is a known header.
6. Require the line to be short and visually header-like.

The key function is `_is_section_header`.

It returns a canonical section name only when:

- line length is under 80 characters
- normalized header is in `known_headers`
- line is bold or font size is at least 11

When a header is detected, the parser changes the current section. All following lines are appended to that section until another header is found.

### 9.5 Full Text Materialization

Internally, sections are collected as:

```python
dict[str, list[str]]
```

After all pages are processed, each list is joined into a string:

```python
materialized = {
    section: "\n".join(lines).strip()
}
```

Empty sections are discarded.

### 9.6 Abstract Extraction

If a formal `abstract` section is found, it is used directly. Otherwise, the parser falls back to regex extraction:

```python
abstract ... introduction
```

The regex attempts to capture text after the word `abstract` and before `introduction` or `1 introduction`.

### 9.7 Reference Splitting

References are split with a regex that recognizes common citation starts:

- `[1]`
- `[2]`
- `1.`
- `2.`

Very short fragments are ignored. This gives the system a list of reference-like strings without needing a full citation parser.

### 9.8 pdfplumber Fallback

If PyMuPDF fails, pdfplumber extracts plain page text:

1. Open PDF.
2. Extract text from each page.
3. Join pages.
4. Split into non-empty lines.
5. Use the first line as a fallback title.
6. Run a simpler section split.

The fallback cannot use font metadata, so it calls `_is_section_header` with assumed values:

```python
font_size = 12
is_bold = True
```

This makes plain-text section splitting possible even without layout metadata.

### 9.9 arXiv Parsing

For arXiv ingestion:

1. Download the PDF from `https://arxiv.org/pdf/{id}.pdf`.
2. Save it temporarily.
3. Query the arXiv Atom API.
4. Parse title, abstract, authors, and published date.
5. Parse the PDF normally.
6. Override PDF-derived metadata with arXiv metadata when available.

This gives more reliable title and author information for arXiv papers.

## 10. Metadata Extraction Logic

Metadata extraction is in `backend/ingestion/metadata_extractor.py`.

Input:

```python
PaperRawData
```

Output:

```python
{
    "title": ...,
    "authors": ...,
    "abstract": ...,
    "publication_year": ...,
    "doi": ...,
    "raw_text": ...
}
```

The extractor builds a search string from:

- title
- abstract
- parser metadata

It finds the first year matching:

```regex
\b(19|20)\d{2}\b
```

It finds DOI values with:

```regex
10\.\d{4,9}/[-._;()/:A-Z0-9]+
```

Finally, all section text is joined into `raw_text`. This raw text supports landscape search and broader analysis.

## 11. Chunking Logic

Chunking is in `backend/ingestion/chunker.py`.

The purpose of chunking is to turn a long paper into smaller evidence units that can be:

- retrieved
- scored
- embedded
- cited
- passed to Gemma within context limits

### 11.1 Chunk Object

Each chunk stores:

- `section`
- `sub_index`
- `content`
- `importance_score`
- `word_count`

This makes chunks traceable back to their paper section.

### 11.2 Sections Skipped

The chunker skips:

- references
- acknowledgments

These sections often contain citations or administrative text rather than primary scientific claims.

### 11.3 Short and High-Value Sections

Some sections are kept as a single chunk:

- abstract
- future work
- conclusion
- any section under 450 words

This is because these sections are already compact and semantically dense.

### 11.4 Sentence Window Splitting

For longer sections, the default splitter is `_sentence_window_split`.

Steps:

1. Normalize whitespace.
2. Split text into sentences using punctuation boundaries.
3. Set target word count from token budget:

   ```python
   target_words = int(MAX_CHUNK_TOKENS / 1.3)
   ```

   Since one English word is roughly 1.3 tokens, this approximates a 400-token maximum.

4. Accumulate sentences into a current chunk.
5. When adding a sentence would exceed the target, finalize the current chunk.
6. Continue until all sentences are consumed.

This preserves sentence boundaries and avoids slicing scientific claims mid-sentence.

### 11.5 Optional Semantic Splitting

The chunker can optionally use embeddings for semantic splitting.

When enabled:

1. Use spaCy sentencizer to split sentences.
2. Encode each sentence.
3. Compute cosine similarity between adjacent sentence embeddings.
4. Split where similarity drops below `0.6`.

This detects topic shifts. For example, a method paragraph transitioning into an evaluation paragraph may have a lower adjacent-sentence similarity and become a split point.

The current default avoids this heavier path unless explicitly enabled.

### 11.6 Chunk Size Normalization

After splitting, `_normalize_chunk_sizes` enforces size quality:

- If a chunk is still too large, split it in half by words.
- If a chunk is too small, merge it into the previous chunk.

This avoids both oversized model inputs and tiny low-context fragments.

### 11.7 Overlap Logic

Adjacent chunks get overlap using the last two sentences of the previous chunk:

```python
OVERLAP_SENTENCES = 2
```

This prevents boundary loss. If a claim begins at the end of one chunk and is clarified at the start of the next, the retrieval unit still contains enough context.

### 11.8 Importance Scoring

Every chunk gets an importance score.

Base score depends on section:

| Section | Base Score |
| --- | --- |
| abstract | 1.00 |
| results | 0.95 |
| conclusion | 0.90 |
| future_work | 0.88 |
| discussion | 0.75 |
| methods | 0.70 |
| introduction | 0.60 |
| related_work | 0.50 |
| other | 0.40 |

The score gets bonuses for scientific signal:

- `+0.07` for terms like significant, novel, demonstrate, discovered, found that, we show
- `+0.05` if the chunk contains percentages
- `+0.03` for contrast markers like however, in contrast, surprisingly

The final score is capped at `1.0`.

This scoring helps prioritize results, conclusions, and claim-heavy chunks during entity extraction and retrieval.

## 12. Entity Extraction Logic

Entity extraction is in `backend/reasoning/entity_extractor.py`.

The output type is:

```python
EntityExtractionResult(
    entities: dict[str, list[str]],
    relationships: list[dict],
    key_findings: list[str]
)
```

Supported entity types:

- DISEASE
- PROTEIN
- GENE
- CHEMICAL
- METHOD
- PATHWAY
- ORGANISM
- CONCEPT

### 12.1 Chunk Selection for Extraction

The extractor does not run over every chunk equally. It first selects chunks where:

```python
importance_score >= 0.7
```

If no chunks meet that threshold, it chooses the top eight chunks by importance.

This focuses extraction on the most scientifically meaningful parts of a paper: abstract, methods, results, discussion, conclusion.

### 12.2 Optional SciSpaCy Extraction

If `use_scispacy=True`, the extractor loads `en_core_sci_lg`. If the model is unavailable, it falls back to a blank English pipeline with sentence splitting.

For each SciSpaCy entity:

1. Normalize whitespace.
2. Remove plural trailing `s` for longer words.
3. Map SciSpaCy labels into the project entity types.
4. Add the entity into a typed set.
5. Increment frequency counters.

### 12.3 Keyword Entity Extraction

Even without SciSpaCy, the system has a keyword layer. It searches for domain-relevant phrases such as:

- deep learning
- machine learning
- computer vision
- endoscopy
- convolutional neural network
- transformer
- lesion
- cancer
- dataset bias
- generalizability
- real-time deployment
- clinical translation
- privacy
- EHR

Each phrase maps to an entity type. For example:

```text
deep learning -> METHOD
lesion -> DISEASE
dataset bias -> CONCEPT
```

The phrase is converted to a canonical display form, such as:

```text
deep learning -> Deep Learning
ehr -> EHR
```

### 12.4 Acronym and Concept Detection

The extractor also identifies capitalized technical terms and acronyms with regex:

```regex
\b(?:[A-Z][A-Za-z0-9-]{2,}|[A-Z]{2,}(?:-[A-Z0-9]+)?)\b
```

This catches terms such as:

- CNN
- EHR
- BERT
- COVID-19-like patterns
- named datasets or methods

Some generic false positives are ignored:

- TEXT
- TASKS
- JSON
- IEEE
- DOI
- RQ

### 12.5 Entity Ranking

Entities are stored in sets by type, but frequency is tracked with `Counter`.

For each type, entities are sorted by:

1. descending frequency
2. alphabetical name

Only the top 10 per type are retained.

### 12.6 Optional Gemma Refinement

The extractor supports a Gemma refinement mode. When enabled:

1. Candidate entities are serialized as JSON.
2. A prompt asks Gemma to remove false positives, add missed entities, extract typed relationships, and normalize names.
3. Gemma is forced to return valid JSON.
4. If Gemma fails, the deterministic entities are returned.

This gives the system a safe layered design:

```text
heuristics/SciSpaCy first
Gemma refinement second
fallback to deterministic extraction
```

In the current paper-processing path, entity extraction is instantiated with default settings, so deterministic extraction is used unless the code is configured otherwise.

## 13. Database Persistence Logic

The database models are SQLAlchemy ORM objects. During paper processing:

1. Chunks are stored as `Chunk` rows.
2. Extracted entities are stored as `Entity` rows.
3. Paper/entity mentions are stored as `PaperEntity`.
4. Relationships are stored as `EntityRelationship`.

### 13.1 Entity Deduplication

Before creating entities, the system builds keys:

```python
(entity_type, normalized_name)
```

It queries existing entities with those keys. If an entity already exists:

- reuse it
- increment `paper_count`

If it does not exist:

- create a new entity
- store normalized name
- store entity type

This prevents duplicates like:

```text
Deep Learning
deep learning
Deep learning
```

from becoming separate concepts.

### 13.2 Paper-to-Entity Mapping

For every extracted entity in a paper, the system creates or merges a `PaperEntity` row:

```text
paper_id -> entity_id -> frequency
```

Frequency comes from the extraction counter.

This is the first level of the graph: a paper mentions an entity.

### 13.3 Relationship Persistence

Relationships are normalized through `RelationshipMapper`.

Allowed relationship labels:

- treats
- inhibits
- activates
- correlates_with
- causes
- similar_to
- contradicts
- part_of

If a relationship label is not recognized, it defaults to:

```text
correlates_with
```

This prevents uncontrolled relationship vocabulary from damaging graph quality.

## 14. Graph Building Logic

Graph logic exists in two layers:

1. SQL database graph fallback
2. Optional Neo4j graph sync/export

This is important: the app can still display graph data even if Neo4j is not running, because graph routes fall back to the SQL tables.

## 15. Neo4j Graph Builder

Neo4j integration lives in `backend/graph/graph_builder.py`.

The graph has two main node labels:

- `Paper`
- `Entity`

The graph has two main relationship forms:

- `(Paper)-[:MENTIONS]->(Entity)`
- `(Entity)-[:RELATES_TO]->(Entity)`

### 15.1 Neo4j Connection

On initialization:

1. Read Neo4j settings.
2. Create a Neo4j driver.
3. Verify connectivity.
4. Run setup queries.

If connectivity fails, the builder raises:

```python
RuntimeError("Neo4j unreachable")
```

The API graph routes catch this and fall back to SQL graph reconstruction.

### 15.2 Constraints and Indexes

The setup creates:

```cypher
CREATE CONSTRAINT entity_name IF NOT EXISTS
FOR (e:Entity) REQUIRE e.name IS UNIQUE
```

```cypher
CREATE CONSTRAINT paper_id IF NOT EXISTS
FOR (p:Paper) REQUIRE p.id IS UNIQUE
```

```cypher
CREATE INDEX entity_type_idx IF NOT EXISTS
FOR (e:Entity) ON (e.type)
```

These protect graph consistency:

- one node per entity name
- one node per paper ID
- faster filtering by entity type

### 15.3 Paper Upsert

Paper nodes are inserted with Cypher `MERGE`:

```cypher
MERGE (p:Paper {id: $paper_id})
SET p.title=$title, p.year=$year, p.arxiv_id=$arxiv_id
```

`MERGE` means:

- create if missing
- update if already present

This makes processing idempotent. Re-running graph sync for a paper updates the same node instead of creating duplicates.

### 15.4 Entity Upsert

Entities are also inserted with `MERGE`:

```cypher
MERGE (e:Entity {name: $name})
ON CREATE SET e.type=$entity_type, e.mention_count=1
ON MATCH SET e.mention_count = coalesce(e.mention_count, 0) + 1
```

The entity name is the unique key. On create, the node gets a type and mention count. On match, mention count increments.

This captures how often a concept appears across processed papers.

### 15.5 Paper Mentions Entity

The paper-to-entity edge is:

```cypher
MATCH (p:Paper {id: $paper_id})
MATCH (e:Entity {name: $entity_name})
MERGE (p)-[r:MENTIONS]->(e)
SET r.frequency=$frequency
```

The edge means:

```text
This paper discusses this scientific entity.
```

The frequency property tells the frontend and retrieval layers how strongly the paper is associated with that entity.

### 15.6 Entity Relates to Entity

Entity relationships are inserted as:

```cypher
MATCH (a:Entity {name: $source})
MATCH (b:Entity {name: $target})
MERGE (a)-[r:RELATES_TO {type: $rel_type, paper_id: $paper_id}]->(b)
SET r.confidence=$confidence, r.evidence=$evidence
```

The relationship stores:

- relationship type
- source entity
- target entity
- confidence
- evidence sentence
- paper ID

The `paper_id` on the relationship is crucial. It keeps the graph grounded in a paper instead of becoming a free-floating concept map.

### 15.7 Batch Graph Sync

`sync_paper` is the main graph sync method. It batches work using `UNWIND`.

The sync flow is:

1. Merge the paper node.
2. If entities exist:
   - unwind entity list
   - merge each entity
   - increment mention count
3. Link paper to every entity with `MENTIONS`.
4. If relationships exist:
   - unwind relationship list
   - match source and target entities
   - merge `RELATES_TO` edge
   - set confidence and evidence

Using `UNWIND` is more efficient than running one database query per entity.

### 15.8 Entity Neighborhood Query

The graph can retrieve a local concept neighborhood:

```cypher
MATCH path = (start:Entity {name: $entity_name})-[*1..2]-(neighbor)
RETURN path LIMIT 100
```

This means:

- start from a selected entity
- traverse any relationship direction
- include paths one or two hops away
- limit to 100 paths

The result is converted into frontend graph JSON with:

- nodes
- edges
- labels
- types
- confidence
- paper IDs

### 15.9 Cross-Paper Paths

The graph can search for paths between two entities:

```cypher
MATCH path = (a:Entity {name: $entity_a})-[*1..4]-(b:Entity {name: $entity_b})
WHERE ALL(r IN relationships(path) WHERE r.paper_id IS NOT NULL)
```

The `WHERE` condition requires every relationship in the path to be grounded in a paper. This avoids speculative paths.

Returned values include:

- papers involved
- entity chain
- hop length

This supports discovery-style questions such as:

```text
How might method A connect to disease B across papers?
```

## 16. SQL Graph Fallback Logic

Graph routes live in `backend/api/routes/graph.py`.

The route first tries Neo4j:

```python
graph = _builder().export_graph_json(...)
```

If Neo4j is unavailable or returns no nodes, the route reconstructs a graph from SQL tables.

This fallback is especially important in the Docker hackathon deployment, where Neo4j is not required by default.

### 16.1 Paper Graph Fallback

For a paper graph:

1. Load the paper row.
2. Query entities mentioned by that paper.
3. Create one paper node.
4. Create one entity node per extracted entity.
5. Create `MENTIONS` edges from paper to entity.

The node IDs are synthetic:

```text
paper-{paper.id}
entity-{entity.id}
```

This makes frontend rendering independent of Neo4j element IDs.

### 16.2 Entity Graph Fallback

For an entity graph:

1. Normalize the search term.
2. Find matching entities by exact or partial name.
3. Add seed entity nodes.
4. Find papers that mention those entities.
5. Add paper nodes and `MENTIONS` edges.
6. Find relationships connected to seed entities.
7. Add neighboring entity nodes.
8. Add relationship edges.
9. Add co-mentioned entities from the same papers.

This creates a useful local graph even without a dedicated graph database.

### 16.3 Why Both Graph Modes Matter

Neo4j is better for deep path traversal and graph-native queries. SQL fallback is better for lightweight deployment and hackathon demos. Insight Weaver supports both:

```text
Neo4j available -> graph database mode
Neo4j unavailable -> SQL reconstruction mode
```

That makes the project deployable on simple Docker setups while still having a path to production-grade graph infrastructure.

## 17. Vector Store Logic

Vector storage is in `backend/retrieval/vector_store.py`.

The system uses ChromaDB with persistent local storage:

```python
chromadb.PersistentClient(path=settings.chroma_path)
```

The collection is:

```text
scientific_chunks
```

with cosine distance:

```python
metadata={"hnsw:space": "cosine"}
```

### 17.1 Embedding Model

The embedding model is:

```text
all-MiniLM-L6-v2
```

It is loaded through sentence-transformers and cached with `@lru_cache`.

### 17.2 Adding Chunks

Chunks are indexed in batches of 32.

For each batch:

1. Generate stable IDs:

   ```text
   p{paper_id}_{section}_{sub_index}
   ```

2. Encode chunk content with normalized embeddings.
3. Build metadata:
   - paper ID
   - title
   - section
   - importance score
   - year
   - authors
   - arXiv ID
4. Upsert into Chroma.

`upsert` allows re-indexing without duplicating records.

### 17.3 Searching

Search flow:

1. Encode query.
2. Apply optional filters:
   - paper ID
   - section
3. Query Chroma.
4. Convert distance to similarity:

   ```python
   similarity_score = 1.0 - distance
   ```

5. Filter by minimum importance.
6. Sort by similarity.

### 17.4 Cross-Paper Similarity

For unexplored connections, the vector store searches for chunks similar to a source chunk while excluding the source paper:

```python
where={"paper_id": {"$nin": exclude_paper_ids}}
```

Only results above a similarity threshold are retained.

This is how the system finds papers that may discuss similar concepts without being manually linked.

## 18. GraphRAG Logic

GraphRAG is in `backend/retrieval/graph_rag.py`.

The goal is to answer research questions using both text evidence and graph context.

The main flow:

1. Search database chunks lexically.
2. Optionally merge vector search results.
3. Build graph context from entities and relationships.
4. Boost retrieval using entity terms.
5. Build a fast extractive answer.
6. Optionally ask Gemma to summarize the evidence.
7. Return answer, model name, warnings, retrieved chunks, graph context, and timing.

### 18.1 Database Chunk Search

The database search extracts query terms by:

- splitting on non-word characters
- lowercasing
- removing short terms
- removing common stopwords
- keeping up to eight terms

It queries chunks whose content contains any of those terms:

```python
Chunk.content.ilike(f"%{term}%")
```

Results are ordered by chunk importance and then rescored with lexical relevance.

If term search returns nothing, the system falls back to important chunks instead of returning nothing immediately.

### 18.2 Lexical Score

The lexical score considers:

- query term coverage
- hit count
- base score

Formula:

```python
min(1.0, 0.25 + coverage * 0.55 + min(hits, 10) * 0.03)
```

Chunk importance contributes additional score:

```python
importance_score * 0.15
```

This balances text match with scientific section importance.

### 18.3 Merging Vector Results

If Chroma is available, vector search is run and merged with database results.

If vector search fails, a warning is added and database retrieval is still used.

The merge keeps the highest score per chunk ID and sorts by score.

### 18.4 Graph Context Construction

Graph context is built from:

- candidate paper IDs
- entities mentioned in those papers
- entities matching query terms
- relationships connected to those entities
- co-mentions if explicit relationships are sparse

The result has:

```python
{
    "entities": [...],
    "relationships": [...],
    "papers": [...]
}
```

### 18.5 Entity Filtering

GraphRAG filters noisy entities with rules:

- ignore empty names
- ignore very short names
- ignore pure punctuation/digits
- ignore generic stopwords
- ignore overly long names
- require at least one alphabetic token
- prefer stronger scientific entity types

This is necessary because PDF-derived text and heuristic NER can produce noisy tokens.

### 18.6 Relationship Facts

Explicit relationships are loaded from `EntityRelationship`.

Each relationship becomes a `GraphFact`:

```python
source
relationship
target
confidence
evidence
paper_id
kind = "explicit"
```

If explicit relationships are limited, co-mentions are generated.

### 18.7 Co-Mention Facts

Co-mentions are weaker graph facts created when two valid entities occur in the same paper.

The score increases with:

- entity frequencies
- entity strength
- scientific type quality

Co-mentions are labeled:

```text
co_mentioned_with
```

They are useful for discovery, but the UI and answer explain that these are weaker than explicit extracted relationships.

### 18.8 Entity-Based Retrieval Boosting

After graph context is created, the system extracts important terms from entity names. If those terms appear in retrieved chunks, the chunks get a small score bonus.

This lets graph context influence retrieval ordering without replacing the original evidence ranking.

### 18.9 Fast Extractive Answer

The fast answer is deterministic. It includes:

- key finding
- evidence strength
- important concepts
- best evidence list
- graph grounding
- next checks

It uses top-scoring sentences and excerpts from retrieved chunks. This means users get an answer even if Gemma is slow or disabled.

### 18.10 Gemma Summary Layer

If `use_gemma=True`, the deterministic answer, top evidence, and graph relationships are passed to Gemma.

The prompt asks for:

- key finding
- evidence
- graph signal
- limitations
- next experiment

Rules enforce that Gemma uses only supplied evidence and includes uncertainty when evidence is weak.

If Gemma fails or times out, the system returns the fast GraphRAG answer and adds a warning.

## 19. Hypothesis Generation Logic

Hypothesis generation is in `backend/core/hypothesis_generator.py`.

The route calls:

```text
POST /api/v1/hypothesis/generate
```

The generator performs:

1. Retrieve relevant chunks.
2. Identify knowledge gaps.
3. Find cross-paper connections.
4. Prepare graph context.
5. Build a Gemma context object.
6. Ask Gemma for structured hypotheses.
7. Validate generated hypotheses.
8. Store valid hypotheses.
9. Return hypotheses and meta-insights.

### 19.1 Retrieval for Hypotheses

If paper IDs are selected, the system searches each selected paper and merges results. Otherwise it searches all indexed evidence.

If vector store is unavailable, retrieval returns an empty list and the fallback pathway activates.

### 19.2 Gap Detection

The generator uses two levels of gap detection:

1. Heuristic gaps from retrieved text.
2. Gemma gap extraction if not in fast fallback mode.

Heuristic examples:

- if text mentions bias/generalizability, gap is external validation
- if text mentions real-time/latency, gap is deployment validation
- if text mentions federated/privacy, gap is privacy-preserving multi-center training
- if text mentions dataset, gap is dataset diversity and annotation consistency

This gives useful outputs even without model calls.

### 19.3 Gemma Hypothesis Prompt

`GemmaEngine.generate_hypothesis` builds a strict scientific prompt. It includes:

- research query
- retrieved evidence
- graph entities
- graph relationships
- identified knowledge gaps
- cross-domain connections
- requested number of hypotheses

The output must be valid JSON with:

- hypothesis statement
- reasoning
- supporting evidence
- confidence
- novelty score
- testability
- suggested experiments
- falsifiable conditions
- research gaps addressed
- cross-domain insight

This structure makes the generated idea auditable.

### 19.4 Validation and Storage

Generated hypotheses are filtered:

```python
confidence > 0.3
supporting_evidence exists
```

Then sorted by:

```python
confidence * novelty_score
```

This prioritizes hypotheses that are both plausible and interesting.

Valid hypotheses are stored in the database with:

- text
- reasoning
- confidence
- novelty
- testability
- supporting paper IDs
- supporting evidence
- suggested experiments
- research gaps
- cross-domain insights
- query context

### 19.5 Deterministic Fallback Hypotheses

If Gemma fails, no evidence is retrieved, or fast fallback is requested, the system returns conservative deterministic hypotheses.

The fallback focuses on:

- multi-center validation
- dataset bias
- clinical deployment
- privacy-preserving training
- latency/workflow metrics

This protects the user experience from model failures while still keeping outputs grounded in likely research gaps.

## 20. Contradiction Detection Logic

Contradiction analysis is in `backend/reasoning/cross_paper_reasoner.py`.

The route:

```text
POST /api/v1/analysis/contradictions
```

requires at least two paper IDs.

Flow:

1. For each paper, retrieve top chunks related to the topic.
2. For every pair of selected papers, compare their retrieved text.
3. If either side lacks text, return an insufficient data result.
4. Otherwise ask Gemma to detect contradiction.
5. Store high-severity contradictions in the database.

Gemma is asked to identify:

- whether contradiction exists
- severity
- contradiction type
- paper A claim
- paper B claim
- explanation
- resolution suggestion

If the model errors, the system returns a model-error verdict rather than crashing.

## 21. Cross-Paper Connection Logic

Cross-paper connection discovery looks for similar evidence across different papers.

Flow:

1. Load the top five high-importance chunks for a source paper.
2. For each chunk, search the vector store for similar chunks from other papers.
3. Exclude the source paper.
4. Keep the best connection per target paper.
5. Sort by connection score.
6. Return top ten.

Each returned connection includes:

- source paper ID
- target paper ID
- target paper title
- similarity score
- source excerpt
- target excerpt
- shared concepts placeholder

This feature helps surface papers that may belong in the same reasoning chain even if the user did not manually connect them.

## 22. Research Landscape Logic

Landscape analysis:

1. Finds papers whose raw text contains the topic.
2. Computes year range from publication years.
3. Asks Gemma for:
   - key milestones
   - paradigm shifts
   - open questions
   - trending direction
4. Falls back to deterministic output if Gemma fails.

The logic is intentionally lightweight but useful for giving a topic-level overview.

## 23. Frontend Logic

The main frontend file is `frontend/src/main.jsx`.

Important frontend concepts:

- `API_BASE` defaults to `http://127.0.0.1:8000/api/v1`.
- In Docker, the build argument sets it to `/api/v1`.
- `useApi` wraps fetch into `get`, `post`, and `upload`.
- Uploads use `FormData`.
- Model status is refreshed from `/agents/model-status`.
- Papers are loaded from `/papers/?limit=100&offset=0`.
- The UI stores simple user/theme state in `localStorage`.

The frontend deliberately keeps API behavior simple and leaves scientific logic in the backend.

## 24. Docker and Deployment Logic

Docker Compose runs:

- `ollama`
- `ollama-pull`
- `backend`
- `frontend`
- `public-tunnel`

### 24.1 Ollama Service

Ollama exposes port `11434` and stores models in a persistent Docker volume:

```yaml
ollama-models:/root/.ollama
```

This prevents the Gemma model from being downloaded again every time containers restart.

### 24.2 Model Pull Service

`ollama-pull` runs:

```text
ollama pull ${OLLAMA_MODEL:-gemma4:e4b}
```

The backend depends on this service completing successfully. That prevents the backend from starting too early and reporting model-missing errors during normal Compose startup.

### 24.3 Backend Service

The backend:

- builds from `backend/Dockerfile`
- exposes port `8000`
- points `OLLAMA_HOST` to the Ollama container
- uses SQLite inside `/app/data`
- stores uploads in `/app/uploads`
- persists both directories as Docker volumes

SQLite is used for easy deployment. The code also includes PostgreSQL-related dependencies and naming, but the current Compose deployment is intentionally lightweight.

### 24.4 Frontend Service

The frontend:

- builds React with Vite
- serves static output through Nginx
- proxies `/api` to the backend
- exposes port `8080`
- sets `client_max_body_size 200m` to support larger PDF uploads

### 24.5 Public Tunnel

The public tunnel uses Cloudflare `cloudflared`:

```text
cloudflared tunnel --no-autoupdate --url http://frontend:80
```

This creates a temporary public HTTPS URL. It is suitable for demos. It is not a production SLA endpoint. For production, a named tunnel or cloud-hosted deployment should be used.

## 25. Error Handling Philosophy

Insight Weaver is designed to degrade gracefully:

- If PyMuPDF fails, use pdfplumber.
- If Neo4j fails, use SQL graph fallback.
- If vector search fails, use database retrieval.
- If Gemma fails, return deterministic fallback answers.
- If JSON parsing fails, retry with stricter prompting or fallback.
- If paper processing fails, mark the paper as failed instead of hanging.

This is important in real research tooling because PDFs, models, local machines, and network calls are all unreliable.

## 26. Why the Graph Matters

The graph is the most important architectural idea in the project.

A normal RAG system retrieves text chunks and asks a model to answer. Insight Weaver adds another layer:

```text
papers -> entities -> relationships -> graph context -> answer/hypothesis
```

This allows the system to reason over:

- which papers mention the same scientific concepts
- which methods relate to which diseases or outcomes
- which entities co-occur across papers
- which relationships have explicit evidence
- which paths connect ideas across the literature

The graph turns isolated documents into a connected research landscape.

## 27. Example End-to-End Trace

Suppose a user uploads a paper about deep learning for lesion detection.

1. The PDF is saved with a UUID filename.
2. A `Paper` row is created.
3. PyMuPDF extracts title, authors, sections, and page text.
4. Metadata extractor finds publication year and DOI if present.
5. Chunker splits methods/results/discussion into evidence chunks.
6. Chunks receive importance scores.
7. Entity extractor finds entities such as:
   - Deep Learning
   - Endoscopy
   - Lesion
   - Dataset Bias
   - Clinical Translation
8. Entities are deduplicated by normalized name and type.
9. Paper/entity mention rows are created.
10. Relationships are normalized and persisted if extracted.
11. Neo4j sync is attempted.
12. If Neo4j is unavailable, SQL graph tables still support graph views.
13. User asks a GraphRAG question.
14. System retrieves chunks matching the query.
15. System builds graph context from entities and relationships.
16. Fast answer is generated from evidence.
17. Gemma optionally summarizes the evidence and suggests next experiments.
18. User can generate hypotheses grounded in the retrieved evidence and graph context.

## 28. Limitations and Engineering Notes

Current limitations:

- PDF parsing is heuristic and may miss complex multi-column structures.
- Entity extraction defaults to deterministic keyword/acronym extraction unless SciSpaCy/Gemma refinement is enabled.
- Relationship extraction is conservative in the default path.
- Neo4j is optional and not part of the lightweight Compose deployment.
- Vector indexing is controlled by `index_vectors_during_processing`; if disabled, GraphRAG still works through database retrieval.
- Cloudflare quick tunnels are temporary demo links.

These are reasonable hackathon tradeoffs. The architecture already leaves clear upgrade paths for stronger production extraction, named tunnels, hosted databases, and graph-native deployment.

## 29. Summary

Insight Weaver solves a real research bottleneck by transforming papers into a structured, inspectable, model-assisted discovery system.

The core innovation is not simply using Gemma. The innovation is how Gemma is placed inside a pipeline:

```text
parse -> chunk -> extract -> graph -> retrieve -> reason -> hypothesize
```

That architecture makes the output more grounded, more explainable, and more useful for real scientific workflows.

