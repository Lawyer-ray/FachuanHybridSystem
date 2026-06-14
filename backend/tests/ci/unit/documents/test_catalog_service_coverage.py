"""Tests for documents/services/code_placeholders/catalog_service.py.

Covers: CodePlaceholderCatalogService — get_definition, list_keys, _is_placeholder_key_candidate,
_looks_like_template_placeholder, _ContextDictKeyVisitor, _extract_definitions_from_spec,
_spec_metadata, _extract_string_assignment, _scan_placeholder_spec_files.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.code_placeholders.registry import (
    CodePlaceholderDefinition,
    CodePlaceholderRegistry,
)


class TestContextDictKeyVisitor:
    def test_visit_assign_with_context_dict(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = 'context = {"plaintiff_name": "张三", "case_number": "2026-01"}'
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert "plaintiff_name" in visitor.keys
        assert "case_number" in visitor.keys

    def test_visit_return_with_dict(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = 'def f():\n    return {"key1": "val1", "key2": "val2"}'
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert "key1" in visitor.keys
        assert "key2" in visitor.keys

    def test_non_context_assign_ignored(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = 'data = {"key1": "val1"}'
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert len(visitor.keys) == 0

    def test_non_string_keys_ignored(self):
        from apps.documents.services.code_placeholders.catalog_service import _ContextDictKeyVisitor

        code = 'context = {1: "val", None: "other"}'
        tree = ast.parse(code)
        visitor = _ContextDictKeyVisitor()
        visitor.visit(tree)
        assert len(visitor.keys) == 0


class TestExtractStringAssignment:
    def test_valid_string(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'KEY = "test.key"'
        tree = ast.parse(code)
        result = _extract_string_assignment(tree.body[0])
        assert result == "test.key"

    def test_non_string_value(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'KEY = 42'
        tree = ast.parse(code)
        result = _extract_string_assignment(tree.body[0])
        assert result is None

    def test_non_assign(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'pass'
        tree = ast.parse(code)
        result = _extract_string_assignment(tree.body[0])
        assert result is None

    def test_empty_string(self):
        from apps.documents.services.code_placeholders.catalog_service import _extract_string_assignment

        code = 'KEY = ""'
        tree = ast.parse(code)
        result = _extract_string_assignment(tree.body[0])
        assert result is None


class TestSpecMetadata:
    def test_litigation_ai(self):
        from apps.documents.services.code_placeholders.catalog_service import _spec_metadata

        path = Path("/backend/apps/litigation_ai/placeholders/spec.py")
        source, category, desc = _spec_metadata(path)
        assert source == "诉讼文书"
        assert category == "litigation"
        assert "诉讼文书" in desc

    def test_other_app(self):
        from apps.documents.services.code_placeholders.catalog_service import _spec_metadata

        path = Path("/backend/apps/documents/placeholders/spec.py")
        source, category, desc = _spec_metadata(path)
        assert "documents" in source
        assert category == "documents"


class TestCatalogServiceHelpers:
    def test_is_placeholder_key_candidate_valid(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        svc = CodePlaceholderCatalogService()
        assert svc._is_placeholder_key_candidate("plaintiff_name") is True

    def test_is_placeholder_key_candidate_chinese(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        svc = CodePlaceholderCatalogService()
        assert svc._is_placeholder_key_candidate("原告姓名") is True

    def test_is_placeholder_key_candidate_empty(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        svc = CodePlaceholderCatalogService()
        assert svc._is_placeholder_key_candidate("") is False

    def test_is_placeholder_key_candidate_no_match(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        svc = CodePlaceholderCatalogService()
        assert svc._is_placeholder_key_candidate("@invalid") is False

    def test_looks_like_template_placeholder_chinese(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        svc = CodePlaceholderCatalogService()
        assert svc._looks_like_template_placeholder("原告姓名") is True

    def test_looks_like_template_placeholder_english_only(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        svc = CodePlaceholderCatalogService()
        assert svc._looks_like_template_placeholder("plaintiff_name") is False


class TestCatalogServiceGetDefinition:
    def test_get_existing_definition(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        reg = CodePlaceholderRegistry()
        reg.clear()
        reg.register([
            CodePlaceholderDefinition(key="findme", source="test", category="c", display_name="Find Me"),
        ])
        svc = CodePlaceholderCatalogService()
        with patch.object(svc, "_from_registry", return_value=[]), \
             patch.object(svc, "_from_spec_files_scan", return_value=[]), \
             patch.object(svc, "_from_evidence_list", return_value=[]), \
             patch.object(svc, "_from_generation_ast_scan", return_value=[]):
            result = svc.get_definition("findme")
            assert result is not None
            assert result.display_name == "Find Me"

    def test_get_nonexistent_definition(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        reg = CodePlaceholderRegistry()
        reg.clear()
        svc = CodePlaceholderCatalogService()
        with patch.object(svc, "_from_registry", return_value=[]), \
             patch.object(svc, "_from_spec_files_scan", return_value=[]), \
             patch.object(svc, "_from_evidence_list", return_value=[]), \
             patch.object(svc, "_from_generation_ast_scan", return_value=[]):
            result = svc.get_definition("nonexistent")
            assert result is None

    def test_list_keys(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            CodePlaceholderCatalogService,
        )

        reg = CodePlaceholderRegistry()
        reg.clear()
        reg.register([
            CodePlaceholderDefinition(key="a", source="s", category="c"),
            CodePlaceholderDefinition(key="b", source="s", category="c"),
        ])
        svc = CodePlaceholderCatalogService()
        with patch.object(svc, "_from_registry", return_value=[]), \
             patch.object(svc, "_from_spec_files_scan", return_value=[]), \
             patch.object(svc, "_from_evidence_list", return_value=[]), \
             patch.object(svc, "_from_generation_ast_scan", return_value=[]):
            keys = svc.list_keys()
            assert "a" in keys
            assert "b" in keys


class TestExtractDefinitionsFromSpec:
    def test_extracts_from_spec(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            _extract_definitions_from_spec,
        )

        content = textwrap.dedent('''\
            class CasePlaceholderKeys:
                plaintiff_name = "原告姓名"
                defendant_name = "被告姓名"
        ''')
        tree = ast.parse(content)
        with patch("builtins.open", MagicMock()):
            with patch.object(Path, "read_text", return_value=content):
                defs = _extract_definitions_from_spec(Path("/fake/spec.py"))
                assert len(defs) == 2
                keys = {d.key for d in defs}
                assert "原告姓名" in keys
                assert "被告姓名" in keys

    def test_skips_non_placeholder_keys_classes(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            _extract_definitions_from_spec,
        )

        content = textwrap.dedent('''\
            class SomeOtherClass:
                value = "test"
        ''')
        with patch.object(Path, "read_text", return_value=content):
            defs = _extract_definitions_from_spec(Path("/fake/spec.py"))
            assert len(defs) == 0

    def test_syntax_error_returns_empty(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            _extract_definitions_from_spec,
        )

        with patch.object(Path, "read_text", return_value="invalid python {{{"):
            defs = _extract_definitions_from_spec(Path("/fake/spec.py"))
            assert len(defs) == 0

    def test_read_error_returns_empty(self):
        from apps.documents.services.code_placeholders.catalog_service import (
            _extract_definitions_from_spec,
        )

        with patch.object(Path, "read_text", side_effect=OSError("no file")):
            defs = _extract_definitions_from_spec(Path("/fake/spec.py"))
            assert len(defs) == 0


class TestScanPlaceholderSpecFiles:
    def test_empty_root(self):
        from apps.documents.services.code_placeholders.catalog_service import _scan_placeholder_spec_files

        with patch.object(Path, "exists", return_value=False):
            result = _scan_placeholder_spec_files(Path("/nonexistent"))
            assert result == []
