"""文档生成结果和占位符注册表测试。"""

from __future__ import annotations

import pytest

from apps.documents.services.generation.result import GenerationResult
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.documents.services.placeholders.base import BasePlaceholderService


class TestGenerationResult:
    """GenerationResult 数据类测试。"""

    def test_success_result(self) -> None:
        result = GenerationResult(
            success=True,
            file_path="/path/to/file.docx",
            file_name="file.docx",
            duration_ms=1500,
        )
        assert result.success is True
        assert result.file_path == "/path/to/file.docx"
        assert result.file_name == "file.docx"
        assert result.duration_ms == 1500
        assert result.error_message is None

    def test_failure_result(self) -> None:
        result = GenerationResult(
            success=False,
            error_message="生成失败",
            duration_ms=500,
        )
        assert result.success is False
        assert result.error_message == "生成失败"

    def test_success_without_path_raises(self) -> None:
        """成功但无路径应抛出异常。"""
        with pytest.raises(ValueError, match="文件路径"):
            GenerationResult(success=True)

    def test_failure_without_error_raises(self) -> None:
        """失败但无错误信息应抛出异常。"""
        with pytest.raises(ValueError, match="错误信息"):
            GenerationResult(success=False)

    def test_negative_duration_raises(self) -> None:
        """负耗时应抛出异常。"""
        with pytest.raises(ValueError, match="负数"):
            GenerationResult(success=True, file_path="/path", duration_ms=-1)


class TestPlaceholderRegistry:
    """PlaceholderRegistry 测试。"""

    def setup_method(self) -> None:
        # 重置单例
        PlaceholderRegistry._instance = None
        PlaceholderRegistry._initialized = False
        PlaceholderRegistry._services = {}

    def test_singleton(self) -> None:
        """单例模式。"""
        r1 = PlaceholderRegistry()
        r2 = PlaceholderRegistry()
        assert r1 is r2

    def test_register_service(self) -> None:
        """注册占位符服务。"""
        class TestService(BasePlaceholderService):
            name = "test_reg"
            display_name = "测试注册"
            placeholder_keys = ["key1"]

            def generate(self, context_data):
                return {"key1": "value1"}

        PlaceholderRegistry.register(TestService)
        registry = PlaceholderRegistry()
        assert "test_reg" in registry._services

    def test_register_invalid_service(self) -> None:
        """注册无效服务应抛出异常。"""
        with pytest.raises(ValueError, match="继承自 BasePlaceholderService"):
            PlaceholderRegistry.register(type("Bad", (), {}))

    def test_register_service_without_name(self) -> None:
        """无名称的服务应抛出异常。"""
        class NoNameService(BasePlaceholderService):
            name = ""
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        with pytest.raises(ValueError, match="name"):
            PlaceholderRegistry.register(NoNameService)

    def test_register_duplicate_raises(self) -> None:
        """重复注册应抛出异常。"""
        class DupService(BasePlaceholderService):
            name = "dup_test"
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        PlaceholderRegistry.register(DupService)
        with pytest.raises(Exception):
            PlaceholderRegistry.register(DupService)
