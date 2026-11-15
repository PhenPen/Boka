# Boka — clinic booking API

A JSON API for booking clinic appointment slots, plus a single-page front end
that uses it. Built to the contract at <https://koyaacademy.com/assessment-api>.

FastAPI + Postgres, no other services. Every API request must carry an
`X-API-Key` header; the page reaches the same logic through `/web`, where the
server adds it.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/reset` | Delete all bookings, replace all slots |
| `GET` | `/slots` | Slots earliest first, optional `?provider=`, with `available` |
| `POST` | `/bookings` | Book a slot (`201`) |
| `GET` | `/bookings` | A person's bookings, cursor paginated |
| `GET` | `/bookings/{id}` | One booking |
| `DELETE` | `/bookings/{id}` | Cancel a booking |

Errors are always `{"error": "<message>"}`. Missing or wrong key is `401`.

## The page, and why it has no key

The page is served from the same origin as the API, so the person using it is a
patient — not an API consumer. Making the browser send `X-API-Key` would mean
asking every visitor for the clinic's credential, so the page calls `/web/*`
instead:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/web/slots` | Same list the API returns |
| `POST` | `/web/bookings` | Book through the page |
| `GET` | `/web/bookings` | A person's bookings |
| `GET` | `/web/bookings/{id}` | One booking |
| `DELETE` | `/web/bookings/{id}` | Cancel |

These routes run the same core as the API with the key added on the server. They
are deliberately unauthenticated: a public booking page is public, and the key
protects the machine-to-machine contract, which is unchanged. Every rule still
applies through the page — validation, one booking per slot, idempotency and the
per-email rate limit — because the page and the API share the same code path.
The key never reaches the browser and is never part of this repository.


## How the hard requirements are met

**One booking per slot, even at the same instant.** `bookings` carries a partial
unique index:

```sql
CREATE UNIQUE INDEX bookings_one_confirmed_per_slot
    ON bookings (slot_id) WHERE status = 'confirmed';
```

Bookings are inserted with `ON CONFLICT DO NOTHING`; zero rows returned means
another request won the race, so the caller gets `409`. Nothing in the
application code decides who wins — the database does. Cancelling drops the row
out of the partial index, which frees the slot.

**Retries never duplicate.** An `Idempotency-Key` header maps to the first
response (fingerprint of `slot_id`/`name`/`email`, status, body). A replay with
the same body returns that stored response and is not counted against the rate
limit. The same key with a different body is `422`. The booking insert and the
key insert share one transaction, so a booking can never exist without its key.

**Five attempts per email per rolling minute.** `pg_advisory_xact_lock` on the
address serialises concurrent attempts; the window prunes rows older than 60
seconds. The sixth attempt is `429` with `Retry-After` in whole seconds. Failed
attempts count. A replay of an idempotent request does not.

**Pagination.** `bigserial seq` is both insertion order and the cursor, so
"oldest first" and paging are the same thing. `next_cursor` is null on the last
page.

`/reset` also clears idempotency keys and rate-limit history, so a fresh
assessment starts from a clean state.

## Local development

Requires Python 3.11+ and Docker.

```bash
# 1. a Postgres just for this project, on port 55432
docker run -d --name boka-pg \
  -e POSTGRES_USER=boka -e POSTGRES_PASSWORD=boka -e POSTGRES_DB=boka \
  -p 55432:5432 -v boka_pgdata:/var/lib/postgresql/data postgres:16-alpine

# 2. dependencies and configuration
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
cp .env.example .env                                       # then set API_KEY

# 3. schema, then the server
.venv/Scripts/python scripts/db_push.py
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1   # http://127.0.0.1:8010
```

Open <http://127.0.0.1:8010> for the page. It needs no setup: the server holds
the key.

```bash
.venv/Scripts/python scripts/seed_demo.py    # a few slots so the page has content
.venv/Scripts/python scripts/smoke.py        # the conformance suite
```

On macOS or Linux use `.venv/bin/python` and the same commands.

## Tests

`scripts/smoke.py` is black-box: it takes a base URL and a key, so it runs
unchanged against localhost or production.

```bash
python scripts/smoke.py https://your-deployment.example <api-key>
```

It covers authentication, reset and seeding, ordering and provider filtering,
every validation branch, `404`/`409`/`422`/`429` outcomes, cancelled bookings,
idempotent replay, cursor paging, and the rate limit. It also checks that the
page's `/web` routes work with no key while still enforcing every rule, and races
25 concurrent bookings for one slot three times, then 80 bookings across ten
slots, asserting exactly one winner per slot each time.

## Deploying

The app runs as a single Vercel Python function; `public/index.html` is served as
a static file from the same origin.

1. Create a Neon project and copy the **pooled** connection string.
2. Apply the schema to it: `DATABASE_URL='...' python scripts/db_push.py`.
3. In Vercel, set `DATABASE_URL`, `API_KEY` (a long random string) and
   `TZ=UTC`, then deploy with `npx.cmd vercel --prod`.
4. Verify: `python scripts/smoke.py https://your-url <api-key>`.

`vercel.json` rewrites only the API and page paths (`/slots`, `/bookings/*`,
`/web/*`, `/health`, `/docs`, the schema) into `api/index.py`, so the static page
is never caught by a catch-all. The app registers every route under `/`, `/api`
and `/api/index`, so it works whichever path the rewrite produces.

**Keep the key out of the repository.** `.env` is gitignored; `.env.example`
contains names only. The page never receives the key either — it is added
server-side — so this repository can be public. Send the key to whoever needs to
test the API, and rotate it in Vercel if it is ever exposed; nothing else in the
code depends on its value.

## Layout

```
api/index.py          entry point for the host
app/main.py           wiring: CORS, error shape, route registration
app/auth.py           the X-API-Key check
app/slots.py          /reset, /slots
app/bookings.py       bookings, cancel, pagination
app/web.py            the page's backend, key added server-side
app/idempotency.py    request fingerprints and stored replies
app/ratelimit.py      the rolling per-email window
app/validation.py     timestamps, emails, trimming
db/schema.sql         the whole schema, idempotent
public/index.html     the page
scripts/              db_push, dev, seed_demo, smoke
```
