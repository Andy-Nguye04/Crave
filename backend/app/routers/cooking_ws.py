"""
Gemini Live Audio WebSocket bridge for hands-free cooking.

Browser connects to ``/ws/cooking/{session_id}``. Audio flows bidirectionally:
- Browser sends binary frames (PCM 16-bit 16kHz mono) from the microphone
- Server sends binary frames (PCM 16-bit 24kHz mono) from Gemini's voice
- JSON text frames carry control messages (step_changed, navigate_step, etc.)

Crave (the sous-chef persona) automatically introduces herself on connect and
reads the user through each recipe step using voice. Users speak naturally to
ask questions, request next steps, or get technique explanations.
"""

from __future__ import annotations

import asyncio
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
    """Build the Crave sous-chef system prompt with full recipe context."""

    steps_text = "\n".join(
        f"  Step {s.step_number}: {s.instruction}"
        for s in sorted(recipe.steps, key=lambda s: s.step_number)
    )
    ing_text = "\n".join(
        f"  - {i.item} ({i.amount})"
        + (
            f" -- dietary conflict, swap: {i.suggested_substitute}"
            if i.dietary_conflict
            else ""
        )
        for i in recipe.ingredients
    )

    return f"""You are Crave, a warm and encouraging AI sous-chef guiding a home cook through a recipe step by step using voice.

PERSONALITY:
- Friendly, calm, and confident — like a trusted friend who happens to be a great cook
- Use natural conversational language, not robotic instructions
- Keep responses concise since you are speaking aloud (2-3 sentences max per turn)
- Celebrate small wins ("Nice work!", "That looks great!")

BEHAVIOR:
- When you first connect, warmly greet the user, introduce yourself as Crave, tell them what they are cooking today, and begin reading Step 1
- Read each step's instruction clearly and naturally
- After reading a step, ask the user if they are ready before moving on
- If the user asks about a technique (e.g. "how do I emulsify?"), explain it simply and briefly
- If the user says "next step", "done", "ready", or similar — use the navigate_to_step tool to advance to the next step number, then read the new step
- If you receive a step_changed notification, acknowledge the new step and read its instruction
- Use set_kitchen_timer when timing is mentioned in a step or when the user asks
- Use get_ingredient_info when the user asks about amounts or substitutions
- Use get_step_details to look up specific step information when needed
- When you reach the final step, congratulate the user and let them know they are done

RECIPE CONTEXT:
Name: {recipe.recipe_name}
Source: {recipe.source_url}
Dietary summary: {recipe.dietary_summary}
Total steps: {len(recipe.steps)}

Ingredients:
{ing_text}

Steps:
{steps_text}
"""


async def _execute_tool_call(
    fc: types.FunctionCall,
    recipe: RecipeModel,
    notify_timer,
    notify_navigate,
) -> dict[str, Any]:
    """Dispatch a Live function call and return the result dict."""

    name = fc.name or ""
    args = fc.args or {}
    log_function_call(
        "_execute_tool_call",
        (),
        {"function": name, "args": sanitize_for_log(args)},
    )

    if name == "get_step_details":
        return get_step_details(recipe, int(args.get("step_number", 0)))
    if name == "get_ingredient_info":
        return get_ingredient_info(recipe, str(args.get("item_name", "")))
    if name == "set_kitchen_timer":
        return await set_kitchen_timer(
            int(args.get("duration_seconds", 0)), notify=notify_timer
        )
    if name == "navigate_to_step":
        step_num = int(args.get("step_number", 1))
        await notify_navigate(step_num)
        return {"ok": True, "navigated_to": step_num}
    return {"error": f"Unknown tool {name}"}


