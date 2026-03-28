"""
Saved recipes store (SQLite via SQLAlchemy).
De-duplicates by source_url per user.
"""

import uuid
from datetime import datetime
from typing import List

from app.logging_utils import trace_calls
from app.schemas.saved import SavedRecipe as SavedRecipeSchema
from app.services.recipe_store import get_session
from app.database import SessionLocal
from app.models import SavedRecipe


def _extract_thumb(source_url: str):
    if not source_url:
        return None
    import re
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{6,})", source_url)
    return f"https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg" if m else None


@trace_calls
def save_recipe(user_id: str, session_id: str) -> SavedRecipeSchema:
    """
    Save a recipe from an active session.
    Raises ValueError if already saved (de-dup by source_url per user).
    """
    session = get_session(session_id)
    if not session:
        raise ValueError("Invalid session ID or session expired")

    recipe = session.recipe
    source_url = recipe.source_url or ""

    with SessionLocal() as db:
        # De-duplicate by source_url per user
        existing = (
            db.query(SavedRecipe)
            .filter(SavedRecipe.user_id == user_id, SavedRecipe.source_url == source_url)
            .first()
        )
        if existing:
            raise ValueError("already_saved")

        record = SavedRecipe(
            id=str(uuid.uuid4()),
            user_id=user_id,
            recipe_name=recipe.recipe_name or "Unknown Recipe",
            source_url=source_url,
            thumbnail_url=_extract_thumb(source_url),
            saved_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return SavedRecipeSchema(
            id=record.id,
            recipe_name=record.recipe_name,
            source_url=record.source_url,
            thumbnail_url=record.thumbnail_url,
            saved_at=record.saved_at,
        )


@trace_calls
def get_saved_recipes(user_id: str) -> List[SavedRecipeSchema]:
    """Return all saved recipes for a user, newest first."""
    with SessionLocal() as db:
        results = (
            db.query(SavedRecipe)
            .filter(SavedRecipe.user_id == user_id)
            .order_by(SavedRecipe.saved_at.desc())
            .all()
        )
        return [
            SavedRecipeSchema(
                id=r.id,
                recipe_name=r.recipe_name,
                source_url=r.source_url,
                thumbnail_url=r.thumbnail_url,
                saved_at=r.saved_at,
            )
            for r in results
        ]


@trace_calls
def delete_saved_recipe(user_id: str, saved_id: str) -> bool:
    """Remove a saved recipe. Returns True if deleted, False if not found."""
    with SessionLocal() as db:
        record = (
            db.query(SavedRecipe)
            .filter(SavedRecipe.id == saved_id, SavedRecipe.user_id == user_id)
            .first()
        )
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True
