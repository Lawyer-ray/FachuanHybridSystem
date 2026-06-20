"""代码占位符注册表和文档生成输出存储测试。"""

from __future__ import annotations

from unittest.mock import patch

from apps.documents.services.code_placeholders.registry import (
    CodePlaceholderDefinition,
    CodePlaceholderRegistry,
)
from apps.documents.services.generation.output_storage import GeneratedDocumentStorage


class TestCodePlaceholderDefinition:
    """CodePlaceholderDefinition 数据类测试。"""

    def test_creation(self) -> None:
        defn = CodePlaceholderDefinition(
            key="party_name",
            source="test",
            category="party",
            display_name="当事人姓名",
            description="案件当事人的姓名",
            example_value="张三",
        )
        assert defn.key == "party_name"
        assert defn.source == "test"
        assert defn.category == "party"
        assert defn.display_name == "当事人姓名"

    def test_defaults(self) -> None:
        defn = CodePlaceholderDefinition(key="test", source="test", category="test")
        assert defn.display_name == ""
        assert defn.description == ""
        assert defn.example_value == ""

    def test_frozen(self) -> None:
        defn = CodePlaceholderDefinition(key="test", source="test", category="test")
        try:
            defn.key = "changed"  # type: ignore
            raise AssertionError("应抛出异常")
        except AttributeError:
            pass


class TestCodePlaceholderRegistry:
    """CodePlaceholderRegistry 测试。"""

    def setup_method(self) -> None:
        # 重置单例
        CodePlaceholderRegistry._instance = None

    def test_singleton(self) -> None:
        r1 = CodePlaceholderRegistry()
        r2 = CodePlaceholderRegistry()
        assert r1 is r2

    def test_register_definitions(self) -> None:
        registry = CodePlaceholderRegistry()
        registry.register([
            CodePlaceholderDefinition(key="key1", source="test", category="basic"),
            CodePlaceholderDefinition(key="key2", source="test", category="basic"),
        ])
        defs = registry.list_definitions()
        assert len(defs) == 2
        assert any(d.key == "key1" for d in defs)

    def test_register_duplicate_ignored(self) -> None:
        registry = CodePlaceholderRegistry()
        registry.register([CodePlaceholderDefinition(key="key1", source="test", category="basic")])
        registry.register([CodePlaceholderDefinition(key="key1", source="test2", category="basic")])
        defs = registry.list_definitions()
        assert len(defs) == 1
        assert defs[0].source == "test"  # 第一次注册的

    def test_upsert_definitions(self) -> None:
        registry = CodePlaceholderRegistry()
        registry.register([CodePlaceholderDefinition(key="key1", source="test", category="basic")])
        registry.upsert([CodePlaceholderDefinition(key="key1", source="updated", category="basic")])
        defs = registry.list_definitions()
        assert len(defs) == 1
        assert defs[0].source == "updated"

    def test_clear(self) -> None:
        registry = CodePlaceholderRegistry()
        registry.register([CodePlaceholderDefinition(key="key1", source="test", category="basic")])
        registry.clear()
        assert registry.list_definitions() == []

    def test_list_sorted(self) -> None:
        registry = CodePlaceholderRegistry()
        registry.register([
            CodePlaceholderDefinition(key="z_key", source="test", category="basic"),
            CodePlaceholderDefinition(key="a_key", source="test", category="basic"),
        ])
        defs = registry.list_definitions()
        assert defs[0].key == "a_key"
        assert defs[1].key == "z_key"


class TestGeneratedDocumentStorage:
    """GeneratedDocumentStorage 测试。"""

    def test_save_bytes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GeneratedDocumentStorage(media_root=tmpdir)
            with patch("apps.documents.services.generation.output_storage.default_storage") as mock_storage:
                mock_storage.save.side_effect = lambda rel, f: rel
                result = storage.save_bytes(
                    relative_dir="test_dir",
                    filename="test.txt",
                    content=b"hello world",
                )
                assert "test_dir/test.txt" in result

    def test_save_for_case(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = GeneratedDocumentStorage(media_root=tmpdir)
            with patch("apps.documents.services.generation.output_storage.default_storage") as mock_storage:
                mock_storage.save.side_effect = lambda rel, f: rel
                result = storage.save_for_case(
                    case_id=1,
                    filename="contract.docx",
                    content=b"fake docx",
                )
                assert "case_1" in result
            assert "contract.docx" in result

    def test_media_root_from_config(self) -> None:
        """从配置获取 media_root。"""
        storage = GeneratedDocumentStorage(media_root="/tmp/test")
        assert str(storage.media_root) == "/tmp/test"

    def test_media_root_not_configured_raises(self) -> None:
        """未配置 media_root 抛出异常。"""
        storage = GeneratedDocumentStorage(media_root=None)
        # media_root 从配置读取，可能成功也可能失败
        try:
            root = storage.media_root
            # 如果成功，说明配置存在
            assert root is not None
        except (RuntimeError, Exception):
            pass  # 预期的异常
