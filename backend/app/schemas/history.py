"""
Pydantic schemas for the recipe cooking history.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class HistoryAddRequest(BaseModel):
    """Payload sent from the cooking-mode-finish page."""
    session_id: str
    rating: int = Field(ge=1, le=5, description="1-5 star rating")
    tags: List[str] = Field(default_factory=list, description="User tags like 'Needs Salt'")

class CookedRecipe(BaseModel):
    """Data model representing a completed recipe."""
    id: str
    recipe_name: str
    source_url: str
    thumbnail_url: Optional[str] = None
    rating: int
    tags: List[str]
    cooked_at: datetime
