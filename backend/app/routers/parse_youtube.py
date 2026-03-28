"""
YouTube ingestion REST endpoint.

Exposes ``POST /api/parse-youtube`` which runs the Gemini recipe parser,
stores the result under a new session id, and returns JSON for the web UI.
Supports ``dry_run`` so demos and automated tests never spend quota or touch
real video content.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from app.config import get_settings
from app.logging_utils import trace_calls
from app.schemas.recipe import ParseYoutubeRequest, ParseYoutubeResponse
from app.services.recipe_parser import parse_youtube_to_recipe
from app.services.recipe_store import create_session
from app.routers.profile import get_current_user_id
from app.services.profile_store import get_or_create_profile

router = APIRouter(prefix="/api", tags=["parse"])


@router.post("/parse-youtube", response_model=ParseYoutubeResponse)
@trace_calls
async def parse_youtube(
    body: ParseYoutubeRequest,
    user_id: str = Depends(get_current_user_id)
) -> ParseYoutubeResponse:
    """
    Parse a YouTube URL into structured recipe JSON and open a cooking session.

    Args:
        body: Request containing ``youtube_url`` and optional ``dry_run``.

    Returns:
        ``session_id`` and validated ``recipe``.

    Raises:
        HTTPException: 400 on validation/parsing errors, 500 on unexpected failures.
    """

    settings = get_settings()
    dry = body.dry_run or settings.crave_dry_run_default
    profile = get_or_create_profile(user_id)
    try:
        recipe = parse_youtube_to_recipe(str(body.youtube_url), profile=profile, dry_run=dry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Parse failed: {exc}",
        ) from exc

    session_id = create_session(recipe, dry_run=dry)
    return ParseYoutubeResponse(session_id=session_id, recipe=recipe)
