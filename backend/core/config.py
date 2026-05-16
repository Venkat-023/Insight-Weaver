from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Scientific Discovery Copilot"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ])

    postgres_dsn: str = "sqlite+aiosqlite:///./scidb.db"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    paper_processing_mode: str = "local"
    index_vectors_during_processing: bool = False

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    ollama_host: str = "http://localhost:11435"
    # Default preference: e4b (higher quality). Warmup will fall back to e2b if e4b not installed.
    gemma_reasoning_model: str = "gemma4:e4b"
    gemma_light_model: str = "gemma4:e4b"
    gemma_timeout_seconds: int = 60
    gemma_keep_alive: str = "30m"
    gemma_num_thread: int | None = None

    chroma_path: str = "./data/chroma_db"
    uploads_dir: str = "./uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_model(settings: Settings) -> str:
    """Return the active model name, respecting runtime fallback."""
    return settings.gemma_reasoning_model
