"""Insight Weaver - Scientific Discovery Copilot Streamlit Interface.

Lightweight Python frontend dashboard for PDF research synthesis, GraphRAG querying,
and hypothesis exploration via the FastAPI backend.
"""

from __future__ import annotations

import os
from typing import Any
import requests

from ui_helpers import build_workspace_headers, format_status_badge, truncate_abstract_snippet

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")


def check_backend_health() -> bool:
    """Verify backend connectivity."""
    try:
        resp = requests.get(f"{API_BASE.replace('/api/v1', '')}/health", timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def query_graphrag_api(question: str, workspace_id: str = "default") -> dict[str, Any]:
    """Send a scientific research question to the GraphRAG backend endpoint."""
    url = f"{API_BASE}/reasoning/graphrag"
    payload = {"query": question}
    headers = build_workspace_headers(workspace_id)
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as err:
        return {"error": str(err), "answer": "Failed to communicate with GraphRAG service."}


def fetch_indexed_papers(workspace_id: str = "default") -> list[dict[str, Any]]:
    """Retrieve indexed research papers from the library."""
    url = f"{API_BASE}/papers"
    headers = build_workspace_headers(workspace_id)
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json().get("papers", [])
    except requests.RequestException:
        return []


# ==============================================================================
# UNUSED DUMMY FUNCTIONS FOR DEAD CODE ANALYSIS TESTING
# ==============================================================================

def dummy_frontend_cache_clearer() -> bool:
    """[UNUSED DUMMY] Clear memory caches in the UI process.

    Dead code target: Placeholder function that is never invoked.
    """
    return True


def dummy_calculate_reading_progress(current_page: int, total_pages: int) -> float:
    """[UNUSED DUMMY] Calculate PDF reading completion percentage.

    Dead code target: Never wired to any Streamlit widget or progress bar.
    """
    if total_pages <= 0:
        return 0.0
    return min(100.0, max(0.0, round((current_page / total_pages) * 100, 1)))


def dummy_unused_notification_toast(message: str, icon: str = "ℹ️") -> str:
    """[UNUSED DUMMY] Format dummy notification toast for UI alerting.

    Dead code target: Never called anywhere in frontend or backend.
    """
    return f"{icon} [ALERT]: {message.strip()}"
