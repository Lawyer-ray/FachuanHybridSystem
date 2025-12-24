"""
爬虫核心服务
"""
from .browser_service import BrowserService
from .anti_detection import anti_detection, AntiDetection
from .captcha_service import CaptchaService
from .captcha_recognizer import CaptchaRecognizer, DdddocrRecognizer
from .security_service import SecurityService
from .validator_service import ValidatorService
from .monitor_service import MonitorService
from .screenshot_utils import ScreenshotUtils
from .exceptions import (
    ScraperException,
    BrowserCreationError,
    BrowserConfigurationError,
    CaptchaRecognitionError,
    LoginError,
)

__all__ = [
    'BrowserService',
    'anti_detection',
    'AntiDetection',
    'CaptchaService',
    'CaptchaRecognizer',
    'DdddocrRecognizer',
    'SecurityService',
    'ValidatorService',
    'MonitorService',
    'ScreenshotUtils',
    'ScraperException',
    'BrowserCreationError',
    'BrowserConfigurationError',
    'CaptchaRecognitionError',
    'LoginError',
]
