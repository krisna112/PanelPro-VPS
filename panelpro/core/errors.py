"""Shared exception types for the panel backend."""

from __future__ import annotations


class PanelError(Exception):
    """A user-facing error that maps cleanly onto an HTTP response."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
