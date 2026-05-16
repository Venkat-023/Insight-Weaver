from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.gemma_engine import GemmaEngine
from models.database import get_db_session
from retrieval.vector_store import VectorStore


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


def settings_dep() -> Settings:
    return get_settings()


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
def get_vector_store() -> VectorStore:
    return VectorStore()
