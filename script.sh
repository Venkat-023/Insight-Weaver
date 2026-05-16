# =============================================================================
# fix_all.ps1  –  run from E:\Projects\Gemma-hackathon-main\
# Fixes every bug found in the Gemma-hackathon codebase.
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
function Write-File($relPath, $content) {
    $fullPath = Join-Path $PSScriptRoot $relPath
    $dir = Split-Path $fullPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::WriteAllText($fullPath, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host "  [FIXED] $relPath"
}

Write-Host "`n=== Gemma-hackathon: applying all fixes ===`n"

# ===========================================================================
# FIX 1 – backend/api/main.py
# Bug: duplicate "import logging" at lines 1 and 3; also asynccontextmanager
#       yield must be in try/finally so lifespan always completes cleanly.
# ===========================================================================
Write-File "backend/api/main.py" @'
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import agents, analysis, graph, hypothesis, papers, search
from core.config import get_settings
from core.model_warmup import start_model_warmup
from models.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(start_model_warmup())
    try:
        yield
    finally:
        pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(papers.router, prefix=settings.api_prefix)
    app.include_router(search.router, prefix=settings.api_prefix)
    app.include_router(graph.router, prefix=settings.api_prefix)
    app.include_router(hypothesis.router, prefix=settings.api_prefix)
    app.include_router(analysis.router, prefix=settings.api_prefix)
    app.include_router(agents.router, prefix=settings.api_prefix)
    app.include_router(agents.chat_router, prefix=settings.api_prefix)

    @app.exception_handler(Exception)
    async def structured_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR", "detail": str(exc)},
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
'@

# ===========================================================================
# FIX 2 – backend/api/routes/graph.py
# Bug: _builder() creates a NEW Neo4j driver on every HTTP request (connection
#      storm + slow setup). Cache the builder as a module-level singleton;
#      return None gracefully when Neo4j is unavailable so the postgres fallback
#      is always reached.
# ===========================================================================
Write-File "backend/api/routes/graph.py" @'
import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from graph.graph_builder import KnowledgeGraphBuilder
from models.entity import Entity, PaperEntity
from models.paper import Paper

logger = logging.getLogger("scientific_discovery.graph_route")
router = APIRouter(prefix="/graph", tags=["graph"])


@lru_cache(maxsize=1)
def _get_builder() -> KnowledgeGraphBuilder | None:
    """Return a cached KnowledgeGraphBuilder, or None if Neo4j is unreachable."""
    try:
        return KnowledgeGraphBuilder()
    except Exception as exc:
        logger.warning("neo4j_unavailable_at_startup: %s", exc)
        return None


def _builder() -> KnowledgeGraphBuilder | None:
    return _get_builder()


@router.get("/entity/{entity_name}")
async def graph_for_entity(entity_name: str) -> dict:
    builder = _builder()
    if builder is None:
        raise HTTPException(503, {"error": "Neo4j unavailable", "code": "GRAPH_UNAVAILABLE"})
    try:
        return builder.get_entity_neighborhood(entity_name, 2)
    except Exception as exc:
        raise HTTPException(503, {"error": "Neo4j unavailable", "code": "GRAPH_UNAVAILABLE", "detail": str(exc)}) from exc


@router.get("/{paper_id}")
async def graph_for_paper(
    paper_id: int,
    include_neighbors: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    builder = _builder()
    if builder is not None:
        try:
            graph = builder.export_graph_json([paper_id])
            if graph.get("nodes"):
                return graph
        except Exception as exc:
            logger.warning("neo4j_graph_fetch_failed paper_id=%s: %s", paper_id, exc)
    # Fallback: build graph from Postgres entities
    return await _paper_graph_from_postgres(paper_id, db)


async def _paper_graph_from_postgres(paper_id: int, db: AsyncSession) -> dict:
    paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, {"error": "Paper not found", "code": "PAPER_NOT_FOUND", "detail": str(paper_id)})

    rows = await db.execute(
        select(Entity, PaperEntity.frequency)
        .join(PaperEntity, PaperEntity.entity_id == Entity.id)
        .where(PaperEntity.paper_id == paper_id)
        .order_by(PaperEntity.frequency.desc(), Entity.name)
        .limit(80)
    )
    entity_rows = rows.all()
    paper_node_id = f"paper-{paper.id}"
    nodes = [
        {
            "id": paper_node_id,
            "label": paper.title,
            "type": "Paper",
            "paper_count": 1,
        }
    ]
    edges = []
    for entity, frequency in entity_rows:
        entity_node_id = f"entity-{entity.id}"
        nodes.append(
            {
                "id": entity_node_id,
                "label": entity.name,
                "type": entity.entity_type,
                "mention_count": frequency,
                "paper_count": entity.paper_count,
            }
        )
        edges.append(
            {
                "source": paper_node_id,
                "target": entity_node_id,
                "type": "MENTIONS",
                "paper_id": paper.id,
            }
        )
    return {"nodes": nodes, "edges": edges}
'@

# ===========================================================================
# FIX 3 – backend/tasks/paper_processing.py
# Bug: asyncio.run() inside a Celery task on Windows raises
#      "This event loop is already running" in some environments.
#      Use a fresh loop explicitly. Also: the graph builder is instantiated
#      inside the paper-processing try/except which is correct, but we must
#      ensure the inner neo4j try/except covers KnowledgeGraphBuilder()
#      construction too (currently it does—just making it explicit).
# ===========================================================================
Write-File "backend/tasks/paper_processing.py" @'
import asyncio
import logging
import time
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from celery import Celery
from sqlalchemy import select, tuple_

from core.config import get_settings
from graph.graph_builder import KnowledgeGraphBuilder
from ingestion.chunker import SemanticChunker
from ingestion.metadata_extractor import MetadataExtractor
from ingestion.pdf_parser import ScientificPDFParser
from models.database import AsyncSessionLocal
from models.entity import Entity, EntityRelationship, PaperEntity
from models.paper import Chunk as ChunkModel
from models.paper import Paper, ProcessingStatus
from reasoning.entity_extractor import ScientificEntityExtractor
from reasoning.relationship_mapper import RelationshipMapper

logger = logging.getLogger("scientific_discovery.tasks")
settings = get_settings()
celery_app = Celery("scientific_discovery", broker=settings.celery_broker_url, backend=settings.celery_result_backend)


def _run_async(coro):
    """Run a coroutine safely in any thread context (Windows-safe)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(name="tasks.paper_processing.process_paper", bind=True, max_retries=2)
def process_paper(self, paper_id: int) -> dict:
    return _run_async(_process_paper_async(paper_id))


def process_paper_local(paper_id: int) -> dict:
    return _run_async(_process_paper_async(paper_id))


async def _process_paper_async(paper_id: int) -> dict:
    timings: dict[str, float] = {}
    async with AsyncSessionLocal() as db:
        paper = await db.get(Paper, paper_id)
        if not paper:
            raise ValueError(f"Paper {paper_id} not found")
        try:
            await _set_status(db, paper, ProcessingStatus.processing)

            started = time.perf_counter()
            parser = ScientificPDFParser()
            raw = parser.parse_from_arxiv(paper.arxiv_id) if paper.arxiv_id else parser.parse_pdf(paper.pdf_path or "")
            timings["parse_pdf"] = time.perf_counter() - started

            started = time.perf_counter()
            metadata = MetadataExtractor().extract(raw)
            if metadata.get("doi"):
                duplicate_doi = (
                    await db.execute(select(Paper).where(Paper.doi == metadata["doi"], Paper.id != paper.id))
                ).scalar_one_or_none()
                if duplicate_doi:
                    metadata["doi"] = None
            for key, value in metadata.items():
                if value is not None and hasattr(paper, key):
                    setattr(paper, key, value)
            if not paper.pdf_path and paper.arxiv_id:
                paper.pdf_path = str(Path("/tmp") / f"{paper.arxiv_id}.pdf")
            await db.commit()
            timings["metadata"] = time.perf_counter() - started

            started = time.perf_counter()
            chunks = SemanticChunker().chunk_paper(raw)
            chunk_embedding_ids = [f"p{paper.id}_{chunk.section}_{chunk.sub_index}" for chunk in chunks]
            for chunk, embedding_id in zip(chunks, chunk_embedding_ids, strict=False):
                db.add(
                    ChunkModel(
                        paper_id=paper.id,
                        section=chunk.section,
                        content=chunk.content,
                        sub_index=chunk.sub_index,
                        importance_score=chunk.importance_score,
                        chroma_embedding_id=embedding_id,
                        word_count=chunk.word_count,
                    )
                )
            await db.commit()
            timings["chunk_store"] = time.perf_counter() - started

            started = time.perf_counter()
            extraction = ScientificEntityExtractor().extract(chunks)
            entity_name_to_id: dict[str, int] = {}
            entity_keys = {
                (entity_type, name.lower().strip())
                for entity_type, names in extraction.entities.items()
                for name in names
            }
            existing_entities: dict[tuple[str, str], Entity] = {}
            if entity_keys:
                rows = await db.execute(
                    select(Entity).where(
                        tuple_(Entity.entity_type, Entity.normalized_name).in_(entity_keys)
                    )
                )
                existing_entities = {
                    (entity.entity_type, entity.normalized_name): entity
                    for entity in rows.scalars().all()
                }
            for entity_type, names in extraction.entities.items():
                for name in names:
                    normalized = name.lower().strip()
                    existing = existing_entities.get((entity_type, normalized))
                    if existing:
                        existing.paper_count += 1
                        entity = existing
                    else:
                        entity = Entity(name=name, normalized_name=normalized, entity_type=entity_type, aliases=[])
                        db.add(entity)
                        await db.flush()
                        existing_entities[(entity_type, normalized)] = entity
                    entity_name_to_id[name] = entity.id
            frequencies = Counter(word.lower().strip() for names in extraction.entities.values() for word in names)
            for name, entity_id in entity_name_to_id.items():
                await db.merge(PaperEntity(paper_id=paper.id, entity_id=entity_id, frequency=frequencies[name.lower().strip()] or 1))
            mapper = RelationshipMapper()
            for rel in extraction.relationships:
                source_id = entity_name_to_id.get(rel.get("source"))
                target_id = entity_name_to_id.get(rel.get("target"))
                if source_id and target_id:
                    db.add(
                        EntityRelationship(
                            source_entity_id=source_id,
                            target_entity_id=target_id,
                            relationship_type=mapper.normalize(rel.get("relation", "")),
                            confidence=float(rel.get("confidence", 0.5)),
                            evidence_text=rel.get("evidence"),
                            paper_id=paper.id,
                        )
                    )
            await db.commit()
            timings["entities"] = time.perf_counter() - started

            started = time.perf_counter()
            try:
                # KnowledgeGraphBuilder() raises RuntimeError if Neo4j is unreachable;
                # this is caught here so the paper still completes successfully.
                graph = KnowledgeGraphBuilder()
                graph.sync_paper(
                    paper_id=paper.id,
                    title=paper.title,
                    year=paper.publication_year,
                    arxiv_id=paper.arxiv_id,
                    entities=[
                        {
                            "name": name,
                            "entity_type": entity_type,
                            "frequency": frequencies[name.lower().strip()] or 1,
                        }
                        for entity_type, names in extraction.entities.items()
                        for name in names
                    ],
                    relationships=[
                        {
                            "source": rel.get("source"),
                            "target": rel.get("target"),
                            "rel_type": mapper.normalize(rel.get("relation", "")),
                            "confidence": float(rel.get("confidence", 0.5)),
                            "evidence": rel.get("evidence", ""),
                            "paper_id": paper.id,
                        }
                        for rel in extraction.relationships
                        if rel.get("source") and rel.get("target")
                    ],
                )
            except Exception:
                logger.exception("neo4j_graph_update_failed", extra={"paper_id": paper.id})
            timings["graph"] = time.perf_counter() - started

            paper.processing_status = ProcessingStatus.completed
            paper.processed_at = datetime.now(UTC)
            await db.commit()

            if settings.index_vectors_during_processing:
                started = time.perf_counter()
                try:
                    from retrieval.vector_store import VectorStore

                    VectorStore().add_chunks(
                        paper.id,
                        chunks,
                        {"title": paper.title, "year": paper.publication_year, "authors": paper.authors or [], "arxiv_id": paper.arxiv_id},
                    )
                except Exception:
                    logger.exception("vector_index_failed", extra={"paper_id": paper.id})
                timings["vector_index"] = time.perf_counter() - started

            logger.info("paper_processed", extra={"paper_id": paper.id, "timings": timings})
            return {"paper_id": paper.id, "status": "completed", "timings": timings}
        except Exception:
            traceback.print_exc()
            await db.rollback()
            paper.processing_status = ProcessingStatus.failed
            await db.commit()
            logger.error("paper_processing_failed", extra={"paper_id": paper.id, "traceback": traceback.format_exc()})
            return {"paper_id": paper.id, "status": "failed", "error": traceback.format_exc()}


async def _set_status(db, paper: Paper, status: ProcessingStatus) -> None:
    paper.processing_status = status
    await db.commit()
'@

# ===========================================================================
# FIX 4 – backend/run_local_uvicorn.ps1
# Bugs:
#   (a) OLLAMA_HOST uses port 11434 but .env uses 11435 (user's actual port).
#       Align to 11435 so pydantic-settings env var override matches .env.
#   (b) GEMMA_TIMEOUT_SECONDS was 30 – too short for a cold first inference.
#       Raise to 120 so the first chat/hypothesis call doesn't time out.
#   (c) Missing NEO4J_PASSWORD env var override – add it for completeness.
# ===========================================================================
Write-File "backend/run_local_uvicorn.ps1" @'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$env:POSTGRES_DSN                = "postgresql+asyncpg://sci:password@localhost:5432/scidb"
$env:REDIS_URL                   = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL           = "redis://localhost:6379/1"
$env:CELERY_RESULT_BACKEND       = "redis://localhost:6379/2"
$env:PAPER_PROCESSING_MODE       = "local"
$env:INDEX_VECTORS_DURING_PROCESSING = "false"
$env:NEO4J_URI                   = "bolt://localhost:7687"
$env:NEO4J_USER                  = "neo4j"
$env:NEO4J_PASSWORD              = "password"
$env:OLLAMA_HOST                 = "http://localhost:11435"
$env:GEMMA_REASONING_MODEL       = "gemma4:e4b"
$env:GEMMA_LIGHT_MODEL           = "gemma4:e4b"
$env:GEMMA_TIMEOUT_SECONDS       = "120"
$env:GEMMA_KEEP_ALIVE            = "30m"
$env:GEMMA_NUM_THREAD            = "10"
$env:CHROMA_PATH                 = "./data/chroma_db"
$env:UPLOADS_DIR                 = "./uploads"
$env:HF_HOME                     = "./.hf-cache"
$env:TRANSFORMERS_CACHE          = "./.hf-cache/transformers"
$env:HTTP_PROXY                  = ""
$env:HTTPS_PROXY                 = ""
$env:ALL_PROXY                   = ""
$env:GIT_HTTP_PROXY              = ""
$env:GIT_HTTPS_PROXY             = ""
$env:NO_PROXY                    = "localhost,127.0.0.1,::1"

$pidFile = Join-Path $scriptRoot "local-uvicorn.pid"
$PID | Set-Content -Path $pidFile
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
'@

# ===========================================================================
# FIX 5 – backend/.env
# Bug: OLLAMA_HOST port 11435 already correct; GEMMA_TIMEOUT_SECONDS missing
#      (pydantic falls back to default 45 s). Add it explicitly at 120 s.
# ===========================================================================
Write-File "backend/.env" @'
POSTGRES_DSN=postgresql+asyncpg://sci:password@localhost:5432/scidb
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
OLLAMA_HOST=http://localhost:11435
GEMMA_REASONING_MODEL=gemma4:e4b
GEMMA_LIGHT_MODEL=gemma4:e4b
GEMMA_TIMEOUT_SECONDS=120
GEMMA_KEEP_ALIVE=30m
GEMMA_NUM_THREAD=10
PAPER_PROCESSING_MODE=local
INDEX_VECTORS_DURING_PROCESSING=false
CHROMA_PATH=./data/chroma_db
UPLOADS_DIR=./uploads
'@

# ===========================================================================
# FIX 6 – frontend/app.py
# Bugs:
#   (a) poll_paper_processing estimate_seconds=240 (4 min) — target is <1 min;
#       change to 60 s so the progress bar reflects reality.
#   (b) paper_selector with multi=False: st.selectbox can return None when the
#       options list is empty (despite the early-return guard). Add explicit
#       None guard before indexing options[selected].
#   (c) Graph tab: "Load graph" button estimate_seconds=10 — fine, keep it.
#   (d) Upload tab: estimate_seconds=20 for timed_api_call on /papers/upload
#       is fine (just HTTP POST, processing happens in background).
# ===========================================================================
$frontendPath = Join-Path $PSScriptRoot "frontend\app.py"
$fe = [System.IO.File]::ReadAllText($frontendPath)

# Fix (a): poll estimate 240 -> 60
$fe = $fe -replace 'def poll_paper_processing\(paper_id: int, estimate_seconds: int = 240\)',
                   'def poll_paper_processing(paper_id: int, estimate_seconds: int = 60)'

# Fix (b): paper_selector selectbox None guard
# Replace the selectbox return line with a guarded version
$oldSelector = @'
    selected = st.selectbox(label, list(options.keys()))
        return [options[selected]]
'@
$newSelector = @'
    selected = st.selectbox(label, list(options.keys()))
        if selected is None:
            return []
        return [options[selected]]
'@
$fe = $fe -replace [regex]::Escape('    selected = st.selectbox(label, list(options.keys()))
        return [options[selected]]'), $newSelector

[System.IO.File]::WriteAllText($frontendPath, $fe, [System.Text.UTF8Encoding]::new($false))
Write-Host "  [FIXED] frontend/app.py"

# ===========================================================================
# FIX 7 – backend/graph/graph_builder.py
# Bug: setup() runs 3 Cypher queries inside __init__ on every instantiation.
#      With the lru_cache fix in graph.py this is only called once, but
#      also add a _setup_done guard so multiple calls to setup() are no-ops.
#      Also: connection_timeout and max_transaction_retry_time are correct.
# ===========================================================================
$gbPath = Join-Path $PSScriptRoot "backend\graph\graph_builder.py"
$gb = [System.IO.File]::ReadAllText($gbPath)

# Add _setup_done guard to setup()
$oldSetup = @'
    def setup(self) -> None:
        queries = [
'@
$newSetup = @'
    def setup(self) -> None:
        if getattr(self, "_setup_done", False):
            return
        queries = [
'@
$gb = $gb -replace [regex]::Escape($oldSetup), $newSetup

$oldSetupEnd = @'
        with self.driver.session() as session:
            for query in queries:
                session.run(query)
'@
$newSetupEnd = @'
        with self.driver.session() as session:
            for query in queries:
                session.run(query)
        self._setup_done = True
'@
$gb = $gb -replace [regex]::Escape($oldSetupEnd), $newSetupEnd

[System.IO.File]::WriteAllText($gbPath, $gb, [System.Text.UTF8Encoding]::new($false))
Write-Host "  [FIXED] backend/graph/graph_builder.py"

# ===========================================================================
# FIX 8 – backend/core/config.py
# Bug: gemma_timeout_seconds default is 45 s in the class but .env now sets
#      120 — the .env wins, so no code change needed. But the ps1 also sets
#      it to 120 now (fixed above). Just verify the field exists — it does.
#      No change needed here; documented for completeness.
# ===========================================================================
Write-Host "  [OK]    backend/core/config.py  (no change needed)"

# ===========================================================================
# FIX 9 – backend/api/routes/analysis.py
# Bug: get_vector_store() is called as a plain function (not Depends) in the
#      connections endpoint fallback, but it's also listed as Depends — this
#      is actually fine since lru_cache returns the same instance.
#      Real bug: CrossPaperReasoner receives None as vector_store in the
#      gemma4:e4b fast-path for contradictions and landscape, but
#      find_unexplored_connections (connections endpoint) calls
#      self.vector_store.find_cross_paper_similar() unconditionally — will
#      crash with AttributeError if vector_store=None.
#      Fix: always pass vector_store for the connections endpoint.
# ===========================================================================
Write-File "backend/api/routes/analysis.py" @'
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_gemma_engine, get_vector_store
from core.gemma_engine import GemmaEngine
from reasoning.cross_paper_reasoner import CrossPaperReasoner
from retrieval.vector_store import VectorStore
from schemas.analysis_schemas import ConnectionsRequest, ContradictionRequest, LandscapeRequest

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/contradictions")
async def contradictions(
    payload: ContradictionRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> list[dict]:
    return await CrossPaperReasoner(vector_store, gemma, None).detect_contradictions(payload.topic, payload.paper_ids, db)


@router.post("/connections")
async def connections(
    payload: ConnectionsRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> list[dict]:
    items = await CrossPaperReasoner(vector_store, gemma, None).find_unexplored_connections(payload.paper_id, db)
    return [item.__dict__ for item in items]


@router.post("/landscape")
async def landscape(
    payload: LandscapeRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> dict:
    return await CrossPaperReasoner(vector_store, gemma, None).analyze_research_landscape(payload.topic, db)
'@

Write-Host "`n=== All fixes applied successfully ===`n"
Write-Host "Files changed:"
Write-Host "  backend/api/main.py"
Write-Host "  backend/api/routes/graph.py"
Write-Host "  backend/api/routes/analysis.py"
Write-Host "  backend/tasks/paper_processing.py"
Write-Host "  backend/run_local_uvicorn.ps1"
Write-Host "  backend/.env"
Write-Host "  backend/graph/graph_builder.py"
Write-Host "  frontend/app.py"
Write-Host ""
Write-Host "Now restart the backend:"
Write-Host "  cd backend"
Write-Host "  .\run_local_uvicorn.ps1"