"""测试监督卡检测器的纯逻辑方法

覆盖: apps/contracts/services/archive/supervision_card_extractor.py
重点: _resolve_file_path, _SUPERVISION_CARD_KEYWORDS
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.supervision_card_extractor import (
    SupervisionCardExtractor,
    _SUPERVISION_CARD_KEYWORDS,
)


@pytest.fixture
def extractor() -> SupervisionCardExtractor:
    return SupervisionCardExtractor()


class TestConstants:
    """测试常量定义"""

    def test_keywords_not_empty(self) -> None:
        assert len(_SUPERVISION_CARD_KEYWORDS) > 0

    def test_keywords_contain_expected(self) -> None:
        assert "监督卡" in _SUPERVISION_CARD_KEYWORDS
        assert "服务质量" in _SUPERVISION_CARD_KEYWORDS

    def test_keywords_are_strings(self) -> None:
        for kw in _SUPERVISION_CARD_KEYWORDS:
            assert isinstance(kw, str)


class TestResolveFilePath:
    """测试文件路径解析"""

    def test_absolute_path_exists(self, extractor: SupervisionCardExtractor) -> None:
        """绝对路径且存在时应返回该路径"""
        with patch("apps.contracts.services.archive.supervision_card_extractor.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.is_absolute.return_value = True
            mock_instance.exists.return_value = True
            mock_path.return_value = mock_instance
            result = extractor._resolve_file_path("/some/path/file.pdf")
            assert result is not None

    def test_absolute_path_not_exists_falls_back_to_media(
        self, extractor: SupervisionCardExtractor
    ) -> None:
        """绝对路径但不存在时，尝试 MEDIA_ROOT"""
        with (
            patch("apps.contracts.services.archive.supervision_card_extractor.Path") as mock_path_cls,
            patch("django.conf.settings") as mock_settings,
        ):
            mock_settings.MEDIA_ROOT = "/media"
            # First call: absolute, not exists
            mock_abs_path = MagicMock()
            mock_abs_path.is_absolute.return_value = True
            mock_abs_path.exists.return_value = False
            # Second call (MEDIA_ROOT / file_path)
            mock_full_path = MagicMock()
            mock_full_path.exists.return_value = True

            mock_path_cls.side_effect = lambda p: mock_abs_path if p == "file.pdf" else mock_full_path
            result = extractor._resolve_file_path("file.pdf")
            # Should try MEDIA_ROOT path
            assert result is not None

    def test_no_media_root_returns_none(
        self, extractor: SupervisionCardExtractor
    ) -> None:
        with (
            patch("apps.contracts.services.archive.supervision_card_extractor.Path") as mock_path_cls,
            patch("django.conf.settings") as mock_settings,
        ):
            delattr(mock_settings, "MEDIA_ROOT")
            mock_path = MagicMock()
            mock_path.is_absolute.return_value = False
            mock_path.exists.return_value = False
            mock_path_cls.return_value = mock_path
            result = extractor._resolve_file_path("file.pdf")
            assert result is None


class TestDetectAndExtract:
    """测试 detect_and_extract 方法"""

    def test_no_materials_returns_not_found(
        self, extractor: SupervisionCardExtractor
    ) -> None:
        with patch(
            "apps.contracts.services.archive.supervision_card_extractor.FinalizedMaterial"
        ) as mock_fm:
            mock_fm.objects.filter.return_value.order_by.return_value = []
            contract = MagicMock()
            result = extractor.detect_and_extract(contract)
            assert result["found"] is False
            assert result["error"] == "未找到合同正本PDF"
