"""
YouTube → structured recipe parsing with Gemini (JSON mode).

Primary path: send the YouTube watch URL as ``file_data`` to
``generate_content`` with a strict JSON schema (hackathon spec). Fallback:
if video ingestion fails (quota, permissions), fetch a text transcript via
``youtube-transcript-api`` and parse from text only.

Use cases:
- ``POST /api/parse-youtube`` with ``dry_run: true`` returns a fixed sample
  recipe without calling Gemini (tests and UI scaffolding).
- Normal parse persists a validated ``RecipeModel`` for Live tools.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from google.genai import types

from app.config import get_settings
from app.logging_utils import log_genai_event, trace_calls
from app.schemas.recipe import RecipeModel
from app.schemas.profile import UserProfile
from app.services.genai_client import get_genai_client

_YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{6,})")


def _extract_youtube_id(url: str) -> str | None:
    """Return the YouTube video id from a watch, short, or youtu.be URL."""

    parsed = urlparse(str(url))
    if parsed.hostname and "youtu.be" in parsed.hostname:
        seg = (parsed.path or "").strip("/").split("/")[0]
        return seg or None
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]
    m = _YOUTUBE_ID_RE.search(str(url))
    return m.group(1) if m else None


def _transcript_text(url: str) -> str:
    """Fetch concatenated transcript lines with rough timestamps (best-effort)."""

    from youtube_transcript_api import YouTubeTranscriptApi

    vid = _extract_youtube_id(url)
    if not vid:
        raise ValueError("Could not parse YouTube video id from URL")

    # youtube-transcript-api 1.x: YouTubeTranscriptApi().fetch(video_id) → FetchedTranscript
    # Older 0.x: YouTubeTranscriptApi.get_transcript(video_id) → list[dict]
    api = YouTubeTranscriptApi()
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        chunks = YouTubeTranscriptApi.get_transcript(vid)  # type: ignore[attr-defined]
    else:
        fetched = api.fetch(vid)
        chunks = fetched.to_raw_data()

    lines = [f"[{int(c['start'])}s] {c['text']}" for c in chunks[:400]]
    return "\n".join(lines)


SAMPLE_RECIPE_DICT: dict = {
    "recipe_name": "Demo Garden Pesto Pappardelle",
    "source_url": "https://www.youtube.com/watch?v=demo",
    "ingredients": [
        {
            "item": "Basil",
            "amount": "2 cups packed",
            "dietary_conflict": False,
            "suggested_substitute": "Arugula or spinach",
        },
        {
            "item": "Parmesan",
            "amount": "1/2 cup grated",
            "dietary_conflict": True,
            "suggested_substitute": "Nutritional yeast or vegan hard cheese",
        },
    ],
    "steps": [
        {
            "step_number": 1,
            "timestamp_sec": 0,
            "instruction": "Blanch basil in salted boiling water for 10 seconds, then shock in ice water.",
            "visual_context": "Bright green leaves go limp quickly; ice bath locks the color.",
            "technical_terms": ["Blanch"],
        },
        {
            "step_number": 2,
            "timestamp_sec": 45,
            "instruction": "Pulse basil, garlic, nuts, and cheese in a food processor until coarse.",
            "visual_context": "Chef uses short pulses; mixture looks like wet sand, not a paste yet.",
            "technical_terms": ["Pulse"],
        },
        {
            "step_number": 3,
            "timestamp_sec": 120,
            "instruction": "With the machine running, slowly drizzle olive oil to form an emulsion.",
            "visual_context": "Thin stream of oil hits the spinning blade; mixture becomes glossy.",
            "technical_terms": ["Emulsion"],
        },
    ],
    "dietary_summary": "Contains dairy (Parmesan); offer vegan substitute if needed.",
}


@trace_calls
def get_sample_recipe() -> RecipeModel:
    """Return the built-in demo recipe used for dry-run parsing tests."""

    return RecipeModel.model_validate(SAMPLE_RECIPE_DICT)


def _parse_prompt(source_label: str, source_body: str, user_context: str = "") -> str:
    """Build the instruction text sent with video or transcript content."""

    context_block = f"\nUser Dietary Profile:\n{user_context}\n" if user_context else ""

    return f"""You are Crave's recipe extraction engine. {source_label}.
{context_block}
Extract a complete recipe as JSON matching this structure:
- recipe_name: string
- source_url: string (use the URL provided in the user message if applicable)
- ingredients: list of {{item, amount, dietary_conflict (bool), suggested_substitute (string)}}
- steps: list of {{step_number (int from 1), timestamp_sec (int, estimate from video/transcript if unknown use 0), instruction, visual_context (vivid for a blind cook), technical_terms (list of strings)}}
- dietary_summary: one short string

