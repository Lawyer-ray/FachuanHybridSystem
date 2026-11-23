"""
爬虫核心服务
"""

import logging

try:
    from .captcha_recognizer import CaptchaRecognizer, ManualCaptchaRecognizer, get_captcha_recognizer
except ImportError:
    # S31-03（2026-11-23 二轮审计）：原实现把 ImportError 静默吞成三个 None（无日志、无告警），
    # 插件未装时「验证码识别整体消失」在日志里一个字都没有。现在保留可导入性（CI 无
    # plugins 子模块时本包仍可 import），但降级必经 WARNING。
    logging.getLogger("apps.automation.services.scraper.core").warning(
        "验证码识别器插件不可用（已降级为 None）: plugins.court_automation.login 导入失败", exc_info=True
    )
    CaptchaRecognizer = None  # type: ignore[assignment,misc]
    ManualCaptchaRecognizer = None  # type: ignore[assignment,misc]
    get_captcha_recognizer = None  # type: ignore[assignment]
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
    "CaptchaRecognizer",
    "ManualCaptchaRecognizer",
    "get_captcha_recognizer",
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
