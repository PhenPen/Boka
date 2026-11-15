"""The one error shape this API returns: {"error": "<message>"}."""


class ApiError(Exception):
    """An error the caller should see, with a status code and message."""

    def __init__(self, status: int, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers or {}
