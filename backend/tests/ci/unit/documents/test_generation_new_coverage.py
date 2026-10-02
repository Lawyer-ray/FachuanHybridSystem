"""
Tests for documents/services/generation/ - prompts,
path_utils, output_storage, pipeline modules.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestPromptSpec:
    def test_render_user_message_basic(self):
        from apps.documents.services.generation.prompts import PromptSpec

        spec = PromptSpec(
            system_prompt="sys",
            user_template="Hello {name}, {format_instructions}",
            format_instructions="be concise",
        )
        result = spec.render_user_message({"name": "World"})
        assert "Hello World" in result
        assert "be concise" in result

    def test_render_user_message_none_value_uses_fallback(self):
        from apps.documents.services.generation.prompts import PromptSpec

        spec = PromptSpec(
            system_prompt="sys",
            user_template="{name} - {format_instructions}",
            format_instructions="",
        )
        result = spec.render_user_message({"name": None})
        from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE

        assert PLACEHOLDER_FALLBACK_VALUE in result

    def test_render_user_message_missing_key_uses_fallback(self):
        from apps.documents.services.generation.prompts import PromptSpec

        spec = PromptSpec(
            system_prompt="sys",
            user_template="{missing_key} - {format_instructions}",
            format_instructions="",
        )
        result = spec.render_user_message({})
        from apps.documents.services.placeholders.fallback import PLACEHOLDER_FALLBACK_VALUE

        assert PLACEHOLDER_FALLBACK_VALUE in result

    def test_render_empty_values(self):
        from apps.documents.services.generation.prompts import PromptSpec

        spec = PromptSpec(
            system_prompt="sys",
            user_template="{format_instructions}",
            format_instructions="ok",
        )
        result = spec.render_user_message(None)
        assert "ok" in result


class TestPathUtils:
    def test_resolve_media_path_empty(self):
        from apps.documents.services.generation.path_utils import resolve_media_path

        assert resolve_media_path("/media", "") == ""
        assert resolve_media_path("/media", "  ") == ""

    def test_resolve_media_path_http(self):
        from apps.documents.services.generation.path_utils import resolve_media_path

        assert resolve_media_path("/media", "http://example.com/file.pdf") == ""
        assert resolve_media_path("/media", "https://example.com/file.pdf") == ""

    def test_resolve_media_path_with_media_prefix(self):
        from apps.documents.services.generation.path_utils import resolve_media_path

        result = resolve_media_path("/media_root", "/media/test.pdf")
        assert "test.pdf" in result

    def test_resolve_media_path_absolute(self):
        from apps.documents.services.generation.path_utils import resolve_media_path

        # 安全审计 B-04：MEDIA_ROOT 之外的绝对路径拒绝（返回空串）
        result = resolve_media_path("/media", "/absolute/path/file.pdf")
        assert result == ""

    def test_resolve_media_path_relative(self):
        from apps.documents.services.generation.path_utils import resolve_media_path

        result = resolve_media_path("/media_root", "subdir/file.pdf")
        assert "subdir/file.pdf" in result
        assert "media_root" in result

    def test_safe_name(self):
        from apps.documents.services.generation.path_utils import safe_name

        assert safe_name("test/file") == "test／file"
        assert safe_name("test\\file") == "test＼file"
        assert safe_name("test\nfile") == "test file"
        assert safe_name("") == "未命名"
        assert safe_name("  ") == "未命名"

    def test_safe_arcname(self):
        from apps.documents.services.generation.path_utils import safe_arcname

        assert safe_arcname("dir/file.txt") == "dir/file.txt"
        assert safe_arcname("dir\\file.txt") == "dir/file.txt"
        assert safe_arcname("a//b") == "a/b"


class TestOutputStorage:
    def test_media_root_from_config(self, tmp_path):
        from apps.documents.services.generation.output_storage import GeneratedDocumentStorage

        store = GeneratedDocumentStorage(media_root=str(tmp_path))
        assert str(store.media_root) == str(tmp_path)

    def test_media_root_raises_when_not_configured(self):
        from apps.documents.services.generation.output_storage import GeneratedDocumentStorage

        store = GeneratedDocumentStorage(media_root=None)
        with patch("apps.core.config.get_config", return_value=None):
            with pytest.raises(RuntimeError, match="未配置"):
                _ = store.media_root

    def test_save_bytes(self, tmp_path):
        from apps.documents.services.generation.output_storage import GeneratedDocumentStorage

        store = GeneratedDocumentStorage(media_root=str(tmp_path))
        with patch("apps.documents.services.generation.output_storage.default_storage") as mock_storage:
            mock_storage.save.return_value = "sub/test.txt"
            result = store.save_bytes(relative_dir="sub", filename="test.txt", content=b"hello")
            assert "test.txt" in result
            mock_storage.save.assert_called_once()
            call_args = mock_storage.save.call_args
            assert call_args[0][0] == "sub/test.txt"

    def test_save_for_case(self, tmp_path):
        from apps.documents.services.generation.output_storage import GeneratedDocumentStorage

        store = GeneratedDocumentStorage(media_root=str(tmp_path))
        with patch("apps.documents.services.generation.output_storage.default_storage") as mock_storage:
            mock_storage.save.side_effect = lambda rel, f: rel
            result = store.save_for_case(case_id=42, filename="doc.docx", content=b"data")
            assert "case_42" in result


class TestNaming:
    def test_normalize_version(self):
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("V1") == "1"
        assert _normalize_version("v2") == "2"
        assert _normalize_version("V1.0") == "1.0"
        assert _normalize_version("3") == "3"

    def test_contract_docx_filename(self):
        from apps.documents.services.generation.pipeline.naming import contract_docx_filename

        with patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService") as mock_svc:
            mock_svc.render_generated_doc.return_value = "合同-测试-V1-20240101"
            result = contract_docx_filename(template_name="合同.docx", contract_name="测试", version="V1")
            assert result.endswith(".docx")

    def test_supplementary_agreement_docx_filename(self):
        from apps.documents.services.generation.pipeline.naming import supplementary_agreement_docx_filename

        with patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService") as mock_svc:
            mock_svc.render_generated_doc.return_value = "补充协议-测试-V1-20240101"
            result = supplementary_agreement_docx_filename(agreement_name="补充协议", contract_name="测试")
            assert result.endswith(".docx")


class TestTemplateMatcher:
    @pytest.mark.django_db
    def test_match_contract_template_no_templates(self):
        from apps.documents.services.generation.pipeline.template_matcher import TemplateMatcher

        matcher = TemplateMatcher()
        result = matcher.match_contract_template("civil")
        assert result is None

    @pytest.mark.django_db
    def test_match_supplementary_agreement_template_no_templates(self):
        from apps.documents.services.generation.pipeline.template_matcher import TemplateMatcher

        matcher = TemplateMatcher()
        result = matcher.match_supplementary_agreement_template("civil")
        assert result is None

    @pytest.mark.django_db
    def test_match_folder_template_no_templates(self):
        from apps.documents.services.generation.pipeline.template_matcher import TemplateMatcher

        matcher = TemplateMatcher()
        result = matcher.match_folder_template("civil")
        assert result is None
