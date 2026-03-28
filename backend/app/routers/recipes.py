"""
Recipe retrieval REST endpoint.

After parsing, the browser loads ``GET /api/recipes/{session_id}`` to hydrate
cooking-mode UI without resending the full recipe in the WebSocket handshake.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.logging_utils import trace_calls
from app.services.recipe_store import get_session, session_to_dict

router = APIRouter(prefix="/api", tags=["recipes"])


@router.get("/recipes/{session_id}")
@trace_calls
async def get_recipe_session(session_id: str) -> dict:
    """
    Return the stored recipe and metadata for a session id.

    Args:
        session_id: UUID from ``POST /api/parse-youtube``.

    Returns:
        JSON dict with ``session_id``, ``dry_run``, and ``recipe``.

    Raises:
        HTTPException: 404 if the session does not exist.
    """

    stored = get_session(session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return session_to_dict(stored)
