"""Black-box conformance checks for the clinic booking API.

Usage:
    python scripts/smoke.py [base_url] [api_key]

Defaults to http://127.0.0.1:8010 and the API_KEY from .env, so it runs against
a local server or a deployed one unchanged. Exits non-zero if anything fails.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SMOKE_BASE", "http://127.0.0.1:8010")).rstrip("/")
KEY = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("API_KEY", "")


class Response:
    def __init__(self, status: int, headers: dict, body):
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body

    def __repr__(self) -> str:
        return f"<{self.status} {self.body!r}>"


def call(method: str, path: str, body=None, headers: dict | None = None, key: bool = True) -> Response:
    payload = None
    hdrs = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    if key and "X-API-Key" not in hdrs:
        hdrs["X-API-Key"] = KEY
    request = urllib.request.Request(BASE + path, data=payload, headers=hdrs, method=method)
    return _send(request)


def call_raw(method: str, path: str, payload: bytes) -> Response:
    request = urllib.request.Request(
        BASE + path, data=payload, headers={"Content-Type": "application/json", "X-API-Key": KEY}, method=method
    )
    return _send(request)


def _send(request: urllib.request.Request) -> Response:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = response.status
            headers = dict(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        headers = dict(exc.headers)
    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = raw.decode("utf-8", "replace")
    return Response(status, headers, body)


FAILURES: list[str] = []
CHECKS = 0


def check(name: str, condition: bool, detail=None) -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  ok   {name}")
        return
    FAILURES.append(name)
    print(f"  FAIL {name}")
    if detail is not None:
        print(f"       got: {detail}")


def equal(name: str, actual, expected) -> None:
    check(name, actual == expected, f"{actual!r} != {expected!r}")


def section(title: str) -> None:
    print(f"\n{title}")


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #


def check_auth() -> None:
    section("level 2: api key")
    equal("GET /slots without a key is 401", call("GET", "/slots", key=False).status, 401)
    wrong = call("GET", "/slots", headers={"X-API-Key": "definitely-wrong"})
    equal("GET /slots with a wrong key is 401", wrong.status, 401)
    check("401 body is {error}", isinstance(wrong.body, dict) and "error" in wrong.body, wrong.body)
    equal("POST /reset without a key is 401", call("POST", "/reset", {"slots": []}, key=False).status, 401)


def check_reset() -> None:
    section("level 1: reset")
    response = call(
        "POST",
        "/reset",
        {
            "slots": [
                {"id": "s1", "provider": "Dr Ade", "start": "2030-01-10T09:00:00Z", "end": "2030-01-10T09:30:00Z"},
                {"id": "s2", "provider": "Dr Ade", "start": "2030-01-10T10:00:00Z", "end": "2030-01-10T10:30:00Z"},
                {"id": "s3", "provider": "Dr Bello", "start": "2030-01-11T09:00:00Z", "end": "2030-01-11T09:30:00Z"},
            ]
        },
    )
    equal("POST /reset is 200", response.status, 200)

    listing = call("GET", "/slots")
    equal("GET /slots is 200", listing.status, 200)
    slots = listing.body.get("slots", [])
    equal("all seeded slots are listed", len(slots), 3)
    if len(slots) == 3:
        equal("slots are earliest first", [s["id"] for s in slots], ["s1", "s2", "s3"])
        equal("start is echoed verbatim", slots[0]["start"], "2030-01-10T09:00:00Z")
        check("every slot reports availability", all("available" in s for s in slots), slots)


def main() -> int:
    print(f"checking {BASE}")
    if not KEY:
        print("no API key: pass one as the second argument or set API_KEY", file=sys.stderr)
        return 2

    check_auth()
    check_reset()

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print("failed: " + "; ".join(FAILURES))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
