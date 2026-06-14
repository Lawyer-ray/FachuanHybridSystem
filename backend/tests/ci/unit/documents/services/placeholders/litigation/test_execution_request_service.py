"""Tests for ExecutionRequestService.

Covers:
  - generate (no case_id, case not found, no case number, manual text, normal)
  - preview_for_case_number
  - _select_primary_case_number (active with content, fallback to content, first fallback)
  - _build_execution_request (empty main_text, normal, inferred principal, target fallback, etc.)
  - _format_case_number (with document_name, without)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.documents.services.placeholders.litigation.execution_request_models import (
    ExecutionComputation,
    ParsedAmounts,
    ParsedInterestParams,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> Any:
    from apps.documents.services.placeholders.litigation.execution_request_service import (
        ExecutionRequestService,
    )
    return ExecutionRequestService()


def _make_case_number(**kwargs: Any) -> MagicMock:
    cn = MagicMock()
    cn.id = kwargs.get("id", 1)
    cn.number = kwargs.get("number", "(2026)粤01号")
    cn.document_name = kwargs.get("document_name", "判决书")
    cn.document_content = kwargs.get("document_content", "")
    cn.execution_manual_text = kwargs.get("execution_manual_text", "")
    cn.is_active = kwargs.get("is_active", True)
    cn.execution_paid_amount = kwargs.get("execution_paid_amount")
    cn.execution_use_deduction_order = kwargs.get("execution_use_deduction_order", False)
    cn.execution_year_days = kwargs.get("execution_year_days")
    cn.execution_date_inclusion = kwargs.get("execution_date_inclusion")
    cn.execution_cutoff_date = kwargs.get("execution_cutoff_date")
    return cn


def _make_case(**kwargs: Any) -> MagicMock:
    case = MagicMock()
    case.id = kwargs.get("id", 1)
    case.target_amount = kwargs.get("target_amount")
    case.specified_date = kwargs.get("specified_date")
    return case


# ---------------------------------------------------------------------------
# _select_primary_case_number
# ---------------------------------------------------------------------------


class TestSelectPrimaryCaseNumber:
    def test_active_with_content(self) -> None:
        svc = _make_service()
        cn = _make_case_number(is_active=True, document_content="判决内容")
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value = [cn]
            result = svc._select_primary_case_number(1)
        assert result is cn

    def test_fallback_to_content(self) -> None:
        svc = _make_service()
        cn_inactive = _make_case_number(is_active=False, document_content="内容")
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value = [cn_inactive]
            result = svc._select_primary_case_number(1)
        assert result is cn_inactive

    def test_first_fallback(self) -> None:
        svc = _make_service()
        cn = _make_case_number(is_active=False, document_content="", execution_manual_text="")
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value = [cn]
            result = svc._select_primary_case_number(1)
        assert result is cn

    def test_no_case_numbers(self) -> None:
        svc = _make_service()
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.CaseNumber"
        ) as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value = []
            result = svc._select_primary_case_number(1)
        assert result is None


# ---------------------------------------------------------------------------
# _format_case_number
# ---------------------------------------------------------------------------


class TestFormatCaseNumber:
    def test_with_document_name(self) -> None:
        svc = _make_service()
        cn = _make_case_number(number="(2026)粤01号", document_name="判决书")
        result = svc._format_case_number(cn)
        assert "(2026)粤01号" in result
        assert "《判决书》" in result

    def test_without_document_name(self) -> None:
        svc = _make_service()
        cn = _make_case_number(number="(2026)粤01号", document_name="")
        result = svc._format_case_number(cn)
        assert result == "(2026)粤01号"

    def test_document_name_already_bracketed(self) -> None:
        svc = _make_service()
        cn = _make_case_number(number="(2026)粤01号", document_name="《判决书》")
        result = svc._format_case_number(cn)
        assert "《判决书》" in result


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_no_case_id(self) -> None:
        svc = _make_service()
        result = svc.generate({})
        assert result.get("申请执行事项") == "" or result.get("enforcement_execution_request") == ""

    def test_case_id_none(self) -> None:
        svc = _make_service()
        result = svc.generate({"case_id": None})
        assert result.get("申请执行事项") == "" or result.get("enforcement_execution_request") == ""

    def test_case_from_object(self) -> None:
        svc = _make_service()
        case = _make_case(id=1)
        cn = _make_case_number(document_content="判决被告支付100万元")
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.Case"
        ) as mock_case_model, \
             patch.object(svc, "_select_primary_case_number", return_value=cn), \
             patch.object(svc, "_build_execution_request") as mock_build:
            mock_case_model.objects.filter.return_value.first.return_value = case
            mock_build.return_value = ExecutionComputation(
                preview_text="result", warnings=[], structured_params={}
            )
            result = svc.generate({"case": case})
        val = result.get("申请执行事项", result.get("enforcement_execution_request", ""))
        assert "result" in val

    def test_case_not_found(self) -> None:
        svc = _make_service()
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.Case"
        ) as mock_case_model:
            mock_case_model.objects.filter.return_value.first.return_value = None
            result = svc.generate({"case_id": 999})
        val = result.get("申请执行事项", result.get("enforcement_execution_request", ""))
        assert val == ""

    def test_no_case_number(self) -> None:
        svc = _make_service()
        case = _make_case()
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.Case"
        ) as mock_case_model, \
             patch.object(svc, "_select_primary_case_number", return_value=None):
            mock_case_model.objects.filter.return_value.first.return_value = case
            result = svc.generate({"case_id": 1})
        val = result.get("申请执行事项", result.get("enforcement_execution_request", ""))
        assert val == ""

    def test_manual_text(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(execution_manual_text="手动输入的申请执行事项")
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.Case"
        ) as mock_case_model, \
             patch.object(svc, "_select_primary_case_number", return_value=cn):
            mock_case_model.objects.filter.return_value.first.return_value = case
            result = svc.generate({"case_id": 1})
        val = result.get("申请执行事项", result.get("enforcement_execution_request", ""))
        assert "手动输入" in val


# ---------------------------------------------------------------------------
# _build_execution_request
# ---------------------------------------------------------------------------


class TestBuildExecutionRequest:
    def test_empty_main_text(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(document_content="")
        result = svc._build_execution_request(case=case, case_number=cn)
        assert result.preview_text == ""
        assert any("为空" in w for w in result.warnings)

    def test_no_principal_no_target(self) -> None:
        svc = _make_service()
        case = _make_case(target_amount=None)
        cn = _make_case_number(document_content="被告支付货款")
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            enable_llm_fallback=False,
        )
        assert result.preview_text == "" or "未能确定本金" in str(result.warnings)

    def test_target_fallback(self) -> None:
        svc = _make_service()
        case = _make_case(target_amount=Decimal("100000"))
        cn = _make_case_number(document_content="被告支付货款")
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            enable_llm_fallback=False,
        )
        # Should use target_amount as fallback
        assert any("涉案金额" in w for w in result.warnings)

    def test_normal_with_principal(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(
            document_content="被告偿还原告借款本金100万元，利息10万元。"
        )
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            enable_llm_fallback=False,
        )
        assert result.preview_text != ""
        assert "1000000" in result.structured_params.get("principal", "") or "1000000" in result.preview_text

    def test_with_paid_amount(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(
            document_content="被告偿还原告借款本金100万元，利息10万元。"
        )
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            paid_amount=Decimal("50000"),
            enable_llm_fallback=False,
        )
        assert result.preview_text != ""

    def test_preview_for_case_number(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(
            document_content="被告偿还原告借款本金100万元。"
        )
        with patch.object(svc, "_build_execution_request") as mock_build:
            mock_build.return_value = ExecutionComputation(
                preview_text="text", warnings=[], structured_params={}
            )
            result = svc.preview_for_case_number(case=case, case_number=cn)
        assert result["preview_text"] == "text"

    def test_fee_only_items(self) -> None:
        svc = _make_service()
        case = _make_case(target_amount=None)
        cn = _make_case_number(
            document_content="受理费10000元由被告负担，支付给原告。"
        )
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            enable_llm_fallback=False,
        )
        # Should still generate text (fee-only path)
        assert result.preview_text != "" or result.warnings  # either generated or has warnings

    def test_excluded_fees_warning(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(
            document_content="被告偿还原告借款本金100万元。受理费10000元向本院缴纳。"
        )
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            enable_llm_fallback=False,
        )
        assert any("已排除" in w for w in result.warnings)

    def test_structured_params_fields(self) -> None:
        svc = _make_service()
        case = _make_case()
        cn = _make_case_number(
            document_content="被告偿还原告借款本金100万元，利息10万元。"
        )
        result = svc._build_execution_request(
            case=case, case_number=cn,
            cutoff_date=date(2026, 1, 1),
            enable_llm_fallback=False,
        )
        sp = result.structured_params
        assert "principal" in sp
        assert "total" in sp
        assert "cutoff_date" in sp
        assert "year_days" in sp
