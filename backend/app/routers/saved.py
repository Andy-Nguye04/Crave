"""
Saved recipes REST endpoints. All routes are protected.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.routers.profile import get_current_user_id
from app.schemas.saved import SavedRecipe, SaveRequest
from app.services.saved_store import save_recipe, get_saved_recipes, delete_saved_recipe

router = APIRouter(prefix="/api/saved", tags=["saved"])


@router.post("", response_model=SavedRecipe, status_code=status.HTTP_201_CREATED)
async def save(
    request: SaveRequest,
    user_id: str = Depends(get_current_user_id),
) -> SavedRecipe:
    """Save a recipe from an active session."""
    try:
        return save_recipe(user_id, request.session_id)
    except ValueError as e:
        code = status.HTTP_409_CONFLICT if str(e) == "already_saved" else status.HTTP_400_BAD_REQUEST
        detail = "Recipe already saved." if str(e) == "already_saved" else str(e)
        raise HTTPException(status_code=code, detail=detail)


@router.get("", response_model=List[SavedRecipe])
async def list_saved(
    user_id: str = Depends(get_current_user_id),
) -> List[SavedRecipe]:
    """Return the authenticated user's saved recipes."""
    return get_saved_recipes(user_id)


@router.delete("/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave(
    saved_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Remove a saved recipe."""
    deleted = delete_saved_recipe(user_id, saved_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved recipe not found.")
