"""
Logging helpers for Crave.

Provides structured info-level logs for every public function entry (with
sanitized arguments) and dedicated helpers to log Generative AI requests and
responses with inline/binary payload fields redacted so logs stay readable
and safer to share.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

logger = logging.getLogger("crave")

F = TypeVar("F", bound=Callable[..., Any])


def _truncate(s: str, max_len: int = 2000) -> str:
    """Shorten long strings for log lines."""

    if len(s) <= max_len:
        return s
    return s[:max_len] + f"...<truncated {len(s) - max_len} chars>"


def sanitize_for_log(obj: Any, depth: int = 0) -> Any:
    """
    Recursively copy structures for logging, stripping large or binary fields.

    Replaces keys whose names suggest inline data (e.g. ``data``, ``bytes``,
    ``inline_data``) with a placeholder. Limits recursion depth.
    """

    if depth > 12:
        return "<max depth>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _truncate(obj, 1500)
    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in (
                "data",
                "bytes",
                "blob",
                "inline_data",
                "inlinedata",
                "audio",
                "video",
                "image",
            ):
                out[str(k)] = "<stripped inline>"
            else:
                out[str(k)] = sanitize_for_log(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_log(x, depth + 1) for x in obj[:50]] + (
            ["<truncated list>"] if len(obj) > 50 else []
        )
    return str(type(obj).__name__)


def log_function_call(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Emit an info log line describing a function invocation (sanitized)."""

    try:
        payload = {"args": sanitize_for_log(list(args)), "kwargs": sanitize_for_log(kwargs)}
        logger.info("call %s %s", name, json.dumps(payload, default=str))
    except Exception as exc:  # noqa: BLE001 — logging must not break callers
        logger.info("call %s (serialization failed: %s)", name, exc)


def log_genai_event(
    event: str,
    *,
    model: str | None = None,
    prompt_summary: str | None = None,
    config: Any = None,
    output_summary: Any = None,
) -> None:
    """Log a Generative AI operation with model, prompt/config, and output (sanitized)."""

    body: dict[str, Any] = {"event": event}
    if model:
        body["model"] = model
    if prompt_summary is not None:
        body["prompt"] = _truncate(str(prompt_summary), 4000)
    if config is not None:
        body["config"] = sanitize_for_log(config)
    if output_summary is not None:
        body["output"] = sanitize_for_log(output_summary)
    logger.info("genai %s", json.dumps(body, default=str))


def trace_calls(fn: F) -> F:
    """
    Decorator that logs each invocation of a function (sync or async).

    Uses the wrapped function's ``__name__`` and logs sanitized *args* and
    *kwargs* at info level before executing the body.
    """

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            log_function_call(fn.__name__, args, kwargs)
            return await fn(*args, **kwargs)

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        log_function_call(fn.__name__, args, kwargs)
        return fn(*args, **kwargs)

    return sync_wrapper  # type: ignore[return-value]
