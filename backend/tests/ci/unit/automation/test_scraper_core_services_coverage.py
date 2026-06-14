"""Tests for CookieService, ValidatorService, ScreenshotUtils, and TokenService."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCookieService:
    """Cover CookieService.load branches."""

    def _svc(self):
        from apps.automation.services.scraper.core.cookie_service import CookieService
        return CookieService

    def test_load_no_path_returns_false(self):
        svc = self._svc()()
        assert svc.load(MagicMock(), storage_path=None) is False

    def test_load_file_not_exists(self):
        svc = self._svc()(storage_path="/tmp/nonexistent.json")
        with patch("apps.automation.services.scraper.core.cookie_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            assert svc.load(MagicMock()) is False

    def test_load_no_cookies_key(self):
        svc = self._svc()(storage_path="/tmp/test.json")
        with patch("apps.automation.services.scraper.core.cookie_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.read_text.return_value = '{"other": "data"}'
            assert svc.load(MagicMock()) is False

    def test_load_empty_cookies(self):
        svc = self._svc()(storage_path="/tmp/test.json")
        with patch("apps.automation.services.scraper.core.cookie_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.read_text.return_value = '{"cookies": []}'
            assert svc.load(MagicMock()) is False

    def test_load_success(self):
        svc = self._svc()(storage_path="/tmp/test.json")
        context = MagicMock()
        with patch("apps.automation.services.scraper.core.cookie_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.read_text.return_value = '{"cookies": [{"name": "sid", "value": "123"}]}'
            assert svc.load(context) is True
            context.add_cookies.assert_called_once_with([{"name": "sid", "value": "123"}])

    def test_load_non_dict_json(self):
        svc = self._svc()(storage_path="/tmp/test.json")
        with patch("apps.automation.services.scraper.core.cookie_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.read_text.return_value = '[1, 2, 3]'
            assert svc.load(MagicMock()) is False

    def test_load_explicit_path(self):
        svc = self._svc()()
        context = MagicMock()
        with patch("apps.automation.services.scraper.core.cookie_service.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.read_text.return_value = '{"cookies": [{"name": "c"}]}'
            assert svc.load(context, storage_path="/tmp/cookies.json") is True


class TestValidatorService:
    """Cover ValidatorService and ValidatorServiceAdapter branches."""

    def test_init_with_no_args(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc._text_utils is None

    def test_text_utils_lazy_load(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc.text_utils is not None

    def test_file_utils_lazy_load(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc.file_utils is not None

    def test_validate_case_number_empty(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc.validate_case_number("") is False

    def test_validate_case_number_none(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc.validate_case_number(None) is False

    def test_validate_case_number_valid(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc.validate_case_number("（2025）粤01民初12345号") is True

    def test_validate_case_number_invalid(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        assert svc.validate_case_number("not a case number") is False

    def test_normalize_case_number(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        result = svc.normalize_case_number("(2025)粤01民初1")
        assert "（" in result
        assert result.endswith("号")

    def test_validate_file(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        mock_fu = MagicMock()
        mock_fu.validate_file_basic.return_value = {"valid": True}
        svc = ValidatorService(file_utils=mock_fu)
        result = svc.validate_file("/test/file.pdf")
        assert result["valid"] is True

    def test_clean_text(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        result = svc.clean_text("hello  world")
        assert result == "hello world"

    def test_extract_case_numbers(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorService
        svc = ValidatorService()
        result = svc.extract_case_numbers("案件（2025）粤01民初1号")
        assert len(result) >= 1


class TestValidatorServiceAdapter:
    """Cover ValidatorServiceAdapter."""

    def test_init_with_no_service(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        assert adapter._service is None

    def test_service_lazy_load(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        assert adapter.service is not None

    def test_validate_case_number(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        assert adapter.validate_case_number("（2025）粤01民初1号") is True

    def test_normalize_case_number(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        result = adapter.normalize_case_number("(2025)粤01民初1")
        assert result.endswith("号")

    def test_validate_file(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        with patch.object(adapter.service, "validate_file", return_value={"valid": True}):
            result = adapter.validate_file("/test/file.pdf")
            assert result["valid"] is True

    def test_clean_text(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        result = adapter.clean_text("hello  world")
        assert result == "hello world"

    def test_extract_case_numbers(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        result = adapter.extract_case_numbers("案件（2025）粤01民初1号")
        assert len(result) >= 1

    def test_internal_validate_case_number(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        assert adapter.validate_case_number_internal("（2025）粤01民初1号") is True

    def test_internal_normalize_case_number(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        result = adapter.normalize_case_number_internal("(2025)粤01民初1")
        assert result.endswith("号")

    def test_internal_validate_file(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        with patch.object(adapter.service, "validate_file", return_value={"valid": True}):
            result = adapter.validate_file_internal("/test/file.pdf")
            assert result["valid"] is True

    def test_internal_clean_text(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        result = adapter.clean_text_internal("hello  world")
        assert result == "hello world"

    def test_internal_extract_case_numbers(self):
        from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
        adapter = ValidatorServiceAdapter()
        result = adapter.extract_case_numbers_internal("案件（2025）粤01民初1号")
        assert len(result) >= 1


class TestScreenshotUtils:
    """Cover ScreenshotUtils.collect_screenshots branches."""

    def test_dir_not_exists(self):
        from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils
        svc = ScreenshotUtils()
        with patch("apps.automation.services.scraper.core.screenshot_utils.settings") as mock_settings, \
             patch("apps.automation.services.scraper.core.screenshot_utils.Path") as mock_path_cls:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_path_cls.return_value.exists.return_value = False
            result = svc.collect_screenshots()
        assert result == []

    def test_collects_screenshots(self):
        from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils
        from pathlib import Path
        svc = ScreenshotUtils()

        mock_screenshot = MagicMock()
        mock_screenshot.stat.return_value.st_mtime = 1000
        mock_screenshot.relative_to.return_value = Path("automation/screenshots/test.png")

        with patch("apps.automation.services.scraper.core.screenshot_utils.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_settings.MEDIA_URL = "/media/"
            with patch("apps.automation.services.scraper.core.screenshot_utils.Path") as mock_path_cls:
                mock_screenshot_dir = MagicMock()
                mock_screenshot_dir.exists.return_value = True
                mock_screenshot_dir.glob.return_value = [mock_screenshot]
                # Path(root) / "automation" / "screenshots"
                mock_root = MagicMock()
                mock_root.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=mock_screenshot_dir)))
                mock_path_cls.return_value = mock_root

                result = svc.collect_screenshots(limit=3)
        assert len(result) == 1
        assert "test.png" in result[0]

    def test_exception_returns_empty(self):
        from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils
        svc = ScreenshotUtils()
        with patch("apps.automation.services.scraper.core.screenshot_utils.settings") as mock_settings, \
             patch("apps.automation.services.scraper.core.screenshot_utils.Path") as mock_path_cls:
            mock_settings.MEDIA_ROOT = "/tmp/media"
            mock_path_cls.side_effect = Exception("path error")
            result = svc.collect_screenshots()
        assert result == []
