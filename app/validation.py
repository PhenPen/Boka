"""Parsing and validation shared by the endpoints."""

import re
from datetime import datetime, timezone

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# A timestamp with no offset at all, e.g. 2026-12-10T09:00:00 — treated as UTC
# so the result does not depend on the server's local timezone.
NAIVE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if NAIVE_ISO_RE.match(text):
        text += "Z"
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def normalise_email(value: str) -> str:
    return value.strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value))


def clean_text(value: object) -> str | None:
    """A trimmed string, or None when the value is not usable text."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
