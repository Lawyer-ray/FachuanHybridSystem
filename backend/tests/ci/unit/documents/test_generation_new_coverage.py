"""
Tests for documents/services/generation/ - registry, prompts, base_generator,
path_utils, output_storage, pipeline modules.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch
from pathlib import Path as RealPath

import pytest


class TestGeneratorRegistry:
    def _reset_registry(self):
        from apps.documents.services.generation.registry import GeneratorRegistry

        GeneratorRegistry._instance = None
        GeneratorRegistry._generators = {}
        return GeneratorRegistry

    def test_singleton(self):
        Registry = self._reset_registry()
        r1 = Registry()
        r2 = Registry()
        assert r1 is r2

    def test_register_and_get(self):
        Registry = self._reset_registry()

        @Registry.register
        class TestGen:
            name = "test_gen_1"
            display_name = "Test Gen"

        registry = Registry()
        assert "test_gen_1" in registry
        assert len(registry) == 1
        gen = registry.get_generator("test_gen_1")
        assert gen.name == "test_gen_1"

    def test_register_without_name_raises(self):
        Registry = self._reset_registry()

        with pytest.raises(ValueError, match="必须定义 name"):

            @Registry.register
            class NoNameGen:
                pass

    def test_duplicate_name_raises(self):
        Registry = self._reset_registry()

        @Registry.register
        class Gen1:
            name = "dup_gen"

        with pytest.raises(Exception):

            @Registry.register
            class Gen2:
                name = "dup_gen"

    def test_get_nonexistent_raises(self):
        Registry = self._reset_registry()
        registry = Registry()
        with pytest.raises(Exception, match="不存在"):
            registry.get_generator("nonexistent")

    def test_list_generators(self):
        Registry = self._reset_registry()

        @Registry.register
        class G1:
            name = "list_g1"

        @Registry.register
        class G2:
            name = "list_g2"

        registry = Registry()
        names = registry.list_generators()
        assert "list_g1" in names
        assert "list_g2" in names

    def test_get_generators_for_template_type(self):
        Registry = self._reset_registry()

        @Registry.register
        class ContractGen:
            name = "ct_gen"
            template_type = "contract"

        @Registry.register
        class CaseGen:
            name = "case_gen"
            template_type = "case"

        registry = Registry()
        contract_gens = registry.get_generators_for_template_type("contract")
        assert len(contract_gens) == 1

    def test_get_generators_by_category(self):
        Registry = self._reset_registry()

        @Registry.register
        class LitGen:
            name = "lit_gen"
            category = "litigation"

        registry = Registry()
        lit_gens = registry.get_generators_by_category("litigation")
        assert len(lit_gens) == 1

    def test_clear_registry(self):
        Registry = self._reset_registry()

        @Registry.register
        class TGen:
            name = "clear_gen"

        registry = Registry()
        assert len(registry) == 1
        registry.clear_registry()
        assert len(registry) == 0

    def test_get_registry_info(self):
        Registry = self._reset_registry()

        @Registry.register
        class InfoGen:
            name = "info_gen"
            display_name = "Info Generator"
            description = "A test generator"
            category = "general"
            template_type = "contract"

        registry = Registry()
        info = registry.get_registry_info()
        assert "info_gen" in info
        assert info["info_gen"]["display_name"] == "Info Generator"

    def test_str_repr(self):
        Registry = self._reset_registry()
        registry = Registry()
        assert "GeneratorRegistry" in str(registry)

    def test_contains(self):
        Registry = self._reset_registry()

        @Registry.register
        class CGen:
            name = "cont_gen"

        registry = Registry()
        assert "cont_gen" in registry
        assert "nope" not in registry


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

        result = resolve_media_path("/media", "/absolute/path/file.pdf")
        assert result == "/absolute/path/file.pdf"

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
        result = store.save_bytes(relative_dir="sub", filename="test.txt", content=b"hello")
        assert "test.txt" in result
        assert (tmp_path / "sub" / "test.txt").read_bytes() == b"hello"

    def test_save_for_case(self, tmp_path):
        from apps.documents.services.generation.output_storage import GeneratedDocumentStorage

        store = GeneratedDocumentStorage(media_root=str(tmp_path))
        result = store.save_for_case(case_id=42, filename="doc.docx", content=b"data")
        assert "case_42" in result
        assert "doc.docx" in result


class TestNaming:
    def test_normalize_version(self):
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("V1") == "1"
        assert _normalize_version("v2") == "2"
        assert _normalize_version("V1.0") == "1.0"
        assert _normalize_version("3") == "3"

    def test_contract_docx_filename(self):
        from apps.documents.services.generation.pipeline.naming import contract_docx_filename

        with patch(
            "apps.documents.services.generation.pipeline.naming.FilenameTemplateService"
        ) as mock_svc:
            mock_svc.render_generated_doc.return_value = "合同-测试-V1-20240101"
            result = contract_docx_filename(
                template_name="合同.docx", contract_name="测试", version="V1"
            )
            assert result.endswith(".docx")

    def test_supplementary_agreement_docx_filename(self):
        from apps.documents.services.generation.pipeline.naming import (
            supplementary_agreement_docx_filename,
        )

        with patch(
            "apps.documents.services.generation.pipeline.naming.FilenameTemplateService"
        ) as mock_svc:
            mock_svc.render_generated_doc.return_value = "补充协议-测试-V1-20240101"
            result = supplementary_agreement_docx_filename(
                agreement_name="补充协议", contract_name="测试"
            )
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


class TestBaseGenerator:
    def test_sanitize_filename(self):
        from apps.documents.services.generation.base_generator import BaseGenerator

        class DummyGen(BaseGenerator):
            name = "dummy"

            def get_required_placeholders(self):
                return []

            def generate(self, context, template_path, output_dir):
                pass

        gen = DummyGen()
        assert gen._sanitize_filename("test<file>:name") == "test_file__name"
        assert gen._sanitize_filename("  .dots.  ") == "dots"
        assert gen._sanitize_filename("") == "document"

    def test_get_output_filename(self):
        from apps.documents.services.generation.base_generator import BaseGenerator

        class DummyGen(BaseGenerator):
            name = "dummy"

            def get_required_placeholders(self):
                return []

            def generate(self, context, template_path, output_dir):
                pass

        gen = DummyGen()
        result = gen.get_output_filename({"contract_name": "Test"}, "template")
        assert "Test" in result
        assert "template" in result
        assert result.endswith(".docx")

    def test_validate_context(self):
        from apps.documents.services.generation.base_generator import BaseGenerator

        class DummyGen(BaseGenerator):
            name = "dummy"

            def get_required_placeholders(self):
                return ["a", "b"]

            def generate(self, context, template_path, output_dir):
                pass

        gen = DummyGen()
        is_valid, missing = gen.validate_context({"a": "val1"})
        assert not is_valid
        assert "b" in missing

        is_valid, missing = gen.validate_context({"a": "val1", "b": "val2"})
        assert is_valid
        assert not missing

    def test_context_builder_lazy_load(self):
        from apps.documents.services.generation.base_generator import BaseGenerator

        class DummyGen(BaseGenerator):
            name = "dummy"

            def get_required_placeholders(self):
                return []

            def generate(self, context, template_path, output_dir):
                pass

        gen = DummyGen(context_builder=None)
        cb = gen.context_builder
        assert cb is not None

    def test_str_repr(self):
        from apps.documents.services.generation.base_generator import BaseGenerator

        class DummyGen(BaseGenerator):
            name = "test_gen"
            display_name = "Test Generator"
            category = "general"

            def get_required_placeholders(self):
                return []

            def generate(self, context, template_path, output_dir):
                pass

        gen = DummyGen()
        assert "Test Generator" in str(gen)
        assert "DummyGen" in repr(gen)
