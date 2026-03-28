"""
History store for tracking completed recipes and ratings (SQLite backend).
"""

import uuid
from datetime import datetime
from typing import List

from app.logging_utils import trace_calls
from app.schemas.history import CookedRecipe, HistoryAddRequest
from app.services.recipe_store import get_session
from app.database import SessionLocal
from app.models import CookedHistory

@trace_calls
def add_cooked_recipe(user_id: str, request: HistoryAddRequest) -> CookedRecipe:
    session = get_session(request.session_id)
    if not session:
        raise ValueError("Invalid session ID or session expired")
    
    recipe = session.recipe
    
    # Try to extract a youtube thumbnail
    thumbnail_url = None
    if recipe.source_url:
        import re
        m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{6,})", recipe.source_url)
        if m:
            thumbnail_url = f"https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg"
            
    cr_id = str(uuid.uuid4())
    
    with SessionLocal() as db:
        history_record = CookedHistory(
            id=cr_id,
            user_id=user_id,
            recipe_name=recipe.recipe_name or "Unknown Recipe",
            source_url=recipe.source_url or "",
            thumbnail_url=thumbnail_url,
            session_id=request.session_id,
            rating=request.rating,
            tags=request.tags,
            cooked_at=datetime.utcnow()
        )
        db.add(history_record)
        db.commit()
        db.refresh(history_record)

        return CookedRecipe(
            id=history_record.id,
            recipe_name=history_record.recipe_name,
            source_url=history_record.source_url,
            thumbnail_url=history_record.thumbnail_url,
            session_id=history_record.session_id,
            rating=history_record.rating,
            tags=history_record.tags,
            cooked_at=history_record.cooked_at
        )

@trace_calls
def get_user_history(user_id: str, sort_by: str = "ranked") -> List[CookedRecipe]:
    with SessionLocal() as db:
        query = db.query(CookedHistory).filter(CookedHistory.user_id == user_id)
        
        if sort_by == "recent":
            query = query.order_by(CookedHistory.cooked_at.desc())
        else:
            query = query.order_by(CookedHistory.rating.desc(), CookedHistory.cooked_at.desc())
            
        results = query.all()
        
        return [
            CookedRecipe(
                id=r.id,
                recipe_name=r.recipe_name,
                source_url=r.source_url,
                thumbnail_url=r.thumbnail_url,
                session_id=r.session_id,
                rating=r.rating,
                tags=r.tags,
                cooked_at=r.cooked_at
            ) for r in results
        ]
