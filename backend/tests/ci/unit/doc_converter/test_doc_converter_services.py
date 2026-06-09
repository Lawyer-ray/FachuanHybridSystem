"""
Tests for apps.doc_converter.services — 文档转换服务
"""

from __future__ import annotations

import pytest


class TestDocConverterModules:
    """文档转换模块可导入性测试"""

    def test_converter_service_importable(self) -> None:
        from apps.doc_converter.services.converter_service import DocConverterService

        assert DocConverterService is not None

    def test_engine_importable(self) -> None:
        from apps.doc_converter.services.engine import convert_single

        assert callable(convert_single)

    def test_storage_importable(self) -> None:
        from apps.doc_converter.services.storage import DocConverterStorage

        assert DocConverterStorage is not None
