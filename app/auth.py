"""Level 2: no request gets in without the configured key."""

import hmac

from fastapi import Header

from .config import API_KEY
from .errors import ApiError


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not API_KEY:
        raise ApiError(500, "server has no API_KEY configured")
    # compare_digest keeps the comparison time independent of the match length.
    if not x_api_key or not hmac.compare_digest(x_api_key, API_KEY):
        raise ApiError(401, "unauthorized")
