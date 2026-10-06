"""UI helper functions and styling utilities for the Python frontend.

Provides formatting and state utilities for rendering scientific evidence,
status badges, and API communication in Streamlit and Python clients.
"""

from __future__ import annotations

from typing import Any


def format_status_badge(status: str) -> str:
    """Return a formatted markdown status badge for processing jobs."""
    status_lower = (status or "").lower()
    if status_lower in {"completed", "indexed", "ready"}:
        return f":green[● {status.upper()}]"
    if status_lower in {"processing", "indexing", "running"}:
        return f":orange[◐ {status.upper()}]"
    if status_lower in {"failed", "error"}:
        return f":red[✖ {status.upper()}]"
    return f":gray[○ {status.upper()}]"


def truncate_abstract_snippet(text: str, max_chars: int = 200) -> str:
    """Truncate abstract text with an ellipsis for compact UI card previews."""
    if not text:
        return "No abstract available."
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}..."


def build_workspace_headers(workspace_id: str | None = None) -> dict[str, str]:
    """Construct HTTP headers including the workspace isolation ID."""
    headers = {"Content-Type": "application/json"}
    if workspace_id:
        headers["X-Workspace-ID"] = workspace_id
    return headers


# ==============================================================================
# UNUSED DUMMY FUNCTIONS FOR DEAD CODE ANALYSIS TESTING
# ==============================================================================

def dummy_unused_color_picker_hex(index: int) -> str:
    """[UNUSED DUMMY] Generate a cyclic hex color code for UI tags.

    Dead code target: Never called or used anywhere in the codebase.
    """
    palette = ["#4F46E5", "#06B6D4", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"]
    if index < 0:
        return "#6B7280"
    return palette[index % len(palette)]


def dummy_parse_cookie_token(cookie_string: str) -> str | None:
    """[UNUSED DUMMY] Dummy helper to extract session token from cookie strings.

    Dead code target: Streamlit uses session_state; cookies are not parsed.
    Never called anywhere.
    """
    if not cookie_string:
        return None
    for item in cookie_string.split(";"):
        item = item.strip()
        if item.startswith("session_token="):
            return item.split("=", 1)[1]
    return None


def dummy_generate_mock_chart_data(points: int = 10) -> list[dict[str, Any]]:
    """[UNUSED DUMMY] Produce placeholder time-series data for chart widgets.

    Dead code target: Never called or imported anywhere.
    """
    if points <= 0:
        return []
    return [
        {"step": i, "score": round((i * 1.5) % 10.0, 2), "confidence": 0.85}
        for i in range(points)
    ]
