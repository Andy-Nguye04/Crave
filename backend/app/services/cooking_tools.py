"""
Crave sous-chef tool implementations (function calling).

Implements the hackathon tool surface: ``get_step_details``,
``get_ingredient_info``, and ``set_kitchen_timer``. These are invoked from the
Gemini Live session when the model requests structured recipe data or wants to
start a kitchen timer. ``set_kitchen_timer`` does not persist state; it returns
a payload the WebSocket layer forwards to the browser as a UI event.

Use cases:
- Live API ``tool_call`` → execute local function → ``send_tool_response``.
- Optional future REST debugging endpoints mirroring the same handlers.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from app.logging_utils import trace_calls
from app.schemas.recipe import RecipeModel


@trace_calls
def get_step_details(recipe: RecipeModel, step_number: int) -> dict[str, Any]:
    """
    Return instruction and visual cues for a 1-based step index.

    Args:
        recipe: Parsed recipe currently loaded for the session.
        step_number: 1-based step number matching ``StepModel.step_number``.

    Returns:
        Dict with keys ``found``, ``step_number``, ``instruction``,
        ``visual_context``, ``technical_terms``, and ``error`` if not found.
    """

    for step in recipe.steps:
        if step.step_number == step_number:
            return {
                "found": True,
                "step_number": step.step_number,
                "instruction": step.instruction,
                "visual_context": step.visual_context,
                "technical_terms": step.technical_terms,
                "timestamp_sec": step.timestamp_sec,
            }
    return {
        "found": False,
        "error": f"No step {step_number}; recipe has {len(recipe.steps)} steps.",
    }


@trace_calls
def get_ingredient_info(recipe: RecipeModel, item_name: str) -> dict[str, Any]:
    """
    Look up an ingredient by case-insensitive substring match.

    Args:
        recipe: Parsed recipe for the session.
        item_name: Free-text name or fragment from the user.

    Returns:
        Measurement, dietary flags, substitute suggestion, or an error message.
    """

    needle = (item_name or "").strip().lower()
    if not needle:
        return {"found": False, "error": "item_name is empty"}
    for ing in recipe.ingredients:
        if needle in ing.item.lower():
            return {
                "found": True,
                "item": ing.item,
                "amount": ing.amount,
                "dietary_conflict": ing.dietary_conflict,
                "suggested_substitute": ing.suggested_substitute,
            }
    return {
        "found": False,
        "error": f"No ingredient matching '{item_name}'.",
    }


@trace_calls
async def set_kitchen_timer(
    duration_seconds: int,
    *,
    notify: Optional[Callable[[int], Awaitable[None]]] = None,
) -> dict[str, Any]:
    """
    Acknowledge a timer request and optionally notify the WebSocket client.

    Args:
        duration_seconds: Countdown length in seconds (clamped to 1..86400).
        notify: Optional async callback invoked with the same duration for UI.

    Returns:
        A small dict confirming the timer for the model turn.
    """

    sec = max(1, min(int(duration_seconds), 86400))
    if notify is not None:
        await notify(sec)
    return {"ok": True, "duration_seconds": sec, "message": "Timer started in the app UI."}
