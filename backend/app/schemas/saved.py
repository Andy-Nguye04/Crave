"""
Pydantic schemas for saved recipes.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class SaveRequest(BaseModel):
    """Payload from the extracted-recipe page to save a recipe."""
    session_id: str


class SavedRecipe(BaseModel):
    """A recipe the user has bookmarked for later."""
    id: str
    recipe_name: str
    source_url: str
    thumbnail_url: Optional[str] = None
    session_id: Optional[str] = None
    saved_at: datetime