Rules:
- Every step must have rich visual_context for voice assistance.
- Flag dietary_conflict true for common allergens or restrictions when relevant.
- If the content is not a cooking video, still produce a plausible minimal recipe or explain in dietary_summary — prefer real content from the source.

Source content follows:
---
{source_body}
---
"""


@trace_calls
def parse_youtube_to_recipe(youtube_url: str, *, profile: UserProfile | None = None, dry_run: bool = False) -> RecipeModel:
    """
    Parse a YouTube URL into a ``RecipeModel`` using Gemini with JSON schema.

    Args:
        youtube_url: Full https watch or youtu.be URL.
        dry_run: If True, skip all network GenAI calls and return ``SAMPLE_RECIPE``.

    Returns:
        Validated ``RecipeModel``.

    Raises:
        ValueError: On empty URL, invalid JSON from the model, or validation errors.
        RuntimeError: If the API key is missing (via client factory).
    """

    if dry_run:
        log_genai_event(
            "parse_youtube_skipped_dry_run",
            model=None,
            prompt_summary=youtube_url,
            config={"dry_run": True},
            output_summary={"recipe_name": SAMPLE_RECIPE_DICT["recipe_name"]},
        )
        return get_sample_recipe()

    settings = get_settings()
    client = get_genai_client()
    schema = RecipeModel.model_json_schema()

    user_context = ""
    if profile:
        prefs = profile.dietary_preferences
        flags = []
        if getattr(prefs, "vegan", False): flags.append("Vegan")
        if getattr(prefs, "gluten_free", False): flags.append("Gluten-Free")
        if getattr(prefs, "dairy_free", False): flags.append("Dairy-Free")
        if getattr(prefs, "nut_free", False): flags.append("Nut-Free")
        allergies = getattr(profile, "other_allergies", [])
        if flags or allergies:
            user_context = "The user has the following dietary restrictions:\n"
            if flags:
                user_context += f"- Preferences: {', '.join(flags)}\n"
            if allergies:
                user_context += f"- Allergies: {', '.join(allergies)}\n"
            user_context += "\nYou MUST flag any ingredient conflicting with these as `dietary_conflict=true` and provide a safe `suggested_substitute` tailored to these restrictions."

    video_parts = [
        types.Part(
            text=_parse_prompt(
                "The user attached a YouTube video by URL.",
                f"YouTube URL: {youtube_url}",
                user_context=user_context,
            ),
        ),
        types.Part(
            file_data=types.FileData(
                file_uri=str(youtube_url),
                mime_type="video/mp4",
            ),
        ),
    ]

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.2,
    )

    log_genai_event(
        "parse_youtube_attempt_video",
        model=settings.gemini_recipe_model,
        prompt_summary=video_parts[0].text,
        config=config.model_dump(mode="json", exclude_none=True),
        output_summary=None,
    )

    text_out: str | None = None
    try:
        resp = client.models.generate_content(
            model=settings.gemini_recipe_model,
            contents=[
                types.Content(
                    role="user",
                    parts=video_parts,
                ),
            ],
            config=config,
        )
        text_out = resp.text
        log_genai_event(
            "parse_youtube_video_response",
            model=settings.gemini_recipe_model,
            prompt_summary=None,
            config=None,
            output_summary=text_out,
        )
    except Exception as exc:  # noqa: BLE001 — fallback path
        log_genai_event(
            "parse_youtube_video_failed",
            model=settings.gemini_recipe_model,
            prompt_summary=str(youtube_url),
            config=None,
            output_summary={"error": str(exc)},
        )
        transcript = _transcript_text(youtube_url)
        prompt = _parse_prompt(
            "The video could not be read directly; use this transcript.",
            f"URL: {youtube_url}\n\nTranscript:\n{transcript}",
            user_context=user_context,
        )
        log_genai_event(
            "parse_youtube_transcript_attempt",
            model=settings.gemini_recipe_model,
            prompt_summary=prompt,
            config=config.model_dump(mode="json", exclude_none=True),
            output_summary=None,
        )
        resp = client.models.generate_content(
            model=settings.gemini_recipe_model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        text_out = resp.text
        log_genai_event(
            "parse_youtube_transcript_response",
            model=settings.gemini_recipe_model,
            prompt_summary=None,
            config=None,
            output_summary=text_out,
        )

    if not text_out:
        raise ValueError("Empty model response")

    try:
        data = json.loads(text_out)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned non-JSON: {exc}") from exc

    return RecipeModel.model_validate(data)
