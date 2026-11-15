"""The backend for the web page, which is not an API client.

The page is served from the same origin as the API, so the person using it is a
patient, not an API consumer. Making the browser send `X-API-Key` would mean
asking every visitor for the clinic's credential. Instead the browser calls
these routes, and the server runs the same core as the API.

They are unauthenticated on purpose: a public booking page is public. The key
exists to protect the machine-to-machine API, and that contract is unchanged -
`/slots`, `/bookings` and the rest still reject a missing key.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import bookings, idempotency, slots
from .http_utils import json_body

router = APIRouter()


@router.get("/web/slots")
def web_slots(provider: str | None = None) -> dict:
    return slots.list_slots_data(provider)


@router.post("/web/bookings")
async def web_create_booking(request: Request) -> JSONResponse:
    payload = await json_body(request)
    key = (request.headers.get("Idempotency-Key") or "").strip() or None
    digest = idempotency.body_hash(payload) if key else None

    status, body, headers = await run_in_threadpool(
        bookings.handle_create, payload, key, digest
    )
    return JSONResponse(body, status_code=status, headers=headers)


@router.get("/web/bookings")
def web_list_bookings(
    email: str | None = None, limit: str | None = None, cursor: str | None = None
) -> dict:
    return bookings.list_bookings_data(email, limit, cursor)


@router.get("/web/bookings/{booking_id}")
def web_get_booking(booking_id: str) -> dict:
    return bookings.get_booking_data(booking_id)


@router.delete("/web/bookings/{booking_id}")
def web_cancel_booking(booking_id: str) -> dict:
    return bookings.cancel_booking_data(booking_id)