@router.websocket("/ws/cooking/{session_id}")
async def cooking_live_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint bridging browser audio to Gemini Live (AUDIO modality).

    Binary frames: PCM audio (browser <-> server).
    Text frames: JSON control messages.

    Client protocol:
        - Binary: raw PCM 16-bit 16kHz mono from microphone
        - ``{{"type": "step_changed", "step_number": N}}`` — user navigated manually

    Server events:
        - Binary: raw PCM 16-bit 24kHz mono from Gemini voice
        - ``live_ready`` — Live session established, Crave is starting
        - ``navigate_step`` — Crave wants to move to a step
        - ``kitchen_timer`` — timer UI event
        - ``tool_call`` — tool usage notification
        - ``error`` — human-readable failure
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
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
            )
        ),
        system_instruction=_system_instruction(recipe),
        tools=crave_live_tools(),
    )

    log_genai_event(
        "live_connect_audio",
        model=settings.gemini_live_model,
        prompt_summary=_system_instruction(recipe)[:200],
        config={"voice": "Kore", "modality": "AUDIO"},
        output_summary=None,
    )

    async def notify_timer(seconds: int) -> None:
        """Push a timer event to the browser."""
        try:
            await websocket.send_json(
                {"type": "kitchen_timer", "duration_seconds": seconds}
            )
        except Exception:
            pass

    async def notify_navigate(step_number: int) -> None:
        """Push a step navigation event to the browser."""
        try:
            await websocket.send_json(
                {"type": "navigate_step", "step_number": step_number}
            )
        except Exception:
            pass

    try:
        async with client.aio.live.connect(
            model=settings.gemini_live_model,
            config=config,
        ) as session:
            await websocket.send_json({"type": "live_ready"})

            # Trigger Crave's self-introduction and Step 1 readthrough
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                "Hi Crave! I just opened the cooking screen. "
                                "Please introduce yourself and walk me through Step 1."
                            )
                        )
                    ],
                ),
                turn_complete=True,
            )

            async def browser_to_gemini() -> None:
                """Forward browser text messages to Gemini (speech-to-text via Web Speech API)."""
                try:
                    while True:
                        message = await websocket.receive()
                        msg_type = message.get("type", "")

                        if msg_type == "websocket.disconnect":
                            logger.info("browser_to_gemini: ws disconnect frame")
                            break

                        # Binary frames are ignored — mic audio is now handled
                        # by Web Speech API in the browser, not raw PCM.

                        # Text frame = JSON control message
                        if "text" in message and message["text"]:
                            try:
                                payload = json.loads(message["text"])
                            except json.JSONDecodeError:
                                continue

                            msg_kind = payload.get("type", "")

                            if msg_kind == "speech_text":
                                user_text = str(payload.get("text", "")).strip()
                                if not user_text:
                                    continue
                                logger.info("Speech text: %s", user_text[:120])
                                await session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[types.Part(text=user_text)],
                                    ),
                                    turn_complete=True,
                                )

                            elif msg_kind == "step_changed":
                                step_num = int(payload.get("step_number", 1))
                                logger.info("Step changed to %d", step_num)
                                await session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[
                                            types.Part(
                                                text=(
                                                    f"I have navigated to step {step_num}. "
                                                    "Please read me through this step."
                                                )
                                            )
                                        ],
                                    ),
                                    turn_complete=True,
                                )
                except WebSocketDisconnect:
                    logger.info("browser_to_gemini: WebSocketDisconnect")
                except Exception:
                    logger.exception("browser_to_gemini error")
                logger.info("browser_to_gemini: task exiting")

            async def gemini_to_browser() -> None:
                """Forward Gemini audio and events to browser."""
                msg_count = 0
                try:
                    # Wrap in while True so the loop survives turn boundaries.
                    # session.receive() may end after each model turn; we
                    # re-enter it to keep listening for the next turn.
                    while True:
                        async for msg in session.receive():
                            msg_count += 1

                            # Audio data from Gemini voice
                            if msg.data:
                                try:
                                    await websocket.send_bytes(msg.data)
                                except Exception:
                                    logger.info(
                                        "gemini_to_browser: browser gone at msg %d",
                                        msg_count,
                                    )
                                    return

                            # Tool calls
                            if msg.tool_call and msg.tool_call.function_calls:
                                tool_names = [
                                    c.name
                                    for c in msg.tool_call.function_calls
                                ]
                                logger.info("Tool calls: %s", tool_names)
                                try:
                                    await websocket.send_json(
                                        {
                                            "type": "tool_call",
                                            "calls": tool_names,
                                        }
                                    )
                                except Exception:
                                    pass

                                responses: list[types.FunctionResponse] = []
                                for fc in msg.tool_call.function_calls:
                                    if not fc.id:
                                        logger.warning(
                                            "tool call missing id: %s", fc.name
                                        )
                                        continue
                                    result = await _execute_tool_call(
                                        fc,
                                        recipe,
                                        notify_timer,
                                        notify_navigate,
                                    )
                                    log_genai_event(
                                        "live_tool_result",
                                        model=None,
                                        prompt_summary=fc.name,
                                        config=sanitize_for_log(
                                            fc.args or {}
                                        ),
                                        output_summary=result,
                                    )
                                    responses.append(
                                        types.FunctionResponse(
                                            name=fc.name or "unknown",
                                            id=fc.id,
                                            response=result,
                                        )
                                    )
                                if responses:
                                    await session.send_tool_response(
                                        function_responses=responses
                                    )

                        # Generator ended (turn boundary) — re-enter
                        logger.info(
                            "Gemini turn ended at msg %d, re-entering receive loop",
                            msg_count,
                        )
                except Exception:
                    logger.exception(
                        "gemini_to_browser error after %d msgs", msg_count
                    )
                logger.info("gemini_to_browser: task exiting")

            # Run both directions concurrently
            logger.info("Starting browser<->gemini bridge tasks")
            tasks = [
                asyncio.create_task(browser_to_gemini()),
                asyncio.create_task(gemini_to_browser()),
            ]
            _done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            done_names = []
            for t in _done:
                exc = t.exception()
                done_names.append(f"exc={exc}" if exc else "ok")
            logger.info(
                "Bridge tasks: done=%s, cancelling %d pending",
                done_names,
                len(pending),
            )
            for t in pending:
                t.cancel()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected session_id=%s", session_id)
    except Exception:
        logger.exception("Live audio session error")
        try:
            await websocket.send_json(
                {"type": "error", "message": "Live session failed"}
            )
        except Exception:
            pass
