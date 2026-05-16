from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_gemma_engine, get_vector_store
from core.gemma_engine import GemmaEngine
from core.hypothesis_generator import HypothesisGenerator
from models.hypothesis import Hypothesis
from reasoning.cross_paper_reasoner import CrossPaperReasoner
from retrieval.vector_store import VectorStore
from schemas.hypothesis_schemas import HypothesisGenerateRequest, HypothesisListItem, HypothesisResult

router = APIRouter(tags=["hypothesis"])


@router.post("/hypothesis/generate", response_model=HypothesisResult)
async def generate_hypothesis(
    payload: HypothesisGenerateRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> dict:
    reasoner = CrossPaperReasoner(vector_store, gemma, None)
    return await HypothesisGenerator(gemma, vector_store, reasoner).generate(
        payload.query,
        db,
        payload.paper_ids,
        payload.num_hypotheses,
        payload.use_fast_fallback,
    )


@router.post("/hypothesis/{hypothesis_id}/explain")
async def explain_hypothesis(
    hypothesis_id: int,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
    vector_store: VectorStore = Depends(get_vector_store),
) -> dict:
    reasoner = CrossPaperReasoner(vector_store, gemma, None)
    return await HypothesisGenerator(gemma, vector_store, reasoner).explain_hypothesis(hypothesis_id, db)


@router.get("/hypotheses/", response_model=list[HypothesisListItem])
async def list_hypotheses(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_confidence: float = 0.0,
    paper_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Hypothesis]:
    stmt = select(Hypothesis).where(Hypothesis.confidence_score >= min_confidence).offset(offset).limit(limit)
    if paper_id is not None:
        stmt = stmt.where(Hypothesis.supporting_paper_ids.contains([paper_id]))
    return list((await db.execute(stmt)).scalars().all())


@router.post("/hypotheses/{id}/upvote")
async def upvote_hypothesis(id: int, db: AsyncSession = Depends(get_db)) -> dict:
    hypothesis = await db.get(Hypothesis, id)
    if not hypothesis:
        raise HTTPException(404, {"error": "Hypothesis not found", "code": "HYPOTHESIS_NOT_FOUND", "detail": str(id)})
    hypothesis.upvotes += 1
    await db.commit()
    return {"id": id, "upvotes": hypothesis.upvotes}
