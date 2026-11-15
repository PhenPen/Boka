"""Levels 1-3: book a slot, look a booking up, cancel it."""

import uuid

from fastapi import APIRouter, Depends, Request

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
async def create_booking(request: Request) -> dict:
    payload = await json_body(request)

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

        # The partial unique index decides the race: if another request won,
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

    return booking_json(row)


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            f"SELECT {BOOKING_COLUMNS} FROM bookings WHERE id = %s", (booking_id,)
        ).fetchone()
    if row is None:
        raise ApiError(404, "booking not found")
    return booking_json(row)
