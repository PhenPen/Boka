"""Levels 1-4: book a slot, look a booking up, cancel it."""

import base64
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from psycopg.errors import ForeignKeyViolation
from starlette.concurrency import run_in_threadpool

from . import idempotency, ratelimit
from .auth import require_api_key
from .db import pool
from .errors import ApiError
from .http_utils import json_body
from .validation import clean_text, is_valid_email, iso, normalise_email, utc_now

router = APIRouter(dependencies=[Depends(require_api_key)])

BOOKING_COLUMNS = "id, slot_id, name, email, status, created_at"


def encode_cursor(seq: int) -> str:
    """Opaque token for "continue after this row"."""
    return base64.urlsafe_b64encode(str(seq).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return int(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        raise ApiError(400, "cursor is not valid")


def booking_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "slot_id": row["slot_id"],
        "name": row["name"],
        "email": row["email"],
        "status": row["status"],
        "created_at": iso(row["created_at"]),
    }


@router.post("/bookings", status_code=201)
async def create_booking(request: Request) -> JSONResponse:
    payload = await json_body(request)
    key = (request.headers.get("Idempotency-Key") or "").strip() or None
    digest = idempotency.body_hash(payload) if key else None

    # The database work runs in a worker thread so concurrent bookings really
    # are concurrent instead of queueing behind the event loop.
    status, body, headers = await run_in_threadpool(handle_create, payload, key, digest)
    return JSONResponse(body, status_code=status, headers=headers)


def handle_create(payload: dict, key: str | None, digest: str | None):
    if key:
        with pool.connection() as conn:
            stored = idempotency.load(conn, key)
        if stored is not None:
            if stored["body_hash"] != digest:
                return 422, {"error": "idempotency key was used with a different body"}, {}
            return stored["status"], stored["body"], {}

    try:
        status, body = _book(payload, key, digest)
        return status, body, {}
    except ApiError as exc:
        # Persist failures too, so a retried request sees the same answer.
        if key and exc.status in idempotency.REPLAYABLE:
            with pool.connection() as conn:
                idempotency.store(conn, key, digest, exc.status, {"error": exc.message})
        return exc.status, {"error": exc.message}, exc.headers


def _seconds_to_wait(payload: dict) -> int:
    """Count the attempt against the email's rate limit, when it has one."""
    raw = payload.get("email")
    if not isinstance(raw, str) or not raw.strip():
        # Nothing to attribute the attempt to; the request is rejected as
        # invalid further down instead.
        return 0
    return ratelimit.record_attempt(normalise_email(raw))


def _book(payload: dict, key: str | None, digest: str | None) -> tuple[int, dict]:
    wait = _seconds_to_wait(payload)
    if wait:
        raise ApiError(
            429,
            "too many booking attempts for this email",
            {"Retry-After": str(wait)},
        )

    slot_id = clean_text(payload.get("slot_id"))
    name = clean_text(payload.get("name"))
    email = clean_text(payload.get("email"))

    if not slot_id:
        raise ApiError(400, "slot_id is required")
    if not name:
        raise ApiError(400, "name is required")
    if not email:
        raise ApiError(400, "email is required")
    if not is_valid_email(email):
        raise ApiError(400, "email is invalid")

    with pool.connection() as conn:
        slot = conn.execute(
            "SELECT id, start_ts FROM slots WHERE id = %s", (slot_id,)
        ).fetchone()
        if slot is None:
            raise ApiError(404, "slot not found")
        if slot["start_ts"] <= utc_now():
            raise ApiError(400, "slot has already started")

        # The partial unique index decides the race: when another request won,
        # this inserts nothing and the slot is reported as taken.
        try:
            row = conn.execute(
                f"""
                INSERT INTO bookings (id, slot_id, name, email, status)
                VALUES (%s, %s, %s, %s, 'confirmed')
                ON CONFLICT DO NOTHING
                RETURNING {BOOKING_COLUMNS}
                """,
                (str(uuid.uuid4()), slot_id, name, normalise_email(email)),
            ).fetchone()
        except ForeignKeyViolation:
            # The slot was replaced or deleted between the lookup and the insert.
            raise ApiError(404, "slot not found")
        if row is None:
            raise ApiError(409, "slot is already booked")

        booking = booking_json(row)
        if key and not idempotency.store(conn, key, digest, 201, booking):
            # Another request with the same key committed first. Keep its
            # answer and undo this booking rather than creating a duplicate.
            conn.rollback()
            stored = idempotency.load(conn, key)
            if stored is not None:
                return stored["status"], stored["body"]
            raise ApiError(409, "slot is already booked")

    return 201, booking


@router.get("/bookings")
def list_bookings(
    email: str | None = None, limit: str | None = None, cursor: str | None = None
) -> dict:
    return list_bookings_data(email, limit, cursor)


def list_bookings_data(
    email: str | None, limit: str | None = None, cursor: str | None = None
) -> dict:
    address = clean_text(email)
    if not address:
        raise ApiError(400, "email is required")

    page_size = 10
    if limit is not None:
        try:
            page_size = int(limit)
        except (TypeError, ValueError):
            raise ApiError(400, "limit must be an integer from 1 to 50")
        if not 1 <= page_size <= 50:
            raise ApiError(400, "limit must be an integer from 1 to 50")

    after = decode_cursor(cursor) if cursor else 0

    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {BOOKING_COLUMNS}, seq FROM bookings
            WHERE email = %s AND seq > %s
            ORDER BY seq ASC
            LIMIT %s
            """,
            (normalise_email(address), after, page_size + 1),
        ).fetchall()

    page = rows[:page_size]
    next_cursor = encode_cursor(page[-1]["seq"]) if len(rows) > page_size else None
    return {"bookings": [booking_json(row) for row in page], "next_cursor": next_cursor}


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> dict:
    return get_booking_data(booking_id)


def get_booking_data(booking_id: str) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {BOOKING_COLUMNS} FROM bookings WHERE id = %s", (booking_id,)
        ).fetchone()
    if row is None:
        raise ApiError(404, "booking not found")
    return booking_json(row)


@router.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: str) -> dict:
    return cancel_booking_data(booking_id)


def cancel_booking_data(booking_id: str) -> dict:
    with pool.connection() as conn:
        # Locking the row makes two simultaneous cancels settle as one success
        # and one 409 instead of two successes.
        row = conn.execute(
            f"SELECT {BOOKING_COLUMNS} FROM bookings WHERE id = %s FOR UPDATE",
            (booking_id,),
        ).fetchone()
        if row is None:
            raise ApiError(404, "booking not found")
        if row["status"] == "cancelled":
            raise ApiError(409, "booking is already cancelled")

        row = conn.execute(
            f"UPDATE bookings SET status = 'cancelled' WHERE id = %s RETURNING {BOOKING_COLUMNS}",
            (booking_id,),
        ).fetchone()

    # Dropping out of the partial index frees the slot for the next patient.
    return booking_json(row)
