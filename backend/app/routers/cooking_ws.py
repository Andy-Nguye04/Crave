"""
Gemini Live WebSocket bridge for hands-free cooking.

Browser connects to ``/ws/cooking/{session_id}`` after a recipe exists in the
in-memory store. Each ``user_text`` client message is sent with
``send_realtime_input(text=...)``. The Live session uses AUDIO response modality
plus ``output_audio_transcription`` so the UI still gets text (native Live models
reject TEXT-only ``response_modalities`` with WS 1007).

Server pushes ``model_text`` (when present), ``model_audio`` (base64 PCM from
the Live model for browser playback), ``transcription`` (including model output
transcript), ``tool_call`` summaries, ``kitchen_timer`` events, and
``step_navigate`` when the model advances or goes back a step in the UI.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.genai import types
from google.genai.errors import APIError as GenaiAPIError
from websockets.exceptions import ConnectionClosed as WsConnectionClosed

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

# region agent log
def _agent_debug_ndjson(payload: dict[str, Any]) -> None:
    """Append one NDJSON line for debug session (workspace log)."""

    try:
        log_path = Path(__file__).resolve().parents[3] / "debug-36a370.log"
        row = {
            "sessionId": "36a370",
            "timestamp": int(time.time() * 1000),
            **payload,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


# endregion


def _system_instruction(recipe: RecipeModel) -> str:
    """Build the Crave sous-chef system prompt including serialized recipe context."""

    ing_preview = ", ".join(f"{i.item} ({i.amount})" for i in recipe.ingredients[:12])
    if len(recipe.ingredients) > 12:
        ing_preview += ", …"
    return f"""You are the Crave Sous-Chef. You are helping a user cook a specific recipe parsed
from a video. Be concise, encouraging, and wait for user confirmation before moving to the next step.
If a user asks about a technique, explain it simply.

You may call: get_step_details(step_number), get_ingredient_info(item_name), set_kitchen_timer(duration_seconds),
and navigate_recipe_step (direction "next" or "previous") to match the on-screen step. Use "previous"/"next"
only when the user wants to change steps; to repeat or re-explain the current step, use get_step_details,
not "previous". Suggest substitutions when dietary conflicts or missing ingredients come up.

Recipe: {recipe.recipe_name}
Source: {recipe.source_url}
Dietary summary: {recipe.dietary_summary}
Ingredients: {ing_preview}
Total steps: {len(recipe.steps)}.

