# Insight Weaver Process Logic

This document explains the current corrected pipeline after the professional sprint fixes. It focuses on what was broken, what was changed, and how each major subsystem now works.

## 1. Core Design Principle

Insight Weaver is designed as a scientific evidence system, not a generic PDF chatbot.

```text
PDF
  -> clean scientific text
  -> section-aware chunks
  -> scientific entities
  -> relationships and graph context
  -> hybrid retrieval
  -> Gemma reasoning
  -> hypotheses, contradictions, and research insights
```

The model is intentionally placed near the end of the pipeline. Earlier stages are deterministic and inspectable so the user can trace answers back to paper sections, chunks, entities, and graph edges.

## 2. Public Workspace Isolation

The frontend creates a private anonymous workspace for each browser session.

### Frontend Logic

`frontend/src/main.jsx` stores a UUID in `sessionStorage` under:

```text
iw_workspace_id
```

Every request made by the API wrapper sends:

```http
X-Workspace-ID: <workspace uuid>
```

This applies to uploads, paper lists, graph requests, GraphRAG, hypotheses, analysis, and reset.

### Backend Logic

`backend/api/dependencies.py` validates `X-Workspace-ID`.

Rules:

- Header is required for user-data routes.
- Value must look like a UUID.
- Any submitted `paper_id` must belong to the current workspace.
- If a paper or hypothesis belongs to another workspace, the API returns `403` or `404`.

### Data Scope

The following models now carry `workspace_id`:

- `Paper`
- `Entity`
- `Hypothesis`
- `Contradiction`

Chunks inherit workspace through their parent paper. Paper-entity links and relationships are filtered through workspace-owned entities and papers.

### Reset Logic

`DELETE /api/v1/workspace/current` deletes:

- papers
- chunks through paper cascade
- entities
- paper-entity links
- entity relationships
- hypotheses
- contradictions
- uploaded files
- Chroma vector records for the workspace

This is what guarantees that public users do not see each other's data.

## 3. PDF Parsing Logic

PDF parsing lives in `backend/ingestion/pdf_parser.py`.

### Previous Issue

The parser selected the largest font span as title. On real papers, that can be a journal logo, header, arXiv label, or section title. Author extraction also captured affiliations, departments, and emails.

### Current Logic

The parser now builds first-page line blocks with:

- text
- max font size
- bold flag
- vertical position

Title detection uses multiple signals:

- must be in the top area of the first page
- must have reasonable length
- must not be all-caps journal/header text
- must not contain email, DOI, arXiv, preprint metadata, or year-only text
- must not match known section headers
- highest font size wins only after these filters

Author detection uses:

- first-page author zone
- font size range typical for author names
- exclusion of affiliations, departments, universities, hospitals, emails, and correspondence text
- splitting on commas, semicolons, and `and`
- deduplication while preserving order

### Section Detection

Section headings are normalized by:

- lowercasing
- stripping punctuation
- removing numeric prefixes such as `1`, `2.1`, `3.4.2`
- removing Roman numeral prefixes such as `II.`

The expanded vocabulary recognizes method, results, future-work, and limitation variants. It also skips references, appendices, funding, acknowledgements, supplementary material, conflicts, and author contributions.

## 4. Scientific Text Cleaning

Text cleaning lives in `backend/preprocessing/cleaner.py`.

### Previous Issue

Raw PDF text contained ligatures, broken hyphenation, citation markers, table rows, formula spacing artifacts, repeated headers, and single newlines from layout extraction. These artifacts damaged chunking, embeddings, entity extraction, and Gemma prompts.

### Current Logic

`ScientificTextCleaner.clean(text, mode)` supports two modes:

```text
standard   -> chunking and embedding
aggressive -> entity extraction and Gemma prompts
```

Standard mode:

- normalizes Unicode with NFKC
- replaces ligatures such as `fi`, `fl`, `ffi`
- reconstructs hyphenated line breaks such as `multi-\ncenter`
- removes running headers and page numbers
- fixes formula spacing like `0 . 05`
- replaces citations with `[CITE]`
- converts single newlines into spaces
- normalizes repeated spaces

Aggressive mode additionally:

- removes numeric table-like rows
- removes citation placeholders
- removes short parenthetical asides

## 5. Sentence Splitting and Chunking

Sentence splitting lives in `backend/preprocessing/splitter.py`. Chunking lives in `backend/ingestion/chunker.py`.

### Previous Issue

Naive punctuation splitting broke scientific text:

- `et al.`
- `Fig. 3`
- `Dr. Smith`
- decimals such as `p < 0.05`
- abbreviations and initials

Broken splitting caused overlap fragments and poor retrieval chunks.

