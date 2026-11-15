"""Level 4: a retried request replays its first answer instead of acting twice."""

import hashlib
import json

from psycopg.types.json import Jsonb

# Only these outcomes are worth replaying. 401, 422 and 429 are about the
# request itself (auth, key reuse, throttling) and must stay live.
REPLAYABLE = (200, 201, 400, 404, 409)


def body_hash(payload: dict) -> str:
    """Fingerprint of the fields that determine what the booking is."""
    canonical = json.dumps(
        {field: payload.get(field) for field in ("slot_id", "name", "email")},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load(conn, key: str) -> dict | None:
    return conn.execute(
        "SELECT body_hash, status, body FROM idempotency WHERE key = %s", (key,)
    ).fetchone()


def store(conn, key: str, digest: str, status: int, body: dict) -> bool:
    """Record a response. False means another request already claimed the key."""
    row = conn.execute(
        """
        INSERT INTO idempotency (key, body_hash, status, body)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO NOTHING
        RETURNING key
        """,
        (key, digest, status, Jsonb(body)),
    ).fetchone()
    return row is not None
