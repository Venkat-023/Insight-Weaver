from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.postgres_dsn, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from models import entity, hypothesis, paper  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_sqlite_workspace_columns(conn)


async def _ensure_sqlite_workspace_columns(conn) -> None:
    if not settings.postgres_dsn.startswith("sqlite"):
        return
    tables = ("papers", "entities", "hypotheses", "contradictions")
    for table in tables:
        rows = await conn.execute(text(f"PRAGMA table_info({table})"))
        columns = {row[1] for row in rows.fetchall()}
        if "workspace_id" not in columns:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN workspace_id VARCHAR(36) NOT NULL DEFAULT 'legacy'"))
            await conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_workspace_id ON {table} (workspace_id)"))
