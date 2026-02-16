"""Module for auth."""

from dataclasses import dataclass
from typing import Any


@dataclass
class LoginAttemptResult:
    success: bool
    token: str | None
    account: str
    error_message: str | None
    attempt_duration: float
    retry_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "token": self.token,
            "account": self.account,
            "error_message": self.error_message,
            "attempt_duration": self.attempt_duration,
            "retry_count": self.retry_count,
        }


@dataclass
class TokenAcquisitionResult:
    success: bool
    token: str | None
    acquisition_method: str
    total_duration: float
    login_attempts: list[LoginAttemptResult]
    error_details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "token": self.token,
            "acquisition_method": self.acquisition_method,
            "total_duration": self.total_duration,
            "login_attempts": [attempt.to_dict() for attempt in self.login_attempts],
            "error_details": self.error_details,
        }