### Current Logic

The splitter scans punctuation boundaries and rejects false boundaries if the preceding token is a scientific abbreviation, a digit, or a single initial.

Chunks are packed around sentence boundaries with approximately 220 words per chunk. This is intentionally lower than generic text because scientific text has a higher token-to-word ratio.

Chunk importance still uses section and claim signals:

- abstracts, results, conclusions, and future work score higher
- percentages and statistically significant language add bonus
- contrast markers such as `however` and `in contrast` add signal

The result is cleaner evidence for retrieval and Gemma context.

## 6. Entity Extraction Logic

Entity extraction lives in `backend/reasoning/entity_extractor.py`.

### Previous Issue

The system depended heavily on a small keyword table and broad uppercase regex. That produced either too few entities or noisy entities like section names and generic words.

### Current Logic

The extractor now runs pattern NER after aggressive cleaning.

Supported pattern groups:

- proteins and genes: `BRCA1`, `TP53`, `EGFR`, kinase/receptor/protein phrases
- diseases: `Alzheimer disease`, `gastric cancer`, `COVID-19`, `COPD`
- chemicals: common drug suffixes such as `mab`, `nib`, `mycin`, `stat`, `vir`
- methods: `deep learning`, `graph neural network`, `BERT`, `ViT`, `ResNet`, `UNet`, classifiers
- datasets: `ImageNet`, `COCO`, `MIMIC`, `TCGA`, `GEO`, dataset/cohort/benchmark phrases

Entity validation removes:

- stopwords
- section words
- generic paper words
- pure numbers or punctuation
- overly long phrases

Deduplication uses a canonical key:

```text
lowercase + remove spaces + remove hyphens + remove underscores
```

So names such as:

```text
BRCA-1
BRCA1
brca1
```

collapse into one concept.

SciSpaCy output is merged when available, but deterministic pattern NER is enough to produce meaningful graph nodes for demo use.

## 7. Entity Persistence Logic

Entities are stored per workspace.

The database still has a uniqueness constraint on:

```text
normalized_name + entity_type
```

To avoid collisions between public visitors, the internal `normalized_name` is prefixed with the workspace ID:

```text
<workspace_id>:<canonical_entity_key>
```

The display name remains clean for the UI. This approach avoids a risky SQLite table rebuild while still ensuring entity isolation.

## 8. Graph Building Logic

Graph data is represented in SQL through:

- `Paper`
- `Entity`
- `PaperEntity`
- `EntityRelationship`

### Paper to Entity

When an entity is extracted from a paper, a `PaperEntity` row records:

- paper ID
- entity ID
- frequency

This means:

```text
Paper --MENTIONS--> Entity
```

### Entity to Entity

If relationships are extracted or mapped, `EntityRelationship` stores:

- source entity ID
- target entity ID
- relationship type
- confidence
- evidence text
- paper ID

This means:

```text
Entity --relationship_type--> Entity
```

### SQL Graph Fallback

Neo4j is optional. If Neo4j is unavailable, the graph route reconstructs the graph from SQL.

The corrected fallback now returns both:

- paper-to-entity mention edges
- entity-to-entity relationship edges

This fixes the earlier issue where fallback graphs showed only star-shaped mention graphs and lost real scientific relationships.

## 9. Vector Store Logic

Vector storage lives in `backend/retrieval/vector_store.py`.

Chroma metadata now includes:

```text
workspace_id
paper_id
title
section
importance_score
year
authors
arxiv_id
```

Search filters by workspace. This prevents vector search from leaking another visitor's chunks.

The vector store can also be created without loading the embedding model:

```python
VectorStore(load_model=False)
```

This is used by workspace reset so deleting vectors does not load a large embedding model unnecessarily.

## 10. GraphRAG Retrieval Logic

GraphRAG lives in `backend/retrieval/graph_rag.py`.

### Previous Issue

Database chunks and vector chunks used different IDs:

```text
DB: integer Chunk.id
Chroma: p{paper_id}_{section}_{sub_index}
```

Deduplication failed and repeated chunks entered the context.

### Current Merge Logic

Both DB and vector results use:

```text
Chunk.chroma_embedding_id
```

as the canonical chunk identity. If both retrieval paths find the same chunk, GraphRAG keeps one merged result with the stronger score.

### BM25-Style Candidate Scoring

Instead of scanning text with broad `iLIKE '%term%'`, GraphRAG:

1. fetches high-importance candidate chunks for the workspace
2. extracts meaningful query terms
3. scores candidates in Python with BM25-style term frequency
4. blends BM25, chunk importance, and lexical coverage

This produces more relevant evidence without heavy database-specific full-text search setup.

