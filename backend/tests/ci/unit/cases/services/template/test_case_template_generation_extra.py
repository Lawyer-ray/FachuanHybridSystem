"""Tests for cases/services/template/case_template_generation_service.py — uncovered branches.

Covers: _build_filename with all template types, _safe_name, _is_legal_rep_cert_template,
_is_power_of_attorney_template, _get_template_path, _get_our_client, _get_our_legal_client.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


def _make_service():
    from apps.cases.services.template.case_template_generation_service import CaseTemplateGenerationService
    return CaseTemplateGenerationService()


class TestBuildFilename:
    def test_legal_rep_cert_with_client_name(self):
        svc = _make_service()
        result = svc._build_filename(
            template_name="法定代表人身份证明书",
            case_name="案件A",
            client_name="甲公司",
            is_combined=False,
            our_party_count=1,
        )
        assert "法定代表人身份证明书" in result
        assert "甲公司" in result
        assert result.endswith(".docx")

    def test_power_of_attorney_individual_multi_party(self):
        svc = _make_service()
        result = svc._build_filename(
            template_name="授权委托书",
            case_name="案件B",
            client_name="张三",
            is_combined=False,
            our_party_count=3,
        )
        assert "授权委托书" in result
        assert "张三" in result
        assert "案件B" in result

    def test_power_of_attorney_combined(self):
        svc = _make_service()
        result = svc._build_filename(
            template_name="授权委托书",
            case_name="案件C",
            client_name="李四",
            is_combined=True,
            our_party_count=3,
        )
        assert "授权委托书" in result
        assert "案件C" in result
        assert "李四" not in result

    def test_power_of_attorney_single_party(self):
        svc = _make_service()
        result = svc._build_filename(
            template_name="授权委托书",
            case_name="案件D",
            client_name="王五",
            is_combined=False,
            our_party_count=1,
        )
        assert "授权委托书" in result
        assert "案件D" in result
        assert "王五" not in result

    def test_regular_template(self):
        svc = _make_service()
        result = svc._build_filename(
            template_name="民事起诉状",
            case_name="案件E",
        )
        assert "民事起诉状" in result
        assert "案件E" in result
        assert result.endswith(".docx")

    def test_date_in_filename(self):
        svc = _make_service()
        date_str = datetime.now().strftime("%Y%m%d")
        result = svc._build_filename(template_name="模板", case_name="案件")
        assert date_str in result


class TestSafeName:
    def test_normal(self):
        svc = _make_service()
        assert svc._safe_name("正常名称") == "正常名称"

    def test_empty_returns_unnamed(self):
        svc = _make_service()
        assert svc._safe_name("") == "未命名"
        assert svc._safe_name(None) == "未命名"

    def test_whitespace_only_returns_unnamed(self):
        svc = _make_service()
        assert svc._safe_name("   ") == "未命名"

    def test_slash_replaced(self):
        svc = _make_service()
        assert "/" not in svc._safe_name("a/b")

    def test_backslash_replaced(self):
        svc = _make_service()
        assert "\\" not in svc._safe_name("a\\b")

    def test_newlines_replaced(self):
        svc = _make_service()
        result = svc._safe_name("a\nb\rc\td")
        assert "\n" not in result
        assert "\r" not in result
        assert "\t" not in result
        assert result == "a b c d"


class TestIsTemplateType:
    def test_legal_rep_cert(self):
        svc = _make_service()
        t = MagicMock()
        t.name = "法定代表人身份证明书"
        assert svc._is_legal_rep_cert_template(t) is True

    def test_not_legal_rep_cert(self):
        svc = _make_service()
        t = MagicMock()
        t.name = "其他模板"
        assert svc._is_legal_rep_cert_template(t) is False

    def test_power_of_attorney(self):
        svc = _make_service()
        t = MagicMock()
        t.name = "授权委托书"
        assert svc._is_power_of_attorney_template(t) is True

    def test_not_power_of_attorney(self):
        svc = _make_service()
        t = MagicMock()
        t.name = "其他模板"
        assert svc._is_power_of_attorney_template(t) is False


class TestGetTemplatePath:
    def test_empty_path(self):
        svc = _make_service()
        t = MagicMock()
        t.file_path = ""
        t.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            svc._get_template_path(t)

    def test_none_path(self):
        svc = _make_service()
        t = MagicMock()
        t.file_path = None
        t.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            svc._get_template_path(t)

    def test_whitespace_only_path(self):
        svc = _make_service()
        t = MagicMock()
        t.file_path = "   "
        t.id = 1
        with pytest.raises(ValidationException, match="模板文件路径为空"):
            svc._get_template_path(t)

    def test_path_not_exists(self):
        svc = _make_service()
        t = MagicMock()
        t.file_path = "/nonexistent/path.docx"
        t.id = 1
        with patch("apps.cases.services.template.case_template_generation_service.Path") as MockPath:
            MockPath.return_value.exists.return_value = False
            with pytest.raises(ValidationException, match="模板文件不存在"):
                svc._get_template_path(t)

    def test_valid_path(self):
        svc = _make_service()
        t = MagicMock()
        t.file_path = "/valid/path.docx"
        t.id = 1
        with patch("apps.cases.services.template.case_template_generation_service.Path") as MockPath:
            MockPath.return_value.exists.return_value = True
            result = svc._get_template_path(t)
            assert result is not None


class TestGetCaseNotFound:
    def test_case_not_found(self):
        svc = _make_service()
        with patch("apps.cases.services.template.case_template_generation_service.get_case_service") as mock_get:
            mock_cs = MagicMock()
            mock_cs.get_case_model_internal.return_value = None
            mock_get.return_value = mock_cs
            with pytest.raises(NotFoundError):
                svc._get_case(1)


class TestGetTemplateNotFound:
    def test_template_not_found(self):
        svc = _make_service()
        with patch("apps.cases.services.template.case_template_generation_service.get_document_service") as mock_get:
            mock_ds = MagicMock()
            mock_ds.get_template_by_id_internal.return_value = None
            mock_get.return_value = mock_ds
            with pytest.raises(NotFoundError):
                svc._get_template(1)


class TestCountOurParties:
    def test_count(self):
        svc = _make_service()
        mock_case = MagicMock()
        mock_case.parties.filter.return_value.count.return_value = 3
        assert svc._count_our_parties(mock_case) == 3


class TestGetOurClientNotFound:
    def test_client_not_found(self):
        svc = _make_service()
        with patch("apps.cases.services.template.case_template_generation_service.get_client_service") as mock_get:
            mock_cs = MagicMock()
            mock_cs.get_client_internal.return_value = None
            mock_get.return_value = mock_cs
            case = MagicMock()
            with pytest.raises(ValidationException, match="当事人不存在"):
                svc._get_our_client(case, 99)

    def test_client_not_party(self):
        svc = _make_service()
        with patch("apps.cases.services.template.case_template_generation_service.get_client_service") as mock_get:
            mock_cs = MagicMock()
            mock_cs.get_client_internal.return_value = MagicMock()
            mock_get.return_value = mock_cs
            case = MagicMock()
            case.parties.filter.return_value.exists.return_value = False
            with pytest.raises(ValidationException, match="非我方当事人"):
                svc._get_our_client(case, 10)


class TestGetOurLegalClient:
    def test_natural_person_raises(self):
        svc = _make_service()
        with patch.object(svc, '_get_our_client') as mock_get_our:
            mock_client = MagicMock()
            mock_get_our.return_value = mock_client
            with patch("apps.cases.services.template.case_template_generation_service.get_client_service") as mock_get:
                mock_cs = MagicMock()
                mock_cs.is_natural_person_internal.return_value = True
                mock_get.return_value = mock_cs
                case = MagicMock()
                with pytest.raises(ValidationException, match="非法人"):
                    svc._get_our_legal_client(case, 10)
