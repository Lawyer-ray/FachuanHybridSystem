"""Custom exceptions."""

from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    CaptchaRecognitionError,
    LoginFailedError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
)

# 从 core 重新导出，保持向后兼容
__all__ = [
    "AutoTokenAcquisitionError",
    "CaptchaRecognitionError",
    "LoginFailedError",
    "NoAvailableAccountError",
    "TokenAcquisitionTimeoutError",
]
