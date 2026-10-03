"""测试监督卡检测器的纯逻辑方法

覆盖: apps/contracts/services/archive/supervision_card_extractor.py
重点: _resolve_file_path, _SUPERVISION_CARD_KEYWORDS
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.supervision_card_extractor import (
    _SUPERVISION_CARD_KEYWORDS,
    SupervisionCardExtractor,
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
    """测试文件路径解析（统一走 to_media_abs，兼容相对/绝对路径）"""

    def test_relative_path_resolves_under_media_root(
        self, extractor: SupervisionCardExtractor, tmp_path: Path
    ) -> None:
        """相对路径应在 MEDIA_ROOT 下解析到真实文件"""
        media = tmp_path / "media"
        target = media / "contracts" / "a.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"x")

        with patch("django.conf.settings.MEDIA_ROOT", str(media)):
            result = extractor._resolve_file_path("contracts/a.pdf")
        assert result == target.resolve()

    def test_absolute_path_under_media_root(
        self, extractor: SupervisionCardExtractor, tmp_path: Path
    ) -> None:
        """MEDIA_ROOT 内的绝对路径应直接解析"""
        media = tmp_path / "media"
        target = media / "abs" / "b.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"x")

        with patch("django.conf.settings.MEDIA_ROOT", str(media)):
            result = extractor._resolve_file_path(str(target))
        assert result == target.resolve()

    def test_missing_file_returns_none(
        self, extractor: SupervisionCardExtractor, tmp_path: Path
    ) -> None:
        media = tmp_path / "media"
        media.mkdir()
        with patch("django.conf.settings.MEDIA_ROOT", str(media)):
            assert extractor._resolve_file_path("contracts/missing.pdf") is None

    def test_path_outside_media_root_returns_none(
        self, extractor: SupervisionCardExtractor, tmp_path: Path
    ) -> None:
        """MEDIA_ROOT 外的绝对路径不解析，返回 None"""
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"x")
        media = tmp_path / "media"
        media.mkdir()

        with patch("django.conf.settings.MEDIA_ROOT", str(media)):
            assert extractor._resolve_file_path(str(outside)) is None


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
