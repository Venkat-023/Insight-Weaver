from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
import time
from typing import Any

from core.config import get_settings

logger = logging.getLogger("scientific_discovery.warmup")

# ── Module-level resolved model name (set once during warmup) ──────────────────
_resolved_model: str | None = None

_state: dict[str, Any] = {
    "status": "not_started",
    "model": None,
    "message": "Gemma warm-up has not started.",
    "response": None,
    "duration_seconds": None,
    "started_at": None,
    "completed_at": None,
}
_lock = asyncio.Lock()
_task: asyncio.Task | None = None


def get_model_status() -> dict[str, Any]:
    return dict(_state)


def get_resolved_model() -> str | None:
    """Return the runtime-resolved model name (after warmup). None means warmup hasn't run yet."""
    return _resolved_model


async def start_model_warmup() -> None:
    global _task
    async with _lock:
        if _task and not _task.done():
            return
        if _state["status"] == "loaded":
            return
        _task = asyncio.create_task(_warm_model())


# Ordered preference list — first available wins
_MODEL_PREFERENCE = ["gemma4:e4b", "gemma4:e2b"]


async def _warm_model() -> None:
    global _resolved_model
    settings = get_settings()
    configured_model = settings.gemma_reasoning_model

    _state.update(
        {
            "status": "loading",
            "model": configured_model,
            "message": f"Checking Ollama for available models (preference: {configured_model}).",
            "response": None,
            "duration_seconds": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
    )
    started = time.perf_counter()
    try:
        import httpx
        ollama_host = settings.ollama_host.rstrip("/")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ollama_host}/api/tags")
            resp.raise_for_status()
        models = resp.json().get("models", [])
        available = {
            item.get("name") or item.get("model")
            for item in models
            if item.get("name") or item.get("model")
        }
        logger.info("Available Ollama models: %s", available)

        # Resolve: try configured model first, then preference list, then any gemma4
        chosen: str | None = None
        if configured_model in available:
            chosen = configured_model
        else:
            for candidate in _MODEL_PREFERENCE:
                if candidate in available:
                    chosen = candidate
                    break
            if chosen is None:
                # Last resort: any model starting with gemma4
                for m in available:
                    if m and m.startswith("gemma4"):
                        chosen = m
                        break

        if chosen is None:
            _state.update(
                {
                    "status": "failed",
                    "message": f"No Gemma model found in Ollama. Install one of: {_MODEL_PREFERENCE}",
                    "response": None,
                    "duration_seconds": round(time.perf_counter() - started, 3),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "detail": "Run: ollama pull gemma4:e2b",
                }
            )
            return

        # Persist the resolved model so GemmaEngine can pick it up
        _resolved_model = chosen
        # Also mutate the settings object so downstream code that reads it gets the right model
        settings.gemma_reasoning_model = chosen
        settings.gemma_light_model = chosen

        duration = round(time.perf_counter() - started, 3)
        fallback_note = f" (fell back from {configured_model})" if chosen != configured_model else ""
        _state.update(
            {
                "status": "loaded",
                "model": chosen,
                "message": f"{chosen} is ready{fallback_note}.",
                "response": chosen,
                "duration_seconds": duration,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.info("Warmup complete — using model: %s", chosen)
    except Exception as exc:
        _state.update(
            {
                "status": "failed",
                "message": "Failed to connect to Ollama. Ensure Ollama is running on the configured host.",
                "response": None,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "detail": str(exc),
            }
        )
