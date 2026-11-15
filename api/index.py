"""Vercel entry point.

Vercel's Python runtime looks for an ASGI application called `app` in this file.
The repository root has to be importable before `app` is imported.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

__all__ = ["app"]
