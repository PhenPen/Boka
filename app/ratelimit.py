"""Level 5: at most five booking attempts per email in any rolling minute."""

import math
from datetime import timedelta

from .db import pool
from .validation import utc_now

MAX_ATTEMPTS = 5
WINDOW = timedelta(seconds=60)


def record_attempt(email: str) -> int:
    """Count this attempt for `email`.

    Returns 0 when the attempt may proceed, otherwise the number of whole
    seconds until the window has room again (the Retry-After value).
    """
    with pool.connection() as conn:
        # One lock per address: simultaneous attempts for the same email queue
        # here instead of both slipping under the limit.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (email,))

        # The window is rolling, so prune rather than reset a counter.
        conn.execute(
            "DELETE FROM rate_attempts WHERE email = %s AND at <= now() - interval '60 seconds'",
            (email,),
        )
        row = conn.execute(
            "SELECT count(*) AS attempts, min(at) AS oldest FROM rate_attempts WHERE email = %s",
            (email,),
        ).fetchone()

        if row["attempts"] >= MAX_ATTEMPTS:
            wait = math.ceil((row["oldest"] + WINDOW - utc_now()).total_seconds())
            return max(1, wait)

        conn.execute("INSERT INTO rate_attempts (email, at) VALUES (%s, now())", (email,))
    return 0
