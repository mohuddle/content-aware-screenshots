"""Content-aware screenshots: crop, optional note, optional pasted URL."""

from __future__ import annotations

__version__ = "0.1.0"


class CasError(RuntimeError):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code
