"""
Recipe JSON schemas aligned with the hackathon spec (section 5).

These models validate Gemini outputs and API responses. Steps use
``visual_context`` and ``timestamp_sec``; ingredients include dietary flags
and optional substitution hints for the sous-chef voice flow.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class IngredientModel(BaseModel):
    """One ingredient line with dietary metadata for substitution logic."""

    item: str
    amount: str = ""
    dietary_conflict: bool = False
    suggested_substitute: str = ""


class StepModel(BaseModel):
    """A single cooking step with timing and visual narration for voice UI."""

    step_number: int = Field(..., ge=1)
    timestamp_sec: int = Field(0, ge=0)
    instruction: str
    visual_context: str = ""
    technical_terms: list[str] = Field(default_factory=list)


class RecipeModel(BaseModel):
    """Full recipe document returned by parsing and served to the cooking UI."""

    recipe_name: str
    source_url: str
    ingredients: list[IngredientModel] = Field(default_factory=list)
    steps: list[StepModel] = Field(default_factory=list)
    dietary_summary: str = ""


class ParseYoutubeRequest(BaseModel):
    """Request body for YouTube URL ingestion."""

    youtube_url: HttpUrl
    dry_run: bool = False


class ParseYoutubeResponse(BaseModel):
    """Response after a successful parse: server session id and recipe JSON."""

    session_id: str
    recipe: RecipeModel
