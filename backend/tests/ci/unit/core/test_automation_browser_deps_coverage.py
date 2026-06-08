"""apps/core/dependencies/automation_browser.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGetAntiDetection:
    """测试 get_anti_detection。"""

    def test_returns_anti_detection_module(self) -> None:
        """应返回 anti_detection 模块对象。"""
        from apps.core.dependencies.automation_browser import get_anti_detection

        with patch("apps.core.services.browser.anti_detection", new_callable=MagicMock) as mock_ad:
            result = get_anti_detection()
            assert result is mock_ad


class TestCreateCourtZxfwService:
    """测试 create_court_zxfw_service。"""

    def test_creates_service_with_args(self) -> None:
        """传入 page/context/site_name 时正确转发参数。"""
        from apps.core.dependencies.automation_browser import create_court_zxfw_service

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService",
            mock_cls,
        ):
            result = create_court_zxfw_service(
                page=mock_page, context=mock_context, site_name="custom_site"
            )

        mock_cls.assert_called_once_with(
            page=mock_page, context=mock_context, site_name="custom_site"
        )
        assert result is mock_instance

    def test_default_site_name(self) -> None:
        """不传 site_name 时使用默认值 court_zxfw。"""
        from apps.core.dependencies.automation_browser import create_court_zxfw_service

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_cls = MagicMock()

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService",
            mock_cls,
        ):
            create_court_zxfw_service(page=mock_page, context=mock_context)

        mock_cls.assert_called_once_with(
            page=mock_page, context=mock_context, site_name="court_zxfw"
        )

    def test_returns_service_instance(self) -> None:
        """返回值应为 CourtZxfwService 实例。"""
        from apps.core.dependencies.automation_browser import create_court_zxfw_service

        mock_page = MagicMock()
        mock_context = MagicMock()

        with patch(
            "apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService",
            return_value=MagicMock(name="ZxfwInstance"),
        ):
            result = create_court_zxfw_service(page=mock_page, context=mock_context)
        assert result is not None
