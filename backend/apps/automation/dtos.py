"""Data transfer objects."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptchaRecognizeResultDTO:
    success: bool
    text: str | None
    processing_time: float
    error: str | None


@dataclass(frozen=True)
class CourtTokenDTO:
    site_name: str
    account: str
    token: str
    token_type: str
    expires_at: Any
    created_at: Any
    updated_at: Any
