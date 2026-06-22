"""爬虫核心服务测试（Cookie、截图、监控、Token）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

from apps.automation.services.scraper.core.cookie_service import CookieService
from apps.automation.services.scraper.core.screenshot_utils import ScreenshotUtils

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestCookieService:
    """CookieService 测试。"""

    def test_load_no_path(self) -> None:
        """无路径返回 False。"""
        service = CookieService()
        context = MagicMock()
        assert service.load(context) is False

    def test_load_file_not_exists(self) -> None:
        """文件不存在返回 False。"""
        service = CookieService(storage_path="/nonexistent/cookies.json")
        context = MagicMock()
        assert service.load(context) is False

    def test_load_valid_cookies(self) -> None:
        """加载有效 Cookie。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cookies": [{"name": "test", "value": "123"}]}, f)
            f.flush()

            service = CookieService(storage_path=f.name)
            context = MagicMock()
            result = service.load(context)
            assert result is True
            context.add_cookies.assert_called_once()

    def test_load_empty_cookies(self) -> None:
        """空 Cookie 列表返回 False。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cookies": []}, f)
            f.flush()

            service = CookieService(storage_path=f.name)
            context = MagicMock()
            assert service.load(context) is False

    def test_load_no_cookies_key(self) -> None:
        """无 cookies 键返回 False。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"other": "data"}, f)
            f.flush()

            service = CookieService(storage_path=f.name)
            context = MagicMock()
            assert service.load(context) is False

    def test_save_no_path_raises(self) -> None:
        """无路径抛出异常。"""
        service = CookieService()
        context = MagicMock()
        try:
            service.save(context)
            raise AssertionError("应抛出 ValueError")
        except ValueError as e:
            assert "storage_path" in str(e)

    def test_load_with_explicit_path(self) -> None:
        """使用显式路径加载。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cookies": [{"name": "test", "value": "123"}]}, f)
            f.flush()

            service = CookieService()
            context = MagicMock()
            result = service.load(context, storage_path=f.name)
            assert result is True


class TestScreenshotUtils:
    """ScreenshotUtils 测试。"""

    def test_collect_screenshots_no_dir(self) -> None:
        """截图目录不存在返回空列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old_media_root = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                utils = ScreenshotUtils()
                result = utils.collect_screenshots()
                assert result == []
            finally:
                django.conf.settings.MEDIA_ROOT = old_media_root

    def test_collect_screenshots_empty_dir(self) -> None:
        """空截图目录返回空列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old_media_root = django.conf.settings.MEDIA_ROOT
            django.conf.settings.MEDIA_ROOT = tmpdir
            try:
                screenshot_dir = Path(tmpdir) / "automation" / "screenshots"
                screenshot_dir.mkdir(parents=True)
                utils = ScreenshotUtils()
                result = utils.collect_screenshots()
                assert result == []
            finally:
                django.conf.settings.MEDIA_ROOT = old_media_root

    def test_collect_screenshots_with_files(self) -> None:
        """收集截图文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old_media_root = django.conf.settings.MEDIA_ROOT
            old_media_url = django.conf.settings.MEDIA_URL
            django.conf.settings.MEDIA_ROOT = tmpdir
            django.conf.settings.MEDIA_URL = "/media/"
            try:
                screenshot_dir = Path(tmpdir) / "automation" / "screenshots"
                screenshot_dir.mkdir(parents=True)
                # 创建测试截图
                (screenshot_dir / "test1.png").write_bytes(b"fake png")
                (screenshot_dir / "test2.png").write_bytes(b"fake png")

                utils = ScreenshotUtils()
                result = utils.collect_screenshots(limit=5)
                assert len(result) == 2
            finally:
                django.conf.settings.MEDIA_ROOT = old_media_root
                django.conf.settings.MEDIA_URL = old_media_url

    def test_collect_screenshots_limit(self) -> None:
        """限制截图数量。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            import django.conf
            old_media_root = django.conf.settings.MEDIA_ROOT
            old_media_url = django.conf.settings.MEDIA_URL
            django.conf.settings.MEDIA_ROOT = tmpdir
            django.conf.settings.MEDIA_URL = "/media/"
            try:
                screenshot_dir = Path(tmpdir) / "automation" / "screenshots"
                screenshot_dir.mkdir(parents=True)
                for i in range(5):
                    (screenshot_dir / f"test{i}.png").write_bytes(b"fake png")

                utils = ScreenshotUtils()
                result = utils.collect_screenshots(limit=2)
                assert len(result) == 2
            finally:
                django.conf.settings.MEDIA_ROOT = old_media_root
                django.conf.settings.MEDIA_URL = old_media_url
