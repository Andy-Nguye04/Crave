"""
Persistent recipe session store.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.logging_utils import trace_calls
from app.schemas.recipe import RecipeModel
from app.models import ParsedRecipe
from app.database import SessionLocal

@dataclass
class StoredSession:
    session_id: str
    recipe: RecipeModel
    dry_run: bool = False

@trace_calls
def create_session(recipe: RecipeModel, *, dry_run: bool = False) -> str:
    sid = str(uuid.uuid4())
    
    with SessionLocal() as db:
        pr = ParsedRecipe(
            session_id=sid,
            dry_run=dry_run,
            schema_dump=recipe.model_dump()
        )
        db.add(pr)
        db.commit()
    return sid

@trace_calls
def get_session(session_id: str) -> StoredSession | None:
    with SessionLocal() as db:
        pr = db.query(ParsedRecipe).filter(ParsedRecipe.session_id == session_id).first()
        if not pr:
            return None
            
        recipe = RecipeModel(**pr.schema_dump)
        return StoredSession(
            session_id=pr.session_id,
            recipe=recipe,
            dry_run=pr.dry_run
        )

@trace_calls
def session_to_dict(session: StoredSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "dry_run": session.dry_run,
        "recipe": session.recipe.model_dump(),
    }
