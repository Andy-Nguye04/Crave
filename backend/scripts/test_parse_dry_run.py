#!/usr/bin/env python3
"""
CLI smoke test for parse + recipe fetch without calling Gemini or mutating real data.

Uses FastAPI TestClient so no server process is required. Default ``--dry-run``
exercises the full HTTP stack with a fixture recipe only.

Usage (from ``backend/``)::

    python scripts/test_parse_dry_run.py
    python scripts/test_parse_dry_run.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow ``python scripts/test_parse_dry_run.py`` from backend/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    """Parse CLI flags and run the in-process HTTP smoke test."""

    parser = argparse.ArgumentParser(description="Crave parse API dry-run test")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Use dry_run=true (default: on)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Call real Gemini (requires GEMINI_API_KEY); uses a public YouTube URL",
    )
    args = parser.parse_args()
    dry = not args.no_dry_run

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    r = client.post(
        "/api/parse-youtube",
        json={"youtube_url": url, "dry_run": dry},
    )
    if r.status_code != 200:
        print("parse failed", r.status_code, r.text)
        return 1
    body = r.json()
    sid = body["session_id"]
    r2 = client.get(f"/api/recipes/{sid}")
    if r2.status_code != 200:
        print("get recipe failed", r2.status_code, r2.text)
        return 1
    print("OK session_id=", sid)
    print("recipe_name=", r2.json()["recipe"]["recipe_name"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
