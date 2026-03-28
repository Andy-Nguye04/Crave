# Crave — design and features (hackathon)

This document describes what the repository implements for the hackathon MVP: YouTube ingestion, structured recipe JSON, and a Gemini Live (TEXT) WebSocket bridge for the sous-chef tools.

## Architecture

- **Frontend** (`frontend/`): static HTML + Tailwind. Pages are meant to be served over **HTTP** (not `file://`) so browser `fetch` and `WebSocket` work. Use VS Code Live Server, `python -m http.server`, or any static host.
- **Backend** (`backend/`): **FastAPI** + **Uvicorn**, **Google GenAI** (`google-genai`) for:
  - `generate_content` with JSON schema (recipe parsing; YouTube URL as `file_data`, transcript fallback).
  - `aio.live.connect` with **TEXT** modality for the cooking WebSocket (function calling for step/ingredient/timer tools).

Configurable model names and CORS live in `backend/app/config.py` (overridable via environment variables).

## REST API

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/health` | Liveness check |
| POST | `/api/parse-youtube` | Body: `{ "youtube_url": "https://...", "dry_run": false }`. Returns `{ session_id, recipe }`. |
| GET | `/api/recipes/{session_id}` | Returns stored `{ session_id, dry_run, recipe }`. |

## WebSocket

- **URL**: `ws://<host>:<port>/ws/cooking/{session_id}`
- **Client → server**: `{"type": "user_text", "text": "..."}`
- **Server → client** (examples): `live_ready`, `model_text`, `transcription`, `tool_call`, `kitchen_timer`, `error`

Tools implemented server-side: `get_step_details`, `get_ingredient_info`, `set_kitchen_timer` (timer is pushed to the UI as JSON).

## Frontend pages

| File | Role |
|------|------|
| `import.html` | Paste YouTube URL; optional **dry run** (no Gemini); redirects to cooking mode with `?session=`. |
| `cooking-mode.html` | Loads recipe by session; step prev/next; connects Live WebSocket; quick prompts and chef status line. |
| `tracker.html` | Shell UI; **Import** tab links to `import.html`. |

API base URL defaults to `http://127.0.0.1:8000`. Override with `localStorage.setItem('CRAVE_API_BASE', '...')` or `?api=` on the page URL.

## Logging and testing (backend)

- **Function calls**: logged at INFO with sanitized arguments (`app/logging_utils.py`, `trace_calls` decorator on routers/services where used).
- **GenAI**: `log_genai_event` records model, prompt/config, and outputs with inline/binary fields stripped.
- **Dry run**: `POST` with `"dry_run": true` returns a fixed demo recipe (no API key, no quota). CLI: `python scripts/test_parse_dry_run.py` from `backend/`.

## Environment

Copy `backend/.env.example` to `backend/.env` and set `GEMINI_API_KEY` for real parsing and Live chat. Optional: `GEMINI_RECIPE_MODEL`, `GEMINI_LIVE_MODEL`, `CRAVE_CORS_ORIGINS`.
