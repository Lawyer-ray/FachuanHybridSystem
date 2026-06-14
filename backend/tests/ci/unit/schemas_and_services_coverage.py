"""Tests for automation/schemas/preservation.py (missing: 9 lines) +
automation/schemas/captcha.py (missing: 1 line) +
automation/schemas/court_document.py (missing: 1 line) +
workbench/services/chat_service.py (missing: 15 lines for _estimate_tokens).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ── Preservation schemas ──────────────────────────────────────────────────


class TestPreservationQuoteCreateSchema:
    def test_valid_data(self) -> None:
        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema
        result = PreservationQuoteCreateSchema(
            preserve_amount=Decimal("100000"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
        )
        assert result.preserve_amount == Decimal("100000")

    def test_negative_amount_raises(self) -> None:
        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema
        with pytest.raises(Exception):
            PreservationQuoteCreateSchema(
                preserve_amount=Decimal("-100"),
                corp_id="440100",
                category_id="1",
                credential_id=1,
            )

    def test_empty_corp_id_raises(self) -> None:
        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema
        with pytest.raises(Exception):
            PreservationQuoteCreateSchema(
                preserve_amount=Decimal("100000"),
                corp_id="",
                category_id="1",
                credential_id=1,
            )

    def test_whitespace_corp_id_stripped(self) -> None:
        from apps.automation.schemas.preservation import PreservationQuoteCreateSchema
        result = PreservationQuoteCreateSchema(
            preserve_amount=Decimal("100000"),
            corp_id="  440100  ",
            category_id="1",
            credential_id=1,
        )
        assert result.corp_id == "440100"


class TestInsuranceQuoteSchema:
    def test_config_json_encoders(self) -> None:
        from apps.automation.schemas.preservation import InsuranceQuoteSchema
        assert InsuranceQuoteSchema.Config.json_encoders is not None


class TestPreservationQuoteSchemaFromModel:
    def test_from_model(self) -> None:
        from apps.automation.schemas.preservation import PreservationQuoteSchema
        obj = SimpleNamespace(
            id=1,
            preserve_amount=Decimal("50000"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
            status="completed",
            total_companies=5,
            success_count=3,
            failed_count=2,
            error_message=None,
            created_at=datetime.now(),
            started_at=datetime.now(),
            finished_at=datetime.now(),
            quotes=MagicMock(all=MagicMock(return_value=[])),
        )
        result = PreservationQuoteSchema.from_model(obj)
        assert result.id == 1
        assert result.quotes == []


class TestQuoteListItemSchemaFromModel:
    def test_from_model(self) -> None:
        from apps.automation.schemas.preservation import QuoteListItemSchema
        obj = SimpleNamespace(
            id=1,
            preserve_amount=Decimal("100000"),
            corp_id="440100",
            category_id="1",
            status="completed",
            total_companies=10,
            success_count=8,
            failed_count=2,
            created_at=datetime.now(),
            started_at=datetime.now(),
            finished_at=datetime.now(),
            get_success_rate=MagicMock(return_value=80.0),
        )
        result = QuoteListItemSchema.from_model(obj)
        assert result.success_rate == 80.0


# ── Captcha schema ───────────────────────────────────────────────────────


class TestCaptchaRecognizeIn:
    def test_valid_base64(self) -> None:
        import base64
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        data = base64.b64encode(b"test image").decode()
        result = CaptchaRecognizeIn(image_base64=data)
        assert result.image_base64 == data

    def test_with_data_url_prefix(self) -> None:
        import base64
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        data = base64.b64encode(b"test").decode()
        result = CaptchaRecognizeIn(image_base64=f"data:image/png;base64,{data}")
        assert result.image_base64 == data

    def test_invalid_base64_raises(self) -> None:
        from apps.automation.schemas.captcha import CaptchaRecognizeIn
        with pytest.raises(Exception):
            CaptchaRecognizeIn(image_base64="not-valid-base64!!")


# ── Court document schema ────────────────────────────────────────────────


class TestAPIInterceptResponseSchema:
    def test_valid_data(self) -> None:
        from apps.automation.schemas.court_document import APIInterceptResponseSchema
        result = APIInterceptResponseSchema(
            code=200,
            msg="ok",
            data=[],
            success=True,
            totalRows=0,
        )
        assert result.code == 200

    def test_validate_data_structure(self) -> None:
        from apps.automation.schemas.court_document import APIInterceptResponseSchema
        result = APIInterceptResponseSchema(
            code=200,
            msg="ok",
            data=[{"key": "value"}],
            success=True,
            totalRows=1,
        )
        assert len(result.data) == 1


# ── Chat service _estimate_tokens ────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        assert _estimate_tokens("") == 0

    def test_chinese_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("你好世界")
        assert result > 0

    def test_english_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("hello world")
        assert result > 0

    def test_mixed_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("Hello 你好")
        assert result > 0


class TestConvertToModelMessages:
    def test_user_message(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        from pydantic_ai.messages import ModelRequest, UserPromptPart
        msg = SimpleNamespace(role="user", content="hello", tool_output=None, tool_call_id=None, tool_name=None)
        result = _convert_to_model_messages([msg])
        assert len(result) == 1
        assert isinstance(result[0], ModelRequest)
        assert isinstance(result[0].parts[0], UserPromptPart)

    def test_assistant_message(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        from pydantic_ai.messages import ModelResponse, TextPart
        msg = SimpleNamespace(role="assistant", content="response", tool_output=None, tool_call_id=None, tool_name=None)
        result = _convert_to_model_messages([msg])
        assert len(result) == 1
        assert isinstance(result[0], ModelResponse)

    def test_tool_message(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        from pydantic_ai.messages import ModelRequest, ToolReturnPart
        msg = SimpleNamespace(
            role="tool",
            content="result",
            tool_output={"result": "data"},
            tool_call_id="tc_123",
            tool_name="search",
        )
        result = _convert_to_model_messages([msg])
        assert len(result) == 1
        assert isinstance(result[0], ModelRequest)
        assert isinstance(result[0].parts[0], ToolReturnPart)

    def test_unknown_role_skipped(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        msg = SimpleNamespace(role="system", content="ignore", tool_output=None, tool_call_id=None, tool_name=None)
        result = _convert_to_model_messages([msg])
        assert len(result) == 0


class TestBatchServiceHelpers:
    def test_is_excel_true(self) -> None:
        from apps.workbench.services.batch_service import _is_excel
        assert _is_excel("data.xlsx") is True
        assert _is_excel("data.xls") is True
        assert _is_excel("data.XLSX") is True

    def test_is_excel_false(self) -> None:
        from apps.workbench.services.batch_service import _is_excel
        assert _is_excel("doc.docx") is False
        assert _is_excel("file.txt") is False
        assert _is_excel("") is False
        assert _is_excel("noext") is False

    def test_validate_files_empty(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        from apps.core.exceptions import ValidationException
        svc = BatchAnalysisService()
        with pytest.raises(ValidationException):
            svc.validate_files([])

    def test_validate_files_invalid_ext(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        from apps.core.exceptions import ValidationException
        svc = BatchAnalysisService()
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        with pytest.raises(ValidationException, match="不支持"):
            svc.validate_files([mock_file])

    def test_validate_files_valid(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService
        svc = BatchAnalysisService()
        mock_file = MagicMock()
        mock_file.name = "test.docx"
        svc.validate_files([mock_file])  # should not raise
