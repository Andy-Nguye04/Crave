"""
In-memory recipe session store for the hackathon MVP.

Maps opaque session IDs to parsed recipe documents. No database — data is
lost on process restart. Use cases: after ``POST /api/parse-youtube`` the
client receives a ``session_id``; cooking mode and WebSockets load the same
recipe by id. A ``dry_run`` flag on stored entries prevents accidental
confusion in tests (metadata only; recipe still held in memory).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.logging_utils import trace_calls
from app.schemas.recipe import RecipeModel


@dataclass
class StoredSession:
    """One cooking session with parsed recipe and optional dry-run marker."""

    session_id: str
    recipe: RecipeModel
    dry_run: bool = False


_sessions: dict[str, StoredSession] = {}


@trace_calls
def create_session(recipe: RecipeModel, *, dry_run: bool = False) -> str:
    """
    Store a recipe and return a new session id.

    Args:
        recipe: Validated recipe model to associate with the session.
        dry_run: When True, marks the session as test data (metadata only).

    Returns:
        A UUID string used in subsequent API and WebSocket paths.
    """

    sid = str(uuid.uuid4())
    _sessions[sid] = StoredSession(session_id=sid, recipe=recipe, dry_run=dry_run)
    return sid


@trace_calls
def get_session(session_id: str) -> StoredSession | None:
    """
    Look up a session by id.

    Args:
        session_id: UUID returned from ``create_session``.

    Returns:
        The ``StoredSession`` or ``None`` if missing or invalid.
    """

    return _sessions.get(session_id)


@trace_calls
def session_to_dict(session: StoredSession) -> dict[str, Any]:
    """
    Serialize a stored session for JSON responses (includes dry_run flag).

    Args:
        session: Non-null session from ``get_session``.

    Returns:
        A dict suitable for FastAPI ``JSONResponse``.
    """

    return {
        "session_id": session.session_id,
        "dry_run": session.dry_run,
        "recipe": session.recipe.model_dump(),
    }
