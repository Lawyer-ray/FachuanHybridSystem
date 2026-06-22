"""Stub: CaptchaRecognizer moved to plugins/court_automation/login/captcha_recognizer.py"""

try:
    from plugins.court_automation.login.captcha_recognizer import (
        CaptchaRecognizer,
        FileBasedCaptchaRecognizer,
        ManualCaptchaRecognizer,
        get_captcha_recognizer,
    )
except ImportError:
    CaptchaRecognizer = None  # type: ignore[assignment,misc]
    FileBasedCaptchaRecognizer = None  # type: ignore[assignment,misc]
    ManualCaptchaRecognizer = None  # type: ignore[assignment,misc]
    get_captcha_recognizer = None  # type: ignore[assignment]
