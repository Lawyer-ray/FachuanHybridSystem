"""Tests for unified placeholder fallback slash rules."""

from __future__ import annotations

import zipfile

import pytest

from apps.documents.services.generation.prompts import PromptSpec
from apps.documents.services.placeholders.fallback import (
    PLACEHOLDER_FALLBACK_VALUE,
    SANDBOXED_JINJA_ENV,
    build_docx_render_context,
    resolve_render_variable,
)
from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService


class _DocStub:
    def get_undeclared_template_variables(self, context: dict[str, object] | None = None) -> set[str]:
        if context and "known" in context:
            return {"missing_key"}
        return set()


def test_build_docx_render_context_fills_undeclared_with_slash() -> None:
    context = build_docx_render_context(doc=_DocStub(), context={"known": "ok"})

    assert context["known"] == "ok"
    assert context["missing_key"] == PLACEHOLDER_FALLBACK_VALUE


def test_resolve_render_variable_returns_slash_for_none_and_missing() -> None:
    hit, value = resolve_render_variable({"a": None}, "a")
    assert hit is False
    assert value == PLACEHOLDER_FALLBACK_VALUE

    hit_missing, value_missing = resolve_render_variable({}, "missing")
    assert hit_missing is False
    assert value_missing == PLACEHOLDER_FALLBACK_VALUE


def test_placeholder_render_service_renders_slash_for_missing_and_none() -> None:
    rendered, stats = PlaceholderRenderService().render(
        "姓名:{name};地址:{address}",
        {"name": None},
        syntax="single",
        keep_unmatched=True,
    )

    assert rendered == f"姓名:{PLACEHOLDER_FALLBACK_VALUE};地址:{PLACEHOLDER_FALLBACK_VALUE}"
    assert stats.placeholders_found == ["name", "address"]
    assert stats.placeholders_hit == []
    assert stats.placeholders_missed == ["name", "address"]


def _make_minimal_docx(path, body: str) -> None:
    """构造仅含 document.xml 的最小 docx，用于验证 docxtpl 沙箱渲染行为。"""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}</w:body></w:document>",
        )


def _read_docx_document_xml(path) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read("word/document.xml").decode("utf-8")


class TestSandboxedDocxRendering:
    """docxtpl 沙箱 Jinja2 渲染（安全审计：模板注入 RCE）。"""

    def test_sandbox_env_blocks_dunder_class_escape(self) -> None:
        from jinja2.sandbox import SecurityError

        with pytest.raises(SecurityError):
            SANDBOXED_JINJA_ENV.from_string("{{ ''.__class__.__mro__ }}").render({})

    def test_sandbox_env_blocks_attr_chain_escape(self) -> None:
        from jinja2.sandbox import SecurityError

        with pytest.raises(SecurityError):
            SANDBOXED_JINJA_ENV.from_string("{{ config.__class__.__init__.__globals__ }}").render(config={})

    def test_business_template_still_renders_in_sandbox(self, tmp_path) -> None:
        """业务模板的变量与 {%p %} 段落循环语法在沙箱 env 下不受影响。"""
        from docxtpl import DocxTemplate

        tpl = tmp_path / "normal.docx"
        _make_minimal_docx(
            tpl,
            "<w:p><w:r><w:t>案件：{{ case_name }}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{%p for item in items %}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>- {{ item }}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{%p endfor %}</w:t></w:r></w:p>",
        )

        doc = DocxTemplate(str(tpl))
        doc.render({"case_name": "测试案件", "items": ["甲", "乙"]}, jinja_env=SANDBOXED_JINJA_ENV)
        out = tmp_path / "normal_out.docx"
        doc.save(str(out))

        rendered = _read_docx_document_xml(out)
        assert "测试案件" in rendered
        assert "- 甲" in rendered
        assert "- 乙" in rendered

    def test_malicious_template_converted_to_business_error(self, tmp_path) -> None:
        """恶意模板表达式被沙箱拦截，并经渲染服务转为 ValidationException 业务错误而非 500。"""
        from apps.cases.services.template.unified.renderer import DocxRenderer
        from apps.core.exceptions import ValidationException
        from apps.core.utils.path import Path

        tpl = tmp_path / "evil.docx"
        _make_minimal_docx(
            tpl,
            '<w:p><w:r><w:t>{{ "".__class__.__mro__ }}</w:t></w:r></w:p>',
        )

        with pytest.raises(ValidationException):
            DocxRenderer().render(template_path=Path(str(tpl)), context={"case_name": "x"})


def test_prompt_spec_render_user_message_uses_slash_for_none_and_missing() -> None:
    prompt = PromptSpec(system_prompt="s", user_template="A:{a};B:{b}", format_instructions="")

    rendered = prompt.render_user_message({"a": None})

    assert rendered == f"A:{PLACEHOLDER_FALLBACK_VALUE};B:{PLACEHOLDER_FALLBACK_VALUE}"
