"""Unit tests for cases.services.template.unified.resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


class TestTemplateResolverInit:
    """Test constructor."""

    def test_init_with_defaults(self) -> None:
        from apps.cases.services.template.unified.resolver import TemplateResolver

        r = TemplateResolver()
        assert r._document_service is None

    def test_init_with_injected_service(self) -> None:
        from apps.cases.services.template.unified.resolver import TemplateResolver

        doc_svc = MagicMock()
        r = TemplateResolver(document_service=doc_svc)
        assert r.document_service is doc_svc


class TestTemplateResolverResolve:
    """resolve method tests."""

    def _make_resolver(self, doc_svc=None):
        from apps.cases.services.template.unified.resolver import TemplateResolver

        return TemplateResolver(document_service=doc_svc or MagicMock())

    def test_both_none_raises(self) -> None:
        resolver = self._make_resolver()
        with pytest.raises(ValidationException, match="必须提供 template_id 或 function_code"):
            resolver.resolve(template_id=None, function_code=None)

    def test_empty_function_code_with_none_template_raises(self) -> None:
        resolver = self._make_resolver()
        with pytest.raises(ValidationException, match="必须提供 template_id 或 function_code"):
            resolver.resolve(template_id=None, function_code="")

    def test_resolve_by_template_id(self) -> None:
        doc_svc = MagicMock()
        tpl = MagicMock()
        tpl.id = 10
        tpl.name = "测试模板"
        tpl.function_code = "TC001"
        tpl.file_path = "/some/path.docx"
        doc_svc.get_template_by_id_internal.return_value = tpl

        resolver = self._make_resolver(doc_svc)

        with patch.object(resolver, "_get_template_path") as mock_path:
            mock_path.return_value = "/some/path.docx"
            result = resolver.resolve(template_id=10, function_code=None)
            assert result.template is tpl
            assert result.effective_function_code == "TC001"

    def test_resolve_by_function_code(self) -> None:
        doc_svc = MagicMock()
        tpl = MagicMock()
        tpl.id = 20
        tpl.name = "功能模板"
        tpl.function_code = None
        tpl.file_path = "/func/path.docx"
        doc_svc.get_template_by_function_code_internal.return_value = tpl

        resolver = self._make_resolver(doc_svc)

        with patch.object(resolver, "_get_template_path") as mock_path:
            mock_path.return_value = "/func/path.docx"
            result = resolver.resolve(template_id=None, function_code="FC001")
            assert result.template is tpl
            assert result.effective_function_code == "FC001"

    def test_template_id_takes_priority(self) -> None:
        doc_svc = MagicMock()
        tpl = MagicMock()
        tpl.id = 30
        tpl.function_code = "FC002"
        tpl.file_path = "/prio/path.docx"
        doc_svc.get_template_by_id_internal.return_value = tpl

        resolver = self._make_resolver(doc_svc)

        with patch.object(resolver, "_get_template_path") as mock_path:
            mock_path.return_value = "/prio/path.docx"
            result = resolver.resolve(template_id=30, function_code="FC999")
            doc_svc.get_template_by_id_internal.assert_called_once_with(30)
            doc_svc.get_template_by_function_code_internal.assert_not_called()


class TestTemplateResolverGetTemplateInfo:
    """get_template_info tests."""

    def test_returns_expected_keys(self) -> None:
        doc_svc = MagicMock()
        tpl = MagicMock()
        tpl.id = 1
        tpl.name = "测试"
        tpl.function_code = "TC001"
        tpl.description = "描述"
        tpl.template_type = "civil"
        tpl.is_active = True
        tpl.file_path = "/path.docx"
        doc_svc.get_template_by_id_internal.return_value = tpl

        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=doc_svc)
        with patch.object(resolver, "_get_template_path") as mock_path:
            mock_path.return_value = "/path.docx"
            info = resolver.get_template_info(template_id=1, function_code=None)
            assert info["id"] == 1
            assert info["name"] == "测试"
            assert info["function_code"] == "TC001"
            assert info["is_active"] is True


class TestTemplateResolverGetTemplateByFunctionCode:
    """_get_template_by_function_code tests."""

    def test_not_found_raises(self) -> None:
        doc_svc = MagicMock()
        doc_svc.get_template_by_function_code_internal.return_value = None

        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=doc_svc)
        with pytest.raises(NotFoundError, match="未找到功能标识"):
            resolver._get_template_by_function_code("FC_NOT_EXIST")

    def test_found_returns_template(self) -> None:
        doc_svc = MagicMock()
        tpl = MagicMock()
        doc_svc.get_template_by_function_code_internal.return_value = tpl

        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=doc_svc)
        assert resolver._get_template_by_function_code("FC001") is tpl


class TestTemplateResolverGetTemplateById:
    """_get_template_by_id tests."""

    def test_not_found_raises(self) -> None:
        doc_svc = MagicMock()
        doc_svc.get_template_by_id_internal.return_value = None

        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=doc_svc)
        with pytest.raises(NotFoundError, match="模板不存在"):
            resolver._get_template_by_id(999)

    def test_found_returns_template(self) -> None:
        doc_svc = MagicMock()
        tpl = MagicMock()
        doc_svc.get_template_by_id_internal.return_value = tpl

        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=doc_svc)
        assert resolver._get_template_by_id(1) is tpl


class TestTemplateResolverGetTemplatePath:
    """_get_template_path tests."""

    def test_empty_path_raises(self) -> None:
        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=MagicMock())
        tpl = MagicMock()
        tpl.file_path = ""
        tpl.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            resolver._get_template_path(tpl)

    def test_none_path_raises(self) -> None:
        from apps.cases.services.template.unified.resolver import TemplateResolver

        resolver = TemplateResolver(document_service=MagicMock())
        tpl = MagicMock()
        tpl.file_path = None
        tpl.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            resolver._get_template_path(tpl)


class TestResolvedTemplate:
    """ResolvedTemplate dataclass tests."""

    def test_frozen(self) -> None:
        from apps.cases.services.template.unified.resolver import ResolvedTemplate

        rt = ResolvedTemplate(
            template=MagicMock(),
            template_path="/path",
            effective_function_code="FC001",
        )
        assert rt.template_path == "/path"
        assert rt.effective_function_code == "FC001"
