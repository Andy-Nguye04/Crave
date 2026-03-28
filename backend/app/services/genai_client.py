"""
Shared Google GenAI client factory.

The hackathon app uses one ``genai.Client`` per process, constructed with
``GEMINI_API_KEY``. Used by recipe parsing (``generate_content``) and the
Live cooking WebSocket (``aio.live.connect``).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from google import genai

from app.config import get_settings
from app.logging_utils import log_function_call

logger = logging.getLogger("crave")


@lru_cache
def get_genai_client() -> genai.Client:
    """
    Build and cache a ``genai.Client`` using settings.

    Returns:
        Configured client for REST and async Live APIs.

    Raises:
        ValueError: If ``GEMINI_API_KEY`` is missing or empty.
    """

    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        raise ValueError(
            "GEMINI_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and add your hackathon API key.",
        )
    log_function_call("get_genai_client", (), {})
    return genai.Client(api_key=settings.gemini_api_key.strip())