### Graph Context

Graph context is built from:

- papers in the retrieval set
- entities mentioned in those papers
- entities matching query terms
- explicit relationships connected to those entities
- co-mentions only as weak fallback signals

The answer includes retrieved evidence, key entities, relationships, and caveats.

## 11. Hypothesis Generation Logic

Hypothesis generation lives in `backend/core/hypothesis_generator.py`.

### Previous Issue

Generic fallback hypotheses dominated outputs when Gemma was slow or failed. These sounded plausible but were not specific to the uploaded papers.

### Current Logic

The generator now builds context from:

- raw retrieved chunks
- extracted entities from selected papers
- identified knowledge gaps
- cross-paper connections
- graph context

Gemma receives direct evidence, not only a pre-made summary.

If Gemma is skipped or fails, fallback hypotheses are generated from actual entities:

- disease + method
- protein/gene + chemical
- method + dataset
- retrieved claim sentence

This means fallback output can mention entities such as:

```text
BRCA1
TP53
Alzheimer disease
deep learning
ImageNet
```

instead of generic phrases like "multi-center validation is needed" for every paper.

## 12. Contradiction and Cross-Paper Reasoning

Cross-paper reasoning lives in `backend/reasoning/cross_paper_reasoner.py`.

All analysis is workspace-scoped.

Contradiction flow:

1. Validate selected papers belong to the workspace.
2. Retrieve topic-related chunks per paper.
3. Compare each paper pair.
4. Ask Gemma for contradiction verdict when evidence exists.
5. Store high-severity contradictions with workspace ID.

Connection flow:

1. Load high-importance chunks for the source paper.
2. Search for similar chunks in the same workspace, excluding the source paper.
3. Return the strongest target-paper connection.

Landscape flow:

1. Search only workspace papers.
2. Summarize milestones, open questions, paradigm shifts, and trending direction.

## 13. Frontend Logic

The frontend is a research workspace with:

- upload panel
- library
- GraphRAG console
- graph explorer
- hypothesis generation
- cross-paper analysis
- model status
- reset workspace action

The API wrapper centralizes:

- JSON requests
- uploads
- delete requests
- workspace header injection

This keeps the workspace isolation rule consistent across all UI panels.

## 14. Docker and Deployment Logic

Docker Compose runs:

- `ollama`
- `ollama-pull`
- `backend`
- `frontend`
- `public-tunnel`

### Health Gates

Startup is health-gated:

- Ollama must be healthy.
- Model pull must complete.
- Backend must be healthy.
- Frontend must be healthy.
- Public tunnel starts after frontend is healthy.

The backend health endpoint reports:

- database status
- Ollama status
- installed model names
- whether a Gemma model is ready

## 15. Current Fixed Issues Summary

| Fixed Issue | Current Behavior |
| --- | --- |
| PDF text artifacts polluted downstream logic | Cleaner runs before chunking, extraction, and prompts |
| Naive sentence splitting damaged chunks | Scientific splitter protects abbreviations and decimals |
| Title extraction selected logos/headers | Multi-signal first-page title detection |
| Author extraction selected affiliations | Author-zone and affiliation filtering |
| Section detection missed variants | Expanded section vocabulary and numbered prefix normalization |
| Entity extraction produced tiny/noisy graphs | Pattern NER produces richer scientific entities |
| Entity collisions across users | Workspace-scoped normalized names |
| Graph fallback lost relationships | SQL fallback includes entity relationship edges |
| GraphRAG duplicate chunks | Canonical `chroma_embedding_id` merge |
| Broad lexical scans | BM25-style candidate reranking |
| Generic hypotheses | Entity and evidence grounded fallback |
| Public visitors saw shared data | Anonymous workspace isolation |
| Reset was heavy | Chroma deletion can run without loading embedding model |
| Docker startup race | Compose health dependencies and enhanced `/health` |

## 16. Practical Demo Expectations

For a strong demo:

1. Start Docker Compose.
2. Confirm `/health` is ok.
3. Upload one or more papers.
4. Wait for processing to complete.
5. Open graph view and verify 10+ meaningful entities for rich papers.
6. Ask a GraphRAG question.
7. Generate hypotheses and confirm they mention paper-specific entities.
8. Open a second browser session and verify it starts with an empty workspace.
9. Use Reset Workspace before handing the app to another reviewer.

## 17. Engineering Tradeoffs

The current implementation intentionally keeps:

- SQLite for easy local deployment
- Neo4j optional
- Celery optional
- deterministic fallbacks for model failures
- Cloudflare quick tunnel for demos

This keeps the hackathon deployment practical while preserving a clean path to production upgrades.
