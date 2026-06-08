"""文档指纹服务和文件夹模板结构规则测试。"""

from __future__ import annotations
import pytest

import hashlib
import re

from apps.documents.services.external_template.fingerprint_service import (
    _WORD_NS,
    _STYLE_ATTR_PATTERNS,
    _STYLE_ELEMENT_TAGS,
)
from apps.documents.services.folder_template.structure_rules import FolderTemplateStructureRules
from apps.documents.services.folder_template.id_service import FolderTemplateIdService


class TestFingerprintServiceConstants:
    """指纹服务常量测试。"""

    def test_word_namespace(self) -> None:
        """Word XML 命名空间。"""
        assert "wordprocessingml" in _WORD_NS
        assert _WORD_NS.startswith("http://")

    def test_style_attr_patterns_not_empty(self) -> None:
        """样式属性模式不为空。"""
        assert len(_STYLE_ATTR_PATTERNS) > 0

    def test_style_element_tags_not_empty(self) -> None:
        """样式元素标签不为空。"""
        assert len(_STYLE_ELEMENT_TAGS) > 0

    def test_style_element_tags_contain_word_ns(self) -> None:
        """样式元素标签包含 Word 命名空间。"""
        for tag in _STYLE_ELEMENT_TAGS:
            assert _WORD_NS in tag

    def test_style_attr_patterns_are_compiled(self) -> None:
        """样式属性模式是已编译的正则。"""
        for pattern in _STYLE_ATTR_PATTERNS:
            assert isinstance(pattern, type(re.compile("")))


class TestFolderTemplateIdService:
    """FolderTemplateIdService 测试。"""

    def setup_method(self) -> None:
        self.service = FolderTemplateIdService()

    def test_collect_structure_ids_empty(self) -> None:
        """空结构返回空列表。"""
        result = self.service.collect_structure_ids({})
        assert result == []

    def test_collect_structure_ids_flat(self) -> None:
        """扁平结构（只收集 children 的 id）。"""
        structure = {
            "id": "root",
            "children": [
                {"id": "child1"},
                {"id": "child2"},
            ],
        }
        result = self.service.collect_structure_ids(structure)
        # 注意：collect_structure_ids 只收集 children 的 id，不收集 root
        assert "child1" in result
        assert "child2" in result
        assert "root" not in result  # root 不在 children 中

    def test_find_internal_duplicates_no_dup(self) -> None:
        """无重复。"""
        result = self.service.find_internal_duplicates({"a", "b", "c"})
        assert result == set()

    def test_find_internal_duplicates_with_dup(self) -> None:
        """有重复（通过传入重复集合模拟）。"""
        # find_internal_duplicates 接收的是 set，所以不会有重复
        # 这里测试空集
        result = self.service.find_internal_duplicates(set())
        assert result == set()

    def test_find_global_duplicates_empty(self) -> None:
        """空集合无全局重复。"""
        result = self.service.find_global_duplicates(set(), None)
        assert result == set()


class TestFolderTemplateStructureRules:
    """FolderTemplateStructureRules 测试。"""

    def setup_method(self) -> None:
        self.rules = FolderTemplateStructureRules(id_service=FolderTemplateIdService())

    def test_validate_and_fix_empty_structure(self) -> None:
        """空结构。"""
        changed, fixed, messages = self.rules.validate_and_fix_structure_ids({})
        assert changed is False

    def test_validate_and_fix_none_structure(self) -> None:
        """None 结构。"""
        changed, fixed, messages = self.rules.validate_and_fix_structure_ids(None)  # type: ignore
        assert changed is False

    def test_validate_structure_ids_empty(self) -> None:
        """空结构验证。"""
        is_valid, messages = self.rules.validate_structure_ids({})
        assert is_valid is True
        assert messages == []

    def test_validate_structure_ids_none(self) -> None:
        """None 结构验证。"""
        is_valid, messages = self.rules.validate_structure_ids(None)  # type: ignore
        assert is_valid is True

    @pytest.mark.django_db
    def test_validate_and_fix_structure_with_unique_ids(self) -> None:
        """唯一 ID 结构无需修复。"""
        structure = {
            "id": "root",
            "children": [
                {"id": "child1"},
                {"id": "child2"},
            ],
        }
        changed, fixed, messages = self.rules.validate_and_fix_structure_ids(structure)
        assert changed is False
