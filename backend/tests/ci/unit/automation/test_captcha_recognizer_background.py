"""回归测试：后台任务上下文的验证码识别器选择。

背景：message_hub 的 django-q 同步任务是「无人值守」的，验证码页面没有人工输入。
`captcha_ocr` 插件是在 django-q worker 启动之后才部署的（plugins 子模块），加上
importlib 目录缓存与孤儿 worker，导致已运行的 worker 一直判定「无插件」，静默降级到
`FileBasedCaptchaRecognizer`（轮询 .answer 文件）→ 无人应答 → 120 秒后只抛出一个难懂的
「Token 获取超时」。

本测试锁定修复契约：
- allow_manual=False（后台任务）时，插件不可用必须**立即失败**，绝不静默进入手动轮询；
- 插件被检测到但加载失败时，必须记录真实原因（不再 logger.debug 吞掉）；
- 默认 allow_manual=True 行为保持不变（交互式场景仍可手动输入）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin

    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

from apps.automation.services.scraper.core.captcha_recognizer import (
    FileBasedCaptchaRecognizer,
    ManualCaptchaRecognizer,
    get_captcha_recognizer,
)

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestBackgroundNoManual:
    """allow_manual=False（后台任务上下文）下的契约。"""

    def test_no_plugin_background_raises_not_filebased(self):
        """无插件 + 后台上下文：必须抛 RuntimeError，而不是静默返回 FileBased（会轮询超时）。"""
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            with pytest.raises(RuntimeError) as exc_info:
                get_captcha_recognizer(task=None, allow_manual=False)
        msg = str(exc_info.value)
        # 错误必须可操作：指出自动识别不可用 + 后台无法手动输入，而非「Token 获取超时」
        assert "自动验证码识别不可用" in msg
        assert "无法手动输入" in msg

    def test_no_plugin_importerror_background_raises(self):
        """plugins 子模块缺失（ImportError）+ 后台上下文：同样立即失败。"""
        with patch.dict("sys.modules", {"plugins": None}):
            with pytest.raises(RuntimeError):
                get_captcha_recognizer(task=None, allow_manual=False)

    def test_plugin_present_background_returns_ddddocr(self):
        """有插件 + 后台上下文：仍应自动识别（DdddocrRecognizer），不触发手动分支。"""
        sentinel = MagicMock(name="ddddocr_instance")
        with patch.dict(
            "sys.modules",
            {
                "plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=True)),
                "plugins.captcha_ocr": MagicMock(DdddocrRecognizer=MagicMock(return_value=sentinel)),
            },
        ):
            result = get_captcha_recognizer(task=None, allow_manual=False)
        assert result is sentinel

    def test_plugin_detected_but_load_fails_background_raises_with_reason(self):
        """插件被检测到（has_* 返回 True）但 DdddocrRecognizer 初始化失败（如 onnx 损坏/ddddocr 缺失）。

        修复前：logger.debug 静默吞掉 → 降级到 FileBased → 后台超时。
        修复后：必须抛出 RuntimeError，且错误信息带上真实失败原因。
        """
        broken = MagicMock(side_effect=RuntimeError("onnx model corrupt"))
        with patch.dict(
            "sys.modules",
            {
                "plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=True)),
                "plugins.captcha_ocr": MagicMock(DdddocrRecognizer=broken),
            },
        ):
            with patch("plugins.court_automation.login.captcha_recognizer.logger") as mock_logger:
                with pytest.raises(RuntimeError) as exc_info:
                    get_captcha_recognizer(task=None, allow_manual=False)
        # 真实原因必须体现在错误信息里，便于排查
        assert "onnx model corrupt" in str(exc_info.value)
        # 必须以 warning 记录，不能再是 debug
        assert mock_logger.warning.called

    def test_background_never_returns_manual_recognizers(self):
        """后台上下文 + 有 task 被显式忽略：即便传入 task，allow_manual=False 也不该进入手动轮询。

        注意正常契约是 task 优先于 allow_manual；但后台调用方不应传 task。这里仅断言：
        不传 task 时绝不可能得到需要人工的识别器。
        """
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            with pytest.raises(RuntimeError):
                get_captcha_recognizer(allow_manual=False)


class TestManualStillAllowedByDefault:
    """默认行为（allow_manual=True）保持不变：交互式场景仍可手动输入。"""

    def test_no_plugin_no_task_default_returns_filebased(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            result = get_captcha_recognizer(task=None)
        assert isinstance(result, FileBasedCaptchaRecognizer)

    def test_no_plugin_with_task_default_returns_manual(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            task = MagicMock()
            result = get_captcha_recognizer(task=task)
        assert isinstance(result, ManualCaptchaRecognizer)
        assert result.task is task

    def test_default_explicit_allow_manual_true_no_task_returns_filebased(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            result = get_captcha_recognizer(task=None, allow_manual=True)
        assert isinstance(result, FileBasedCaptchaRecognizer)


class TestInvalidateCachesCalled:
    """修复会让 get_captcha_recognizer 每次强制重扫文件系统验证插件存在性（自愈已运行 worker）。"""

    def test_invalidate_caches_invoked(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=MagicMock(return_value=False))}):
            with patch("importlib.invalidate_caches") as mock_inv:
                get_captcha_recognizer(allow_manual=True)
        assert mock_inv.called
