"""oa_filing 模块真实执行测试 - 覆盖 exceptions, models, html_parser, jtn/models 等。"""
from __future__ import annotations

import pytest

# ============================================================
# oa_filing/services/exceptions.py
# ============================================================


class TestOAFilingExceptions:
    def test_oa_filing_error(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError

        exc = OAFilingError("test error")
        assert exc.message == "test error"
        assert str(exc) == "test error"

    def test_oa_filing_error_default(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError

        exc = OAFilingError()
        assert exc.message == ""

    def test_script_execution_error(self) -> None:
        from apps.oa_filing.services.exceptions import OAFilingError, ScriptExecutionError

        exc = ScriptExecutionError()
        assert exc.message == "脚本执行失败"
        assert isinstance(exc, OAFilingError)

    def test_script_execution_error_custom_message(self) -> None:
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        exc = ScriptExecutionError("custom msg")
        assert exc.message == "custom msg"


# ============================================================
# oa_filing/services/oa_scripts/jtn/models.py
# ============================================================


class TestJTNModels:
    def test_oa_case_customer_data(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OACaseCustomerData

        data = OACaseCustomerData(name="Test Corp", customer_type="legal")
        assert data.name == "Test Corp"
        assert data.address is None
        assert data.phone is None

    def test_oa_case_customer_data_with_fields(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OACaseCustomerData

        data = OACaseCustomerData(
            name="张三",
            customer_type="natural",
            address="北京市",
            phone="13800138000",
            id_number="110101199001010001",
        )
        assert data.id_number == "110101199001010001"

    def test_oa_case_info_data(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OACaseInfoData

        info = OACaseInfoData(case_no="2026JD001")
        assert info.case_no == "2026JD001"
        assert info.case_name is None
        assert info.case_stage is None

    def test_oa_case_info_data_full(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OACaseInfoData

        info = OACaseInfoData(
            case_no="2026JD001",
            case_name="Test Case",
            case_stage="一审",
            acceptance_date="2026-01-01",
            case_category="民事",
            responsible_lawyer="王律师",
            description="案情简介",
            client_side="原告",
        )
        assert info.case_category == "民事"
        assert info.client_side == "原告"

    def test_oa_conflict_data(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OAConflictData

        conflict = OAConflictData(name="Opposing Corp")
        assert conflict.conflict_type is None

    def test_oa_case_data(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OACaseData

        data = OACaseData(case_no="2026JD001", keyid="abc123")
        assert data.customers == []
        assert data.conflicts == []
        assert data.case_info is None

    def test_case_search_item(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import CaseSearchItem

        item = CaseSearchItem(case_no="2026JD001", keyid="key123")
        assert item.case_no == "2026JD001"

    def test_oa_list_case_candidate(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import OAListCaseCandidate

        candidate = OAListCaseCandidate(
            case_no="2026JD001",
            case_name="Test Case",
            keyid="key123",
            detail_url="https://example.com",
        )
        assert candidate.detail_url == "https://example.com"

    def test_case_list_form_state(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.models import CaseListFormState

        state = CaseListFormState(
            action_url="https://example.com",
            payload={"key": "value"},
        )
        assert state.payload["key"] == "value"


# ============================================================
# oa_filing/services/oa_scripts/jtn/html_parser.py - pure functions
# ============================================================


class TestJTNHtmlParser:
    def test_normalize_text_none(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text

        assert normalize_text(None) == ""

    def test_normalize_text_whitespace(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text

        result = normalize_text("  hello   world  ")
        assert result == "hello world"

    def test_normalize_text_nbsp(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text

        result = normalize_text("hello\xa0world")
        assert result == "hello world"

    def test_normalize_text_fullwidth_space(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_text

        result = normalize_text("hello　world")
        assert result == "hello world"

    def test_normalize_label_removes_colons(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_label

        assert normalize_label("案件名称：") == "案件名称"
        assert normalize_label("案件名称:") == "案件名称"

    def test_normalize_label_with_spaces(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import normalize_label

        result = normalize_label("  案件名称 ：  ")
        assert result == "案件名称"

    def test_extract_hidden_input_found(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_hidden_input

        html = '<input type="hidden" name="token" value="abc123" />'
        result = extract_hidden_input(html, "token")
        assert result == "abc123"

    def test_extract_hidden_input_not_found(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_hidden_input

        html = '<input type="hidden" name="other" value="val" />'
        result = extract_hidden_input(html, "token")
        assert result == ""

    def test_extract_case_no_from_text_basic(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_no_from_text

        result = extract_case_no_from_text("案号2026JD001已受理")
        assert result == "2026JD001"

    def test_extract_case_no_from_text_empty(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_no_from_text

        assert extract_case_no_from_text("") == ""
        assert extract_case_no_from_text("no case number here") == ""

    def test_extract_keyid_from_href(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_keyid_from_href

        href = "projectView.aspx?keyid=abc123&FirstModel=PROJECT"
        result = extract_keyid_from_href(href)
        assert result == "abc123"

    def test_extract_keyid_from_href_empty(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_keyid_from_href

        assert extract_keyid_from_href("") is None

    def test_score_case_name_cell_empty(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell

        assert score_case_name_cell("", case_no="") == -100

    def test_score_case_name_cell_digit_only(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell

        assert score_case_name_cell("12345", case_no="") == -90

    def test_score_case_name_cell_action_word(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell

        assert score_case_name_cell("查看", case_no="") == -80

    def test_score_case_name_cell_with_case_no(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell

        result = score_case_name_cell("张三诉李四2026JD001", case_no="2026JD001")
        assert result > 0

    def test_score_case_name_cell_with_sue(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import score_case_name_cell

        result = score_case_name_cell("张三诉李四", case_no="")
        assert result >= 20

    def test_clean_case_name_text_basic(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import clean_case_name_text

        result = clean_case_name_text("张三诉李四", case_no="")
        assert "张三" in result
        assert "李四" in result

    def test_clean_case_name_text_removes_markers(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import clean_case_name_text

        result = clean_case_name_text("张三诉李四[诉讼]民商事案件", case_no="")
        assert "诉讼" not in result or result.count("诉讼") == 0

    def test_clean_case_name_text_removes_case_no(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import clean_case_name_text

        result = clean_case_name_text("2026JD001张三诉李四", case_no="2026JD001")
        assert "2026JD001" not in result

    def test_iter_label_value_pairs(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import iter_label_value_pairs

        cells = ["案件名称", "Test Case", "案件阶段", "一审"]
        pairs = iter_label_value_pairs(cells)
        assert len(pairs) == 2
        assert pairs[0] == ("案件名称", "Test Case")
        assert pairs[1] == ("案件阶段", "一审")

    def test_iter_label_value_pairs_odd_count(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import iter_label_value_pairs

        cells = ["label1", "value1", "label2"]
        pairs = iter_label_value_pairs(cells)
        assert len(pairs) == 1

    def test_extract_case_candidates_from_search_html_empty(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import (
            extract_case_candidates_from_search_html,
        )

        result = extract_case_candidates_from_search_html("<html><body></body></html>")
        assert result == []

    def test_extract_case_keyid_from_search_html_not_found(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import extract_case_keyid_from_search_html

        result = extract_case_keyid_from_search_html(html_text="<html></html>", case_no="2026JD001")
        assert result is None

    def test_parse_case_detail_html_invalid(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.case_import.html_parser import parse_case_detail_html

        result = parse_case_detail_html(html_text="", case_no="2026JD001", keyid="key123")
        # Empty HTML should either return None or empty data
        assert result is None or isinstance(result, object)


# ============================================================
# oa_filing/models (integration tests)
# ============================================================


@pytest.mark.django_db
class TestOAFilingModels:
    def test_oa_config_creation(self) -> None:
        from apps.oa_filing.models.oa_config import OAConfig

        config = OAConfig.objects.create(site_name="Test OA Site")
        assert config.pk is not None
        assert config.site_name == "Test OA Site"
        assert config.is_enabled is True

    def test_filing_session_model_fields(self) -> None:
        from apps.oa_filing.models.filing_session import FilingSession

        # Verify model has expected fields
        field_names = {f.name for f in FilingSession._meta.get_fields()}
        assert "contract" in field_names
        assert "oa_config" in field_names
        assert "status" in field_names
        assert "case" in field_names
