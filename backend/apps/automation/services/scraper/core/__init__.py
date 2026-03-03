"""
爬虫核心服务
"""

from .anti_detection import AntiDetection, anti_detection
from .browser_service import BrowserService
from .captcha_recognizer import CaptchaRecognizer, DdddocrRecognizer
from .captcha_service import CaptchaService
from .exceptions import (
    BrowserConfigurationError,
    BrowserCreationError,
    CaptchaRecognitionError,
    LoginError,
    ScraperException,
)
from .monitor_service import MonitorService
from .screenshot_utils import ScreenshotUtils
from .security_service import SecurityService
from .validator_service import ValidatorService

__all__ = [
    "BrowserService",
    "anti_detection",
    "AntiDetection",
    "CaptchaService",
    "CaptchaRecognizer",
    "DdddocrRecognizer",
    "SecurityService",
    "ValidatorService",
    "MonitorService",
    "ScreenshotUtils",
    "ScraperException",
    "BrowserCreationError",
    "BrowserConfigurationError",
    "CaptchaRecognitionError",
    "LoginError",
]
