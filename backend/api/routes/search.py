import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_vector_store, get_workspace_id, validate_paper_belongs_to_workspace
from core.config import get_settings
from core.gemma_engine import GemmaEngine
from retrieval.graph_rag import GraphRAG
from retrieval.semantic_search import SemanticSearch
from retrieval.vector_store import VectorStore
from schemas.search_schemas import GraphRAGRequest, GraphRAGResponse, SearchRequest, SearchResponse, SearchResultSchema

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    payload: SearchRequest,
    vector_store: VectorStore = Depends(get_vector_store),
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> SearchResponse:
    started = time.perf_counter()
    if payload.paper_ids:
        for paper_id in payload.paper_ids:
            await validate_paper_belongs_to_workspace(paper_id, workspace_id, db)
    results = SemanticSearch(vector_store).search(
        payload.query,
        payload.paper_ids,
        payload.n_results,
        payload.section_filter,
        workspace_id=workspace_id,
    )
    return SearchResponse(
        results=[SearchResultSchema(id=item.id, text=item.text, metadata=item.metadata, similarity_score=item.similarity_score) for item in results],
        total=len(results),
        query_time_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post("", response_model=GraphRAGResponse)
async def graph_rag_search(
    payload: GraphRAGRequest,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> dict:
    if payload.paper_ids:
        for paper_id in payload.paper_ids:
            await validate_paper_belongs_to_workspace(paper_id, workspace_id, db)
    settings = get_settings()
    summarizer = GemmaEngine(settings.gemma_light_model, timeout_seconds=payload.max_model_seconds) if payload.use_gemma else None
    vector_store = get_vector_store() if payload.use_vector else None
    return await GraphRAG(vector_store, summarizer).answer(
        payload.query,
        db,
        paper_ids=payload.paper_ids,
        n_results=payload.n_results,
        include_graph=payload.include_graph,
        use_gemma=payload.use_gemma,
        workspace_id=workspace_id,
    )


@router.post("/graphrag", response_model=GraphRAGResponse)
async def graph_rag_search_compat(
    payload: GraphRAGRequest,
    db: AsyncSession = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> dict:
    return await graph_rag_search(payload, db, workspace_id)
