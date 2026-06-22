"""Stub: 验证码识别服务已迁移到 plugins/court_automation/captcha/"""

try:
    from plugins.court_automation.captcha import CaptchaRecognitionService, CaptchaServiceAdapter

    __all__ = ["CaptchaRecognitionService", "CaptchaServiceAdapter"]

except ImportError:
    CaptchaRecognitionService = None  # type: ignore[assignment]
    CaptchaServiceAdapter = None  # type: ignore[assignment]
