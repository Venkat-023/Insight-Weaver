import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_gemma_engine
from core.gemma_engine import GemmaEngine
from core.model_warmup import get_model_status, start_model_warmup
from models.hypothesis import Hypothesis
from reasoning.multi_agent_debate import MultiAgentDebate
from schemas.agent_schemas import ChatRequest, ChatResponse, DebateRequest

router = APIRouter(prefix="/hypothesis", tags=["agents"])


chat_router = APIRouter(prefix="/agents", tags=["agents"])


@chat_router.get("/model-status")
async def model_status() -> dict:
    return get_model_status()


@chat_router.post("/model-warmup")
async def model_warmup() -> dict:
    await start_model_warmup()
    return get_model_status()


@chat_router.post("/chat", response_model=ChatResponse)
async def chat_with_gemma(
    payload: ChatRequest,
    gemma: GemmaEngine = Depends(get_gemma_engine),
) -> dict:
    started = time.perf_counter()
    chat_gemma = GemmaEngine(gemma.model_name, timeout_seconds=payload.timeout_seconds)
    prompt = (
        "Do not reason silently. Start the final answer immediately. "
        "Be concise, useful, and scientific when the question is scientific.\n\n"
        f"{payload.message}"
    )
    response = chat_gemma.generate(
        prompt,
        temperature=payload.temperature,
        num_predict=payload.max_tokens,
        num_ctx=512,
    )
    return {
        "response": response.strip(),
        "model": chat_gemma.model_name,
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


@router.post("/{hypothesis_id}/debate")
async def debate_hypothesis(
    hypothesis_id: int,
    payload: DebateRequest,
    db: AsyncSession = Depends(get_db),
    gemma: GemmaEngine = Depends(get_gemma_engine),
) -> dict:
    hypothesis = await db.get(Hypothesis, hypothesis_id)
    if not hypothesis:
        raise HTTPException(404, {"error": "Hypothesis not found", "code": "HYPOTHESIS_NOT_FOUND", "detail": str(hypothesis_id)})
    result = MultiAgentDebate(gemma).run_debate(
        {
            "id": hypothesis.id,
            "hypothesis": hypothesis.hypothesis_text,
            "reasoning": hypothesis.reasoning,
            "confidence": hypothesis.confidence_score,
        },
        hypothesis.supporting_evidence,
        payload.rounds,
    )
    hypothesis.agent_validated = True
    await db.commit()
    return result.__dict__
