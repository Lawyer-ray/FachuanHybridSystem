"""爬虫核心服务测试 - 真实执行代码。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.scraper.core.exceptions import (
    BrowserConfigurationError,
    BrowserCreationError,
    CaptchaRecognitionError,
    CookieLoadError,
    LoginError,
    ScraperException,
)
from apps.automation.services.scraper.core.validator_service import (
    ValidatorService,
    ValidatorServiceAdapter,
)


class TestValidatorService:
    """测试 ValidatorService。"""

    def setup_method(self) -> None:
        self.service = ValidatorService()

    def test_validate_case_number_valid(self) -> None:
        """有效案号校验。"""
        assert self.service.validate_case_number("（2025）粤0604民初41257号") is True

    def test_validate_case_number_empty(self) -> None:
        """空案号返回 False。"""
        assert self.service.validate_case_number("") is False

    def test_validate_case_number_none(self) -> None:
        """None 案号返回 False。"""
        assert self.service.validate_case_number(None) is False  # type: ignore[arg-type]

    def test_validate_case_number_invalid_format(self) -> None:
        """无效格式案号返回 False。"""
        assert self.service.validate_case_number("not-a-case-number") is False

    def test_normalize_case_number(self) -> None:
        """规范化案号。"""
        result = self.service.normalize_case_number("（2025）粤0604民初41257号")
        assert "2025" in result
        assert "41257" in result

    def test_clean_text(self) -> None:
        """清洗文本。"""
        result = self.service.clean_text("  hello  world  ")
        assert result == "hello world"

    def test_extract_case_numbers(self) -> None:
        """提取案号。"""
        text = "案件（2025）粤0604民初41257号已受理"
        numbers = self.service.extract_case_numbers(text)
        assert len(numbers) >= 1

    def test_validate_file_nonexistent(self) -> None:
        """不存在的文件返回无效。"""
        result = self.service.validate_file("/nonexistent/file.pdf")
        assert result["valid"] is False

    def test_validate_file_with_extension(self, tmp_path: Path) -> None:
        """校验文件扩展名。"""
        f = tmp_path / "test.pdf"
        f.write_bytes(b"test")
        result = self.service.validate_file(str(f), expected_extensions=[".pdf"])
        assert result["valid"] is True

    def test_validate_file_wrong_extension(self, tmp_path: Path) -> None:
        """错误扩展名返回无效。"""
        f = tmp_path / "test.txt"
        f.write_bytes(b"test")
        result = self.service.validate_file(str(f), expected_extensions=[".pdf"])
        assert result["valid"] is False


class TestValidatorServiceAdapter:
    """测试 ValidatorServiceAdapter。"""

    def setup_method(self) -> None:
        self.adapter = ValidatorServiceAdapter()

    def test_validate_case_number(self) -> None:
        assert self.adapter.validate_case_number("（2025）粤0604民初41257号") is True

    def test_normalize_case_number(self) -> None:
        result = self.adapter.normalize_case_number("（2025）粤0604民初41257号")
        assert "2025" in result

    def test_clean_text(self) -> None:
        result = self.adapter.clean_text("  hello  ")
        assert result == "hello"

    def test_extract_case_numbers(self) -> None:
        numbers = self.adapter.extract_case_numbers("（2025）粤0604民初1号")
        assert len(numbers) >= 1

    def test_internal_validate_case_number(self) -> None:
        assert self.adapter.validate_case_number_internal("（2025）粤0604民初1号") is True

    def test_internal_normalize_case_number(self) -> None:
        result = self.adapter.normalize_case_number_internal("（2025）粤0604民初1号")
        assert "2025" in result

    def test_internal_clean_text(self) -> None:
        result = self.adapter.clean_text_internal("  hello  ")
        assert result == "hello"

    def test_internal_extract_case_numbers(self) -> None:
        numbers = self.adapter.extract_case_numbers_internal("（2025）粤0604民初1号")
        assert len(numbers) >= 1

    def test_lazy_service_loading(self) -> None:
        """测试延迟加载服务。"""
        adapter = ValidatorServiceAdapter(service=None)
        assert adapter._service is None
        # 访问时才创建
        adapter.validate_case_number("test")
        assert adapter._service is not None


class TestScraperExceptions:
    """测试爬虫异常类。"""

    def test_scraper_exception(self) -> None:
        exc = ScraperException("基础异常")
        assert str(exc) == "基础异常"

    def test_browser_creation_error(self) -> None:
        exc = BrowserCreationError("创建失败", config={"headless": True}, original_error=Exception("原始错误"))
        assert "创建失败" in str(exc)
        assert exc.config == {"headless": True}
        assert exc.original_error is not None

    def test_browser_creation_error_minimal(self) -> None:
        exc = BrowserCreationError("创建失败")
        assert "创建失败" in str(exc)
        assert exc.config is None
        assert exc.original_error is None

    def test_browser_configuration_error(self) -> None:
        exc = BrowserConfigurationError("timeout", -1, "不能为负数")
        assert exc.field == "timeout"
        assert exc.value == -1
        assert exc.reason == "不能为负数"
        assert "timeout" in str(exc)

    def test_captcha_recognition_error(self) -> None:
        exc = CaptchaRecognitionError("识别失败", attempts=3, selector="#captcha")
        assert exc.attempts == 3
        assert exc.selector == "#captcha"
        assert "3" in str(exc)
        assert "#captcha" in str(exc)

    def test_captcha_recognition_error_minimal(self) -> None:
        exc = CaptchaRecognitionError("识别失败")
        assert exc.attempts == 0
        assert exc.selector is None

    def test_cookie_load_error(self) -> None:
        exc = CookieLoadError("加载失败", site_name="court.gov.cn", account="user1")
        assert exc.site_name == "court.gov.cn"
        assert exc.account == "user1"
        assert "court.gov.cn" in str(exc)

    def test_cookie_load_error_minimal(self) -> None:
        exc = CookieLoadError("加载失败")
        assert exc.site_name is None
        assert exc.account is None

    def test_login_error(self) -> None:
        exc = LoginError("登录失败", account="user1", reason="密码错误", screenshot_path="/tmp/err.png")
        assert exc.account == "user1"
        assert exc.reason == "密码错误"
        assert exc.screenshot_path == "/tmp/err.png"
        assert "user1" in str(exc)

    def test_login_error_minimal(self) -> None:
        exc = LoginError("登录失败")
        assert exc.account is None
        assert exc.reason is None
        assert exc.screenshot_path is None

    def test_exception_hierarchy(self) -> None:
        """验证异常继承关系。"""
        assert issubclass(BrowserCreationError, ScraperException)
        assert issubclass(BrowserConfigurationError, ScraperException)
        assert issubclass(CaptchaRecognitionError, ScraperException)
        assert issubclass(CookieLoadError, ScraperException)
        assert issubclass(LoginError, ScraperException)
        assert issubclass(ScraperException, Exception)
