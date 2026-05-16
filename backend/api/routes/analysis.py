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
    """Detect contradictions between pairs of papers on a topic."""
    return await CrossPaperReasoner(vector_store, gemma, None).detect_contradictions(
        payload.topic, payload.paper_ids, db
    )


@router.post("/connections")
async def connections(
    payload: ConnectionsRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> list[dict]:
    """Find unexplored cross-paper connections for a given paper."""
    items = await CrossPaperReasoner(vector_store, gemma, None).find_unexplored_connections(
        payload.paper_id, db
    )
    return [item.__dict__ for item in items]


@router.post("/landscape")
async def landscape(
    payload: LandscapeRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> dict:
    """Analyse the research landscape for a topic."""
    return await CrossPaperReasoner(vector_store, gemma, None).analyze_research_landscape(
        payload.topic, db
    )
