"""Stub: captcha recognition service moved to plugins/court_automation/captcha/"""

try:
    from plugins.court_automation.captcha.captcha_recognition_service import (
        CaptchaRecognitionService,
        CaptchaResult,
        CaptchaServiceAdapter,
    )

except ImportError:
    CaptchaRecognitionService = None  # type: ignore[assignment,misc]
    CaptchaResult = None  # type: ignore[assignment,misc]
    CaptchaServiceAdapter = None  # type: ignore[assignment,misc]
