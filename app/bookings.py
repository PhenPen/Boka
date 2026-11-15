"""Levels 1-4: book a slot, look a booking up, cancel it."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import idempotency
from .auth import require_api_key
from .db import pool
from .errors import ApiError
from .http_utils import json_body
from .validation import clean_text, is_valid_email, iso, normalise_email, utc_now

router = APIRouter(dependencies=[Depends(require_api_key)])

BOOKING_COLUMNS = "id, slot_id, name, email, status, created_at"


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
    status, body = await run_in_threadpool(_handle_create, payload, key, digest)
    return JSONResponse(body, status_code=status)


def _handle_create(payload: dict, key: str | None, digest: str | None):
    if key:
        with pool.connection() as conn:
            stored = idempotency.load(conn, key)
        if stored is not None:
            if stored["body_hash"] != digest:
                return 422, {"error": "idempotency key was used with a different body"}
            return stored["status"], stored["body"]

    try:
        return _book(payload, key, digest)
    except ApiError as exc:
        # Persist failures too, so a retried request sees the same answer.
        if key and exc.status in idempotency.REPLAYABLE:
            with pool.connection() as conn:
                idempotency.store(conn, key, digest, exc.status, {"error": exc.message})
        return exc.status, {"error": exc.message}


def _book(payload: dict, key: str | None, digest: str | None) -> tuple[int, dict]:
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
        row = conn.execute(
            f"""
            INSERT INTO bookings (id, slot_id, name, email, status)
            VALUES (%s, %s, %s, %s, 'confirmed')
            ON CONFLICT DO NOTHING
            RETURNING {BOOKING_COLUMNS}
            """,
            (str(uuid.uuid4()), slot_id, name, normalise_email(email)),
        ).fetchone()
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


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {BOOKING_COLUMNS} FROM bookings WHERE id = %s", (booking_id,)
        ).fetchone()
    if row is None:
        raise ApiError(404, "booking not found")
    return booking_json(row)


@router.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: str) -> dict:
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
