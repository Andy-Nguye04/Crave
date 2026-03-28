"""
Gemini Live WebSocket bridge for hands-free cooking.

Browser connects to ``/ws/cooking/{session_id}`` after a recipe exists in the
in-memory store. Each client message with ``type: user_text`` is forwarded to
the Live model using ``send_client_content``. Server pushes ``model_text``,
transcription fragments, ``tool_call`` summaries, and ``kitchen_timer`` events.

Use cases:
- Demo the hackathon "Live Sous-Chef" with TEXT modality (no raw audio proxy).
- Execute ``get_step_details``, ``get_ingredient_info``, ``set_kitchen_timer``
  against the session recipe and return tool responses to Gemini.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.genai import types

from app.config import get_settings
from app.logging_utils import log_genai_event, log_function_call, sanitize_for_log
from app.schemas.recipe import RecipeModel
from app.services.cooking_tools import (
    get_ingredient_info,
    get_step_details,
    set_kitchen_timer,
)
from app.services.genai_client import get_genai_client
from app.services.live_tool_declarations import crave_live_tools
from app.services.recipe_store import get_session

logger = logging.getLogger("crave")
router = APIRouter(tags=["cooking-ws"])


def _system_instruction(recipe: RecipeModel) -> str:
    """Build the Crave sous-chef system prompt including serialized recipe context."""

    ing_preview = ", ".join(f"{i.item} ({i.amount})" for i in recipe.ingredients[:12])
    if len(recipe.ingredients) > 12:
        ing_preview += ", …"
    return f"""You are the Crave Sous-Chef. You are helping a user cook a specific recipe parsed
from a video. You have access to get_step_details, get_ingredient_info, and set_kitchen_timer.
Be concise, encouraging, and wait for user confirmation before moving to the next step.
If a user asks a question about a technique, explain it simply. If they sound rushed, slow down your pace.
Offer substitution ideas when dietary conflicts or missing ingredients come up.

Recipe: {recipe.recipe_name}
Source: {recipe.source_url}
Dietary summary: {recipe.dietary_summary}
Ingredients: {ing_preview}
Total steps: {len(recipe.steps)}.
"""


async def _execute_tool_call(
    fc: types.FunctionCall,
    recipe: RecipeModel,
    notify_timer,
) -> dict[str, Any]:
    """Dispatch one Live function call to Python handlers and return the result dict."""

    name = fc.name or ""
    args = fc.args or {}
    log_function_call(
        "_execute_tool_call",
        (),
        {"function": name, "args": sanitize_for_log(args)},
    )
    if name == "get_step_details":
        step_number = int(args.get("step_number", 0))
        return get_step_details(recipe, step_number)
    if name == "get_ingredient_info":
        item_name = str(args.get("item_name", ""))
        return get_ingredient_info(recipe, item_name)
    if name == "set_kitchen_timer":
        duration = int(args.get("duration_seconds", 0))
        return await set_kitchen_timer(duration, notify=notify_timer)
    return {"error": f"Unknown tool {name}"}


async def _forward_server_message(
    websocket: WebSocket,
    gemini_msg: types.LiveServerMessage,
) -> None:
    """Send relevant fragments of a Live server message to the browser as JSON."""

    if gemini_msg.tool_call and gemini_msg.tool_call.function_calls:
        calls = [
            {"name": c.name, "args": sanitize_for_log(c.args or {})}
            for c in gemini_msg.tool_call.function_calls
        ]
        await websocket.send_json({"type": "tool_call", "calls": calls})

    sc = gemini_msg.server_content
    if sc:
        if sc.input_transcription and sc.input_transcription.text:
            await websocket.send_json(
                {
                    "type": "transcription",
                    "role": "user",
                    "text": sc.input_transcription.text,
                },
            )
        if sc.output_transcription and sc.output_transcription.text:
            await websocket.send_json(
                {
                    "type": "transcription",
                    "role": "model",
                    "text": sc.output_transcription.text,
                },
            )

    if gemini_msg.text:
        await websocket.send_json({"type": "model_text", "text": gemini_msg.text})


async def _drain_model_turn(
    session: Any,
    websocket: WebSocket,
    recipe: RecipeModel,
    notify_timer,
) -> None:
    """
    Consume one full model turn from ``session.receive()``, including tool calls.

    Handles ``tool_call`` by executing local tools and ``send_tool_response`` until the turn completes.
    """

    async for gemini_msg in session.receive():
        await _forward_server_message(websocket, gemini_msg)

        if gemini_msg.tool_call and gemini_msg.tool_call.function_calls:
            responses: list[types.FunctionResponse] = []
            for fc in gemini_msg.tool_call.function_calls:
                if not fc.id:
                    logger.warning("tool call missing id: %s", fc.name)
                    continue
                result = await _execute_tool_call(fc, recipe, notify_timer)
                log_genai_event(
                    "live_tool_result",
                    model=None,
                    prompt_summary=fc.name,
                    config=sanitize_for_log(fc.args or {}),
                    output_summary=result,
                )
                responses.append(
                    types.FunctionResponse(
                        name=fc.name or "unknown",
                        id=fc.id,
                        response=result,
                    ),
                )
            if responses:
                await session.send_tool_response(function_responses=responses)


@router.websocket("/ws/cooking/{session_id}")
async def cooking_live_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint bridging the browser to Gemini Live (TEXT modality).

    Args:
        websocket: Starlette WebSocket connection.
        session_id: Existing recipe session from the parse endpoint.

    Client protocol (JSON):
        - ``{{"type": "user_text", "text": "..."}}`` — user message to the chef.

    Server events (JSON):
        - ``live_ready`` — Live session established.
        - ``model_text`` — concatenated text from the model turn.
        - ``transcription`` — optional ASR fragments.
        - ``tool_call`` — model requested tools (sanitized args).
        - ``kitchen_timer`` — timer UI event after ``set_kitchen_timer``.
        - ``error`` — human-readable failure.
    """

    await websocket.accept()
    log_function_call("cooking_live_websocket", (), {"session_id": session_id})

    stored = get_session(session_id)
    if stored is None:
        await websocket.send_json({"type": "error", "message": "Unknown session_id"})
        await websocket.close(code=4404)
        return

    settings = get_settings()
    try:
        client = get_genai_client()
    except ValueError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=4401)
        return

    recipe = stored.recipe
    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=_system_instruction(recipe),
        tools=crave_live_tools(),
    )

    log_genai_event(
        "live_connect",
        model=settings.gemini_live_model,
        prompt_summary=_system_instruction(recipe),
        config=sanitize_for_log(config.model_dump(mode="json", exclude_none=True)),
        output_summary=None,
    )

    async def notify_timer(seconds: int) -> None:
        """Push a timer event to the same WebSocket client."""

        await websocket.send_json(
            {"type": "kitchen_timer", "duration_seconds": seconds},
        )

    try:
        async with client.aio.live.connect(
            model=settings.gemini_live_model,
            config=config,
        ) as session:
            await websocket.send_json({"type": "live_ready"})
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {"type": "error", "message": "Invalid JSON"},
                    )
                    continue
                if payload.get("type") != "user_text":
                    continue
                text = str(payload.get("text", "")).strip()
                if not text:
                    continue
                log_genai_event(
                    "live_user_text",
                    model=settings.gemini_live_model,
                    prompt_summary=text,
                    config=None,
                    output_summary=None,
                )
                await session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=text)],
                    ),
                    turn_complete=True,
                )
                await _drain_model_turn(session, websocket, recipe, notify_timer)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected session_id=%s", session_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Live session error")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
