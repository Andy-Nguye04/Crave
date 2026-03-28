"""
History REST endpoints, protected by session token.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.logging_utils import trace_calls
from app.routers.profile import get_current_user_id
from app.schemas.history import CookedRecipe, HistoryAddRequest
from app.services.history_store import get_user_history, add_cooked_recipe

router = APIRouter(prefix="/api/history", tags=["history"])

@router.get("", response_model=List[CookedRecipe])
@trace_calls
async def get_history(
    sort_by: str = "ranked",
    user_id: str = Depends(get_current_user_id)
) -> List[CookedRecipe]:
    """Returns the authenticated user's cooked history."""
    return get_user_history(user_id, sort_by)

@router.post("", response_model=CookedRecipe)
@trace_calls
async def log_history(
    request: HistoryAddRequest,
    user_id: str = Depends(get_current_user_id)
) -> CookedRecipe:
    """Logs a completed cooking session to history with rating and tags."""
    try:
        return add_cooked_recipe(user_id, request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
