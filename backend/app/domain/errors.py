"""Domain errors mapped to HTTP responses by the API layer."""
from __future__ import annotations

from typing import Any, Optional


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: Optional[str] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "details": self.details}


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Invalid(DomainError):
    status_code = 422
    code = "invalid"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"
