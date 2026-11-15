"""Seed a handful of demo slots so the page has something to show.

Usage: python scripts/seed_demo.py [base_url] [api_key]
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010").rstrip("/")
KEY = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("API_KEY", "")

SLOTS = [
    {"id": "a1", "provider": "Dr Ade", "start": "2030-07-01T09:00:00Z", "end": "2030-07-01T09:30:00Z"},
    {"id": "a2", "provider": "Dr Ade", "start": "2030-07-01T10:00:00Z", "end": "2030-07-01T10:30:00Z"},
    {"id": "a3", "provider": "Dr Bello", "start": "2030-07-01T11:00:00Z", "end": "2030-07-01T11:30:00Z"},
    {"id": "b1", "provider": "Dr Bello", "start": "2030-07-02T09:00:00Z", "end": "2030-07-02T09:30:00Z"},
    {"id": "b2", "provider": "Dr Ade", "start": "2030-07-02T14:00:00Z", "end": "2030-07-02T14:30:00Z"},
    {"id": "old", "provider": "Dr Ade", "start": "2020-01-01T09:00:00Z", "end": "2020-01-01T09:30:00Z"},
]


def main() -> int:
    if not KEY:
        print("no API key: pass one as the second argument or set API_KEY", file=sys.stderr)
        return 2
    request = urllib.request.Request(
        BASE + "/reset",
        data=json.dumps({"slots": SLOTS}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": KEY},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(f"{response.status} {response.read().decode()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
