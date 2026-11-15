"""Levels 1-2: seeding slots on /reset and listing them on /slots."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Request

from .auth import require_api_key
from .db import pool
from .errors import ApiError
from .http_utils import json_body
from .validation import iso, parse_timestamp

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/reset")
async def reset(request: Request) -> dict:
    return reset_slots(await json_body(request))


def reset_slots(payload: dict) -> dict:
    """Replace every slot and drop the state that belonged to the old set."""
    slots = payload.get("slots")
    if not isinstance(slots, list):
        raise ApiError(400, "slots must be an array")

    rows = []
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            continue
        start_raw = slot.get("start")
        if not isinstance(start_raw, str):
            continue
        try:
            start_ts = parse_timestamp(start_raw)
            end_raw = slot.get("end")
            if isinstance(end_raw, str):
                end_ts = parse_timestamp(end_raw)
            else:
                end_ts = start_ts + timedelta(minutes=30)
                end_raw = iso(end_ts)
        except ValueError:
            raise ApiError(400, f"invalid timestamp in slot at index {index}")

        slot_id = slot.get("id")
        if not isinstance(slot_id, str) or not slot_id.strip():
            slot_id = f"slot_{index + 1}"
        provider = slot.get("provider")
        rows.append(
            (
                slot_id.strip(),
                provider.strip() if isinstance(provider, str) else "",
                start_raw,
                end_raw,
                start_ts,
                end_ts,
            )
        )

    with pool.connection() as conn:
        # Bookings first: they reference slots. Idempotency keys and rate-limit
        # history are per-assessment state, so a reset clears them too.
        conn.execute("DELETE FROM bookings")
        conn.execute("DELETE FROM slots")
        conn.execute("DELETE FROM idempotency")
        conn.execute("DELETE FROM rate_attempts")
        if rows:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO slots (id, provider, start_raw, end_raw, start_ts, end_ts)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        start_raw = EXCLUDED.start_raw,
                        end_raw = EXCLUDED.end_raw,
                        start_ts = EXCLUDED.start_ts,
                        end_ts = EXCLUDED.end_ts
                    """,
                    rows,
                )

    return {"ok": True, "slots": len(rows)}


@router.get("/slots")
def list_slots(provider: str | None = None) -> dict:
    return list_slots_data(provider)


def list_slots_data(provider: str | None = None) -> dict:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.provider, s.start_raw, s.end_raw,
                   NOT EXISTS (
                       SELECT 1 FROM bookings b
                       WHERE b.slot_id = s.id AND b.status = 'confirmed'
                   ) AS available
            FROM slots s
            WHERE (%s::text IS NULL OR s.provider = %s)
            ORDER BY s.start_ts ASC, s.id ASC
            """,
            (provider, provider),
        ).fetchall()
    return {"slots": [_slot_json(row) for row in rows]}


def _slot_json(row: dict) -> dict:
    return {
        "id": row["id"],
        "provider": row["provider"],
        "start": row["start_raw"],
        "end": row["end_raw"],
        "available": row["available"],
    }

