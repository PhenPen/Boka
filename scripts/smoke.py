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
from urllib.parse import quote

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
                {"id": "past", "provider": "Dr Ade", "start": "2020-01-10T09:00:00Z", "end": "2020-01-10T09:30:00Z"},
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
    equal("all seeded slots are listed, including past ones", len(slots), 4)
    if len(slots) == 4:
        equal("slots are earliest first", [s["id"] for s in slots], ["past", "s1", "s2", "s3"])
        equal("start is echoed verbatim", slots[1]["start"], "2030-01-10T09:00:00Z")
        equal("end is echoed verbatim", slots[1]["end"], "2030-01-10T09:30:00Z")
        check("every slot reports availability", all("available" in s for s in slots), slots)

    filtered = call("GET", f"/slots?provider={quote('Dr Bello')}")
    equal("provider filter keeps only that provider", [s["id"] for s in filtered.body["slots"]], ["s3"])


_EMAIL_SEQUENCE = 0


def email(tag: str = "patient") -> str:
    """A fresh address per check so the per-email rate limit cannot cascade."""
    global _EMAIL_SEQUENCE
    _EMAIL_SEQUENCE += 1
    return f"{tag}-{_EMAIL_SEQUENCE}@example.com"


def check_booking() -> None:
    section("level 1-3: booking a slot")
    address = email("ada")
    created = call(
        "POST", "/bookings", {"slot_id": "s1", "name": "  Ada Obi  ", "email": address.upper()}
    )
    equal("POST /bookings is 201", created.status, 201)
    booking = created.body or {}
    check("booking has an id", isinstance(booking.get("id"), str) and bool(booking["id"]), booking)
    equal("name is trimmed", booking.get("name"), "Ada Obi")
    equal("email is stored lower case", booking.get("email"), address)
    equal("status is confirmed", booking.get("status"), "confirmed")
    equal("slot_id is echoed", booking.get("slot_id"), "s1")
    check(
        "created_at is an ISO UTC timestamp",
        isinstance(booking.get("created_at"), str) and booking["created_at"].endswith("Z"),
        booking.get("created_at"),
    )

    fetched = call("GET", f"/bookings/{booking.get('id')}")
    equal("GET /bookings/{id} is 200", fetched.status, 200)
    equal("GET /bookings/{id} returns the booking", fetched.body, booking)
    equal("unknown booking id is 404", call("GET", "/bookings/does-not-exist").status, 404)

    listing = call("GET", "/slots")
    taken = [s for s in listing.body["slots"] if s["id"] == "s1"]
    equal("a booked slot is no longer available", taken[0]["available"] if taken else None, False)

    clash = call("POST", "/bookings", {"slot_id": "s1", "name": "Someone Else", "email": email()})
    equal("booking an already taken slot is 409", clash.status, 409)


def check_booking_validation() -> None:
    section("level 2: booking validation")
    equal(
        "slot_id missing is 400",
        call("POST", "/bookings", {"name": "Ada Obi", "email": email()}).status,
        400,
    )
    equal(
        "name missing is 400",
        call("POST", "/bookings", {"slot_id": "s2", "email": email()}).status,
        400,
    )
    equal(
        "email missing is 400",
        call("POST", "/bookings", {"slot_id": "s2", "name": "Ada Obi"}).status,
        400,
    )
    equal(
        "name of only spaces is 400",
        call("POST", "/bookings", {"slot_id": "s2", "name": "   ", "email": email()}).status,
        400,
    )
    equal(
        "empty slot_id is 400",
        call("POST", "/bookings", {"slot_id": "", "name": "Ada Obi", "email": email()}).status,
        400,
    )
    equal(
        "email without @ is 400",
        call("POST", "/bookings", {"slot_id": "s2", "name": "Ada Obi", "email": "not-an-email"}).status,
        400,
    )
    equal(
        "email without a domain is 400",
        call("POST", "/bookings", {"slot_id": "s2", "name": "Ada Obi", "email": "ada@"}).status,
        400,
    )
    equal(
        "numeric slot_id is 400",
        call("POST", "/bookings", {"slot_id": 7, "name": "Ada Obi", "email": email()}).status,
        400,
    )
    equal(
        "unknown slot is 404",
        call("POST", "/bookings", {"slot_id": "nope", "name": "Ada Obi", "email": email()}).status,
        404,
    )
    equal(
        "a slot that already started is 400",
        call("POST", "/bookings", {"slot_id": "past", "name": "Ada Obi", "email": email()}).status,
        400,
    )
    equal("an unparseable body is 400", call_raw("POST", "/bookings", b"{oops").status, 400)


def check_cancel() -> None:
    section("level 3: cancelling")
    address = email("canceller")
    created = call("POST", "/bookings", {"slot_id": "s3", "name": "Ada Obi", "email": address})
    equal("a fresh slot books", created.status, 201)
    booking_id = (created.body or {}).get("id")

    cancelled = call("DELETE", f"/bookings/{booking_id}")
    equal("DELETE /bookings/{id} is 200", cancelled.status, 200)
    equal("the booking is cancelled", (cancelled.body or {}).get("status"), "cancelled")
    equal("the id is unchanged", (cancelled.body or {}).get("id"), booking_id)

    fetched = call("GET", f"/bookings/{booking_id}")
    equal("GET shows the cancelled status", (fetched.body or {}).get("status"), "cancelled")

    listing = call("GET", "/slots")
    freed = [s for s in listing.body["slots"] if s["id"] == "s3"]
    equal("cancelling frees the slot", freed[0]["available"] if freed else None, True)

    equal("cancelling again is 409", call("DELETE", f"/bookings/{booking_id}").status, 409)
    equal("cancelling an unknown booking is 404", call("DELETE", "/bookings/nope").status, 404)

    rebooked = call("POST", "/bookings", {"slot_id": "s3", "name": "Ada Obi", "email": email()})
    equal("a freed slot can be booked again", rebooked.status, 201)


def main() -> int:
    print(f"checking {BASE}")
    if not KEY:
        print("no API key: pass one as the second argument or set API_KEY", file=sys.stderr)
        return 2

    check_auth()
    check_reset()
    check_booking()
    check_booking_validation()
    check_cancel()

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print("failed: " + "; ".join(FAILURES))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