User messages may include UI fields (step_number, ui_step_index, total_steps). Treat step_number as the
canonical recipe step for get_step_details when they mean "this step" or the current screen.
For long or missing details, call get_step_details(step_number) — do not assume the UI sent full text.
"""

# Large send_realtime_input payloads correlate with upstream Live WS aborts (1008) after tool calls.
_LIVE_USER_TURN_MAX_CHARS = 6144


def _clip_live_field(s: str, max_len: int) -> str:
    """Shorten a field for send_realtime_input; keeps Live sessions within policy limits."""

    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _augment_user_text_with_ui_step(
    text: str,
    payload: dict[str, Any],
    recipe: RecipeModel,
) -> str:
    """Prepend lightweight UI step hints; model should call get_step_details for full step text."""

    raw_sn = payload.get("step_number")
    raw_ui = payload.get("ui_step_index")
    raw_tot = payload.get("total_steps")
    if raw_sn is None and raw_ui is None:
        return text

    step_number: int | None = None
    if raw_sn is not None:
        try:
            step_number = int(raw_sn)
        except (TypeError, ValueError):
            step_number = None

    ui_idx: int | None = None
    if raw_ui is not None:
        try:
            ui_idx = int(raw_ui)
        except (TypeError, ValueError):
            ui_idx = None

    total: int | None = None
    if raw_tot is not None:
        try:
            total = int(raw_tot)
        except (TypeError, ValueError):
            total = None

    if step_number is None and ui_idx is None:
        return text

    bits: list[str] = []
    if step_number is not None:
        bits.append(
            f"recipe step_number={step_number} (on-screen step — call get_step_details({step_number}) for text)",
        )
    if ui_idx is not None and total is not None and total > 0:
        bits.append(f"step list {ui_idx} of {total}")
    elif ui_idx is not None:
        bits.append(f"step list position {ui_idx}")

    if step_number is None and ui_idx is not None and recipe.steps:
        ordered = sorted(recipe.steps, key=lambda s: s.step_number or 0)
        if 1 <= ui_idx <= len(ordered):
            sn = ordered[ui_idx - 1].step_number
            if sn is not None:
                try:
                    step_number = int(sn)
                except (TypeError, ValueError):
                    step_number = None

    parts: list[str] = []
    if bits:
        parts.append("[Crave UI — user focus: " + "; ".join(bits) + "]")

    if not parts:
        return text
    out = "\n".join(parts) + "\n\n" + text
    if len(out) > _LIVE_USER_TURN_MAX_CHARS:
        head = "\n".join(parts) + "\n\n"
        budget = max(0, _LIVE_USER_TURN_MAX_CHARS - len(head) - 30)
        clipped = _clip_live_field(text, budget) if budget else ""
        return head + clipped + "\n[clipped]"
    return out


def _pcm_audio_chunks_from_live_message(
    gemini_msg: types.LiveServerMessage,
) -> list[tuple[bytes, str]]:
    """Extract inline PCM/audio bytes from a Live server message (native audio output)."""

    sc = gemini_msg.server_content
    if not sc or not sc.model_turn or not sc.model_turn.parts:
        return []
    out: list[tuple[bytes, str]] = []
    for part in sc.model_turn.parts:
        if not part.inline_data or not part.inline_data.data:
            continue
        raw = part.inline_data.data
        if not isinstance(raw, bytes) or not raw:
            continue
        mime = (part.inline_data.mime_type or "").strip().lower()
        if "audio" in mime or "pcm" in mime or mime.startswith("audio/"):
            out.append(
                (
                    raw,
                    part.inline_data.mime_type or "audio/pcm;rate=24000",
                ),
            )
    if not out:
        bulk = gemini_msg.data
        if isinstance(bulk, bytes) and len(bulk) >= 2:
            out.append((bulk, "audio/pcm;rate=24000"))
    return out


# ``session.receive()`` ends one SDK "cycle" when the server marks turn_complete. Some
# Live sessions emit that flag on input transcription alone before model audio; one
# cycle then has no model_turn. Pull another receive() cycle without new user text.
_LIVE_RECEIVE_MAX_PASSES = 6
_LIVE_RECEIVE_RETRY_TIMEOUT_S = 18.0


def _live_message_has_model_substance(gemini_msg: types.LiveServerMessage) -> bool:
    """True if the message carries model output or a tool call (not user ASR alone)."""

    if gemini_msg.tool_call and gemini_msg.tool_call.function_calls:
        return True
    if gemini_msg.text:
        return True
    if _pcm_audio_chunks_from_live_message(gemini_msg):
        return True
    sc = gemini_msg.server_content
    if sc and sc.model_turn and sc.model_turn.parts:
        return True
    if sc and sc.output_transcription and sc.output_transcription.text:
        return True
    return False


async def _execute_tool_call(
    fc: types.FunctionCall,
    recipe: RecipeModel,
    notify_timer,
    notify_step,
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
    if name == "navigate_recipe_step":
        direction = str(args.get("direction", "")).lower().strip()
        if direction not in ("next", "previous"):
            return {
                "ok": False,
                "error": "direction must be 'next' or 'previous'",
            }
        await notify_step(direction)
        return {"ok": True, "direction": direction}
    return {"error": f"Unknown tool {name}"}


async def _forward_server_message(
    websocket: WebSocket,
    gemini_msg: types.LiveServerMessage,
    *,
    on_model_transcript: Callable[[str], None] | None = None,
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
            ot = sc.output_transcription.text
            if on_model_transcript:
                on_model_transcript(ot)
            await websocket.send_json(
                {
                    "type": "transcription",
                    "role": "model",
                    "text": ot,
                },
            )

    if gemini_msg.text:
        if on_model_transcript:
            on_model_transcript(gemini_msg.text)
        await websocket.send_json({"type": "model_text", "text": gemini_msg.text})

    for pcm, mime_type in _pcm_audio_chunks_from_live_message(gemini_msg):
        await websocket.send_json(
            {
                "type": "model_audio",
                "mime_type": mime_type,
                "data": base64.b64encode(pcm).decode("ascii"),
            },
        )


async def _drain_one_receive_cycle(
    session: Any,
    websocket: WebSocket,
    recipe: RecipeModel,
    notify_timer,
    notify_step,
    *,
    on_model_transcript: Callable[[str], None] | None = None,
) -> tuple[bool, bool]:
    """
    Run one ``session.receive()`` until the SDK ends the cycle.

    Returns:
        (had_model_substance, sent_tool_response) — tool flag is True if
        ``send_tool_response`` was used at least once this cycle.
    """

    had_model_substance = False
    sent_tool_response = False
    async for gemini_msg in session.receive():
        if _live_message_has_model_substance(gemini_msg):
            had_model_substance = True
        await _forward_server_message(
            websocket,
            gemini_msg,
            on_model_transcript=on_model_transcript,
        )

        if gemini_msg.tool_call and gemini_msg.tool_call.function_calls:
            responses: list[types.FunctionResponse] = []
            for fc in gemini_msg.tool_call.function_calls:
                if not fc.id:
                    logger.warning("tool call missing id: %s", fc.name)
                    continue
                result = await _execute_tool_call(
                    fc,
                    recipe,
                    notify_timer,
                    notify_step,
                )
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
                sent_tool_response = True

    return had_model_substance, sent_tool_response


async def _drain_model_turn(
    session: Any,
    websocket: WebSocket,
    recipe: RecipeModel,
    notify_timer,
    notify_step,
    *,
    on_model_transcript: Callable[[str], None] | None = None,
) -> None:
    """
    Consume model output for one user send, including tool rounds.

    The GenAI client ends each ``receive()`` cycle on ``turn_complete``. When that
    arrives on input-only payloads, run another cycle (without new user text) so
    model audio/transcription is not dropped.
    """

    for attempt in range(_LIVE_RECEIVE_MAX_PASSES):
        cycle = _drain_one_receive_cycle(
            session,
            websocket,
            recipe,
            notify_timer,
            notify_step,
            on_model_transcript=on_model_transcript,
        )
        if attempt == 0:
            had_sub, did_tools = await cycle
        else:
            try:
                had_sub, did_tools = await asyncio.wait_for(
                    cycle,
                    timeout=_LIVE_RECEIVE_RETRY_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Live receive pass %s timed out after %.1fs",
                    attempt + 1,
                    _LIVE_RECEIVE_RETRY_TIMEOUT_S,
                )
                return
        if had_sub:
            return
        if did_tools:
            continue
    logger.warning(
        "Live drain finished without model audio/text after %s receive cycles",
        _LIVE_RECEIVE_MAX_PASSES,
    )


@router.websocket("/ws/cooking/{session_id}")
async def cooking_live_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint bridging the browser to Gemini Live (AUDIO modality with
    output transcription surfaced as text events to the UI).

    Args:
        websocket: Starlette WebSocket connection.
        session_id: Existing recipe session from the parse endpoint.

    Client protocol (JSON):
        - ``{{"type": "user_text", "text": "..."}}`` — user message to the chef.
        - Optional: ``step_number`` (recipe step id), ``ui_step_index`` (1-based index in the
          sorted step list), ``total_steps`` — merged into the user turn so the model knows
          which step is on screen.

    Server events (JSON):
        - ``live_ready`` — Live session established.
        - ``model_text`` — concatenated text from the model turn.
        - ``model_audio`` — base64-encoded PCM chunk; ``mime_type`` may include ``rate=``.
        - ``transcription`` — optional ASR fragments.
        - ``tool_call`` — model requested tools (sanitized args).
        - ``kitchen_timer`` — timer UI event after ``set_kitchen_timer``.
        - ``step_navigate`` — ``{{"direction": "next"|"previous"}}`` after ``navigate_recipe_step``.
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
    # Native Live models expect AUDIO response modality; TEXT-only causes WS 1007
    # ("Cannot extract voices from a non-audio request"). We stream the spoken
    # reply as text to the browser via output_audio_transcription.
    #
    # Do not set automatic_activity_detection disabled + activity_start/end here:
    # Google Live returns WS 1007 "Precondition check failed" for that combo with
    # gemini-3.1-flash-live-preview (see crave logs on user_text).
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=_system_instruction(recipe),
        tools=crave_live_tools(),
    )

    log_genai_event(
        "live_connect",
        model=settings.crave_gemini_live_model,
        prompt_summary=_system_instruction(recipe),
        config=sanitize_for_log(config.model_dump(mode="json", exclude_none=True)),
        output_summary=None,
    )

    async def notify_timer(seconds: int) -> None:
        """Push a timer event to the same WebSocket client."""

        await websocket.send_json(
            {"type": "kitchen_timer", "duration_seconds": seconds},
        )

    async def notify_step(direction: str) -> None:
        """Tell the client to move one step forward or back in the recipe UI."""

        await websocket.send_json({"type": "step_navigate", "direction": direction})

    live_aborted = False
    model_transcript_tail: dict[str, str] = {"v": ""}

    def _append_model_transcript(fragment: str) -> None:
        s = (model_transcript_tail["v"] + " " + fragment).strip()
        model_transcript_tail["v"] = s[-1200:] if len(s) > 1200 else s

    try:
        async with client.aio.live.connect(
            model=settings.crave_gemini_live_model,
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
                tail_lc = model_transcript_tail["v"].lower()
                u_lc = text.lower()
                if len(u_lc) >= 14 and tail_lc and u_lc in tail_lc:
                    # region agent log
                    _agent_debug_ndjson(
                        {
                            "hypothesisId": "H-echo",
                            "location": "cooking_ws:user_text",
                            "message": "user_plain_substring_of_recent_model_transcript",
                            "data": {
                                "user_len": len(text),
                                "tail_len": len(model_transcript_tail["v"]),
                            },
                        },
                    )
                    # endregion
                turn_text = _augment_user_text_with_ui_step(text, payload, recipe)
                log_genai_event(
                    "live_user_text",
                    model=settings.crave_gemini_live_model,
                    prompt_summary=turn_text,
                    config=sanitize_for_log(
                        {
                            "step_number": payload.get("step_number"),
                            "ui_step_index": payload.get("ui_step_index"),
                            "total_steps": payload.get("total_steps"),
                        },
                    ),
                    output_summary=None,
                )
                # Gemini 3.x Live rejects mid-session send_client_content (1007).
                try:
                    await session.send_realtime_input(text=turn_text)
                    await _drain_model_turn(
                        session,
                        websocket,
                        recipe,
                        notify_timer,
                        notify_step,
                        on_model_transcript=_append_model_transcript,
                    )
                except (GenaiAPIError, WsConnectionClosed) as live_exc:
                    logger.warning(
                        "Gemini Live session aborted (upstream closed or API error): %s",
                        live_exc,
                    )
                    live_aborted = True
                    try:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": (
                                    "Live chef session ended. The page will try to reconnect; "
                                    "or refresh if it stays quiet."
                                ),
                            },
                        )
                    except Exception:
                        pass
                    break
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected session_id=%s", session_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Live session error")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if live_aborted:
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
