import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.routes import agents, analysis, auth, graph, hypothesis, papers, search, workspace
from core.config import get_settings
from core.model_warmup import start_model_warmup
from models.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        logging.getLogger("startup").info("Database initialised successfully.")
    except Exception as exc:
        logging.getLogger("startup").warning(
            f"Database unavailable at startup (PostgreSQL not running?): {exc}. "
            "Server will start but DB-dependent routes will fail."
        )
    asyncio.create_task(start_model_warmup())
    yield


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
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(search.router, prefix=settings.api_prefix)
    app.include_router(graph.router, prefix=settings.api_prefix)
    app.include_router(hypothesis.router, prefix=settings.api_prefix)
    app.include_router(analysis.router, prefix=settings.api_prefix)
    app.include_router(agents.router, prefix=settings.api_prefix)
    app.include_router(agents.chat_router, prefix=settings.api_prefix)
    app.include_router(workspace.router, prefix=settings.api_prefix)

    @app.exception_handler(Exception)
    async def structured_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR", "detail": str(exc)},
        )

    @app.get("/health")
    async def health(db: AsyncSession = Depends(get_db)) -> dict:
        status: dict = {"status": "ok", "components": {}}
        try:
            await db.execute(text("SELECT 1"))
            status["components"]["database"] = "ok"
        except Exception as exc:
            status["components"]["database"] = f"error: {exc}"
            status["status"] = "degraded"

        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
                response.raise_for_status()
                payload = response.json()
            model_names = [item.get("name", "") for item in payload.get("models", [])]
            status["components"]["ollama"] = "ok"
            status["components"]["models"] = model_names
            status["components"]["model_ready"] = any("gemma" in name.lower() for name in model_names)
            if not status["components"]["model_ready"]:
                status["status"] = "degraded"
        except Exception as exc:
            status["components"]["ollama"] = f"error: {exc}"
            status["components"]["models"] = []
            status["components"]["model_ready"] = False
            status["status"] = "degraded"

        return status

    return app


app = create_app()
