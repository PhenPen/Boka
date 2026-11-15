"""Small request helpers."""

from fastapi import Request

from .errors import ApiError


async def json_body(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        raise ApiError(400, "body must be valid JSON")
    if not isinstance(payload, dict):
        raise ApiError(400, "body must be a JSON object")
    return payload
