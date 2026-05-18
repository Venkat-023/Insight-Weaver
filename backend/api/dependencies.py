from collections.abc import AsyncGenerator
from functools import lru_cache
import os
import re

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.gemma_engine import GemmaEngine
from models.database import get_db_session
from models.paper import Paper
from retrieval.vector_store import VectorStore


_WORKSPACE_RE = re.compile(r"^[a-f0-9-]{36}$", re.IGNORECASE)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


def settings_dep() -> Settings:
    return get_settings()


def get_workspace_id(request: Request) -> str:
    workspace_id = request.headers.get("X-Workspace-ID", "").strip().lower()
    if not workspace_id or not _WORKSPACE_RE.fullmatch(workspace_id):
        raise HTTPException(
            status_code=400,
            detail={"error": "X-Workspace-ID header is required and must be a valid UUID", "code": "WORKSPACE_REQUIRED"},
        )
    return workspace_id


async def validate_paper_belongs_to_workspace(paper_id: int, workspace_id: str, db: AsyncSession) -> Paper:
    paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, {"error": "Paper not found", "code": "PAPER_NOT_FOUND", "detail": str(paper_id)})
    if paper.workspace_id != workspace_id:
        raise HTTPException(403, {"error": "Paper does not belong to this workspace", "code": "WORKSPACE_FORBIDDEN"})
    return paper


def get_gemma_engine() -> GemmaEngine:
    """
    Returns a GemmaEngine using the runtime-resolved model name.
    Tries the warmup-resolved model first, falls back to settings.
    NOT lru_cached so it always picks up the post-warmup model name.
    """
    from core.model_warmup import get_resolved_model
    resolved = get_resolved_model()
    model = resolved or get_settings().gemma_reasoning_model
    return GemmaEngine(model)


@lru_cache
def get_vector_store() -> VectorStore | None:
    if os.getenv("HF_SPACE_LIGHT_MODE", "").lower() == "true":
        return None
    return VectorStore()
