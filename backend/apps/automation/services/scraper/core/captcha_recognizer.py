"""Stub: CaptchaRecognizer has been moved to plugins/court_automation/login/captcha_recognizer.py

This file re-exports from the plugin for backward compatibility.
"""

from plugins.court_automation.login.captcha_recognizer import *  # noqa: F401,F403
from plugins.court_automation.login.captcha_recognizer import (  # noqa: F401
    CaptchaRecognizer,
    FileBasedCaptchaRecognizer,
    ManualCaptchaRecognizer,
    get_captcha_recognizer,
)
