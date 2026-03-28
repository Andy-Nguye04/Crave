"""
Crave FastAPI entrypoint.

Mounts CORS, health check, parse/recipe routers, and the cooking Live WebSocket.
Run from the ``backend`` directory::

    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, cooking_ws, parse_youtube, profile, recipes, history
from app.database import engine
from app.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crave")

app = FastAPI(title="Crave API", version="0.1.0")

Base.metadata.create_all(bind=engine)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(parse_youtube.router)
app.include_router(recipes.router)
app.include_router(cooking_ws.router)
app.include_router(history.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for deploys and local sanity checks."""

    return {"status": "ok"}
