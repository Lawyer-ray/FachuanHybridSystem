"""Protocol definitions for dependency injection in chat_records services."""

from __future__ import annotations

from typing import Protocol

__all__ = ["ScreenshotCreator", "ProgressUpdater"]


class ScreenshotCreator(Protocol):
    """Protocol for creating screenshot records (dependency injection)."""

    def create_screenshot(
        self,
        *,
        project_id: int,
        ordering: int,
        sha256: str,
        dhash: str,
        capture_time_seconds: float | None,
        source: str,
        frame_score: float | None,
        image_name: str,
        image_content: bytes,
    ) -> None: ...


class ProgressUpdater(Protocol):
    """Protocol for reporting extraction progress (dependency injection)."""

    def update_progress(
        self,
        *,
        progress: int,
        current: int,
        total: int,
        message: str,
    ) -> None: ...
