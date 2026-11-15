-- Applied by scripts/db_push.py. Every statement is safe to re-run.

-- Levels 1-2: slots are replaced wholesale by POST /reset.
CREATE TABLE IF NOT EXISTS slots (
    id        text PRIMARY KEY,
    provider  text NOT NULL DEFAULT '',
    start_raw text NOT NULL,          -- echoed back exactly as it was submitted
    end_raw   text NOT NULL,
    start_ts  timestamptz NOT NULL,   -- parsed: ordering and "already started"
    end_ts    timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    seq        bigserial PRIMARY KEY, -- insertion order, doubles as the cursor
    id         text NOT NULL UNIQUE,
    slot_id    text NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
    name       text NOT NULL,
    email      text NOT NULL,         -- stored lower case
    status     text NOT NULL CHECK (status IN ('confirmed', 'cancelled')),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Level 3: the database decides who wins the race, not application code.
-- Concurrent inserts for the same slot collide here, even across processes.
CREATE UNIQUE INDEX IF NOT EXISTS bookings_one_confirmed_per_slot
    ON bookings (slot_id) WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS bookings_by_email ON bookings (email, seq);

-- Level 4: a retried request replays the stored response instead of booking twice.
CREATE TABLE IF NOT EXISTS idempotency (
    key        text PRIMARY KEY,
    body_hash  text NOT NULL,
    status     int  NOT NULL,
    body       jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Level 5: one row per booking attempt, pruned to the last minute.
CREATE TABLE IF NOT EXISTS rate_attempts (
    email text NOT NULL,
    at    timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS rate_attempts_email_at ON rate_attempts (email, at);
