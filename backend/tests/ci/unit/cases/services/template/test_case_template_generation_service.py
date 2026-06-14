"""Unit tests for cases.services.template.case_template_generation_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


class TestCaseTemplateGenerationServiceIsLegalRepCertTemplate:
    """_is_legal_rep_cert_template tests."""

    def test_legal_rep_cert_returns_true(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.name = "法定代表人身份证明书"
        assert svc._is_legal_rep_cert_template(tpl) is True

    def test_other_name_returns_false(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.name = "授权委托书"
        assert svc._is_legal_rep_cert_template(tpl) is False


class TestCaseTemplateGenerationServiceIsPowerOfAttorneyTemplate:
    """_is_power_of_attorney_template tests."""

    def test_power_of_attorney_returns_true(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.name = "授权委托书"
        assert svc._is_power_of_attorney_template(tpl) is True

    def test_other_name_returns_false(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.name = "起诉状"
        assert svc._is_power_of_attorney_template(tpl) is False


class TestCaseTemplateGenerationServiceSafeName:
    """_safe_name tests."""

    def test_normal_name(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        assert svc._safe_name("测试合同") == "测试合同"

    def test_empty_name_returns_default(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        assert svc._safe_name("") == "未命名"

    def test_none_name_returns_default(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        assert svc._safe_name(None) == "未命名"  # type: ignore[arg-type]

    def test_slash_replaced(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        assert "/" not in svc._safe_name("a/b")
        assert "/" not in svc._safe_name("a/b")

    def test_backslash_replaced(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        result = svc._safe_name("a\\b")
        assert "\\" not in result

    def test_newline_replaced(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        assert "\n" not in svc._safe_name("a\nb")

    def test_whitespace_normalized(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        result = svc._safe_name("  hello   world  ")
        assert result == "hello world"

    def test_whitespace_only_returns_default(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        assert svc._safe_name("   ") == "未命名"


class TestCaseTemplateGenerationServiceBuildFilename:
    """_build_filename tests."""

    def _make_svc(self):
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        return CaseTemplateGenerationService()

    def test_normal_template(self) -> None:
        svc = self._make_svc()
        result = svc._build_filename(template_name="起诉状", case_name="张三案")
        assert "起诉状" in result
        assert "张三案" in result
        assert result.endswith(".docx")

    def test_legal_rep_cert_with_client(self) -> None:
        svc = self._make_svc()
        result = svc._build_filename(
            template_name="法定代表人身份证明书",
            case_name="张三案",
            client_name="甲公司",
        )
        assert "甲公司" in result
        assert "法定代表人身份证明书" in result
        assert result.endswith(".docx")

    def test_power_of_attorney_single_client(self) -> None:
        svc = self._make_svc()
        result = svc._build_filename(
            template_name="授权委托书",
            case_name="张三案",
            client_name="张三",
            is_combined=False,
            our_party_count=1,
        )
        assert "授权委托书" in result
        assert "张三案" in result

    def test_power_of_attorney_individual_multi_parties(self) -> None:
        svc = self._make_svc()
        result = svc._build_filename(
            template_name="授权委托书",
            case_name="张三案",
            client_name="张三",
            is_combined=False,
            our_party_count=3,
        )
        assert "张三" in result
        assert "张三案" in result

    def test_power_of_attorney_combined(self) -> None:
        svc = self._make_svc()
        result = svc._build_filename(
            template_name="授权委托书",
            case_name="张三案",
            client_name="张三",
            is_combined=True,
            our_party_count=3,
        )
        assert "张三案" in result


class TestCaseTemplateGenerationServiceGetCase:
    """_get_case tests."""

    def test_case_not_found(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        with patch("apps.cases.services.template.case_template_generation_service.get_case_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_case_model_internal.return_value = None
            mock_get.return_value = mock_service
            with pytest.raises(NotFoundError, match="案件不存在"):
                svc._get_case(1)

    def test_case_found(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        expected_case = MagicMock()
        with patch("apps.cases.services.template.case_template_generation_service.get_case_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_case_model_internal.return_value = expected_case
            mock_get.return_value = mock_service
            assert svc._get_case(1) is expected_case


class TestCaseTemplateGenerationServiceGetTemplate:
    """_get_template tests."""

    def test_template_not_found(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        with patch("apps.cases.services.template.case_template_generation_service.get_document_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_template_by_id_internal.return_value = None
            mock_get.return_value = mock_service
            with pytest.raises(NotFoundError, match="模板不存在"):
                svc._get_template(1)

    def test_template_found(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        expected_tpl = MagicMock()
        with patch("apps.cases.services.template.case_template_generation_service.get_document_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_template_by_id_internal.return_value = expected_tpl
            mock_get.return_value = mock_service
            assert svc._get_template(1) is expected_tpl


class TestCaseTemplateGenerationServiceGetTemplatePath:
    """_get_template_path tests."""

    def test_empty_path_raises(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.file_path = ""
        tpl.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            svc._get_template_path(tpl)

    def test_none_path_raises(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.file_path = None
        tpl.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            svc._get_template_path(tpl)


class TestCaseTemplateGenerationServiceCountOurParties:
    """_count_our_parties tests."""

    def test_returns_count(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        case = MagicMock()
        case.parties.filter.return_value.count.return_value = 3
        assert svc._count_our_parties(case) == 3


class TestCaseTemplateGenerationServiceGetOurClient:
    """_get_our_client tests."""

    def test_client_not_found(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        with patch("apps.cases.services.template.case_template_generation_service.get_client_service") as mock_get:
            mock_service = MagicMock()
            mock_service.get_client_internal.return_value = None
            mock_get.return_value = mock_service
            case = MagicMock()
            with pytest.raises(ValidationException, match="当事人不存在"):
                svc._get_our_client(case, 10)

    def test_client_not_party_of_case(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        with patch("apps.cases.services.template.case_template_generation_service.get_client_service") as mock_get:
            mock_service = MagicMock()
            mock_client_dto = MagicMock()
            mock_service.get_client_internal.return_value = mock_client_dto
            mock_get.return_value = mock_service
            case = MagicMock()
            case.parties.filter.return_value.exists.return_value = False
            with pytest.raises(ValidationException, match="当事人非我方当事人"):
                svc._get_our_client(case, 10)


class TestCaseTemplateGenerationServiceGetOurLegalClient:
    """_get_our_legal_client tests."""

    def test_natural_person_raises(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        with patch("apps.cases.services.template.case_template_generation_service.get_client_service") as mock_get:
            mock_service = MagicMock()
            mock_client_dto = MagicMock()
            mock_service.get_client_internal.return_value = mock_client_dto
            mock_service.is_natural_person_internal.return_value = True
            mock_get.return_value = mock_service
            case = MagicMock()
            case.parties.filter.return_value.exists.return_value = True
            with pytest.raises(ValidationException, match="当事人非法人"):
                svc._get_our_legal_client(case, 10)


class TestCaseTemplateGenerationServiceGenerateDocument:
    """generate_document integration tests (all mocked)."""

    def test_legal_rep_cert_requires_client_id(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        tpl = MagicMock()
        tpl.name = "法定代表人身份证明书"
        tpl.id = 1

        with (
            patch.object(svc, "_get_case", return_value=MagicMock()),
            patch.object(svc, "_get_template", return_value=tpl),
            patch.object(svc, "_get_template_path", return_value=MagicMock()),
        ):
            with pytest.raises(ValidationException, match="请先选择我方法人当事人"):
                svc.generate_document(case_id=1, template_id=1)

    def test_missing_case_raises(self) -> None:
        from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService

        svc = CaseTemplateGenerationService()
        with patch.object(svc, "_get_case", side_effect=NotFoundError("not found")):
            with pytest.raises(NotFoundError):
                svc.generate_document(case_id=1, template_id=1)
