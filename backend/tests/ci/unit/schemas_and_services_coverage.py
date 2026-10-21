"""Tests for automation/schemas/preservation.py (missing: 9 lines) +
automation/schemas/captcha.py (missing: 1 line) +
automation/schemas/court_document.py (missing: 1 line).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


# ── Preservation schemas ──────────────────────────────────────────────────


class TestPreservationQuoteCreateSchema:
    def test_valid_data(self) -> None:
        from plugins.court_automation.preservation_quote.schemas import PreservationQuoteCreateSchema

        result = PreservationQuoteCreateSchema(
            preserve_amount=Decimal("100000"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
        )
        assert result.preserve_amount == Decimal("100000")

    def test_negative_amount_raises(self) -> None:
        from plugins.court_automation.preservation_quote.schemas import PreservationQuoteCreateSchema

        with pytest.raises(Exception):
            PreservationQuoteCreateSchema(
                preserve_amount=Decimal("-100"),
                corp_id="440100",
                category_id="1",
                credential_id=1,
            )

    def test_empty_corp_id_raises(self) -> None:
        from plugins.court_automation.preservation_quote.schemas import PreservationQuoteCreateSchema

        with pytest.raises(Exception):
            PreservationQuoteCreateSchema(
                preserve_amount=Decimal("100000"),
                corp_id="",
                category_id="1",
                credential_id=1,
            )

    def test_whitespace_corp_id_stripped(self) -> None:
        from plugins.court_automation.preservation_quote.schemas import PreservationQuoteCreateSchema

        result = PreservationQuoteCreateSchema(
            preserve_amount=Decimal("100000"),
            corp_id="  440100  ",
            category_id="1",
            credential_id=1,
        )
        assert result.corp_id == "440100"


class TestInsuranceQuoteSchema:
    def test_config_json_encoders(self) -> None:
        from plugins.court_automation.preservation_quote.schemas import InsuranceQuoteSchema

        assert InsuranceQuoteSchema.Config.json_encoders is not None


class TestPreservationQuoteSchemaFromModel:
    def test_from_model(self) -> None:
        from plugins.court_automation.preservation_quote.schemas import PreservationQuoteSchema

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
        from plugins.court_automation.preservation_quote.schemas import QuoteListItemSchema

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
        import pytest as _pytest

        from apps.automation.schemas.court_document import APIInterceptResponseSchema

        # validator 要求每项含 9 个拦截平台字段（#511 存量用例传 {"key": "value"}
        # 必然触发校验失败，此处改为合规数据 + 缺字段负例两段断言）
        full_item = {
            "c_sdbh": "SD001",
            "c_stbh": "TB001",
            "wjlj": "/media/x.pdf",
            "c_wsbh": "WS001",
            "c_wsmc": "测试文书",
            "c_fybh": "FY001",
            "c_fymc": "测试法院",
            "c_wjgs": "2",
            "dt_cjsj": "2026-10-04",
        }
        result = APIInterceptResponseSchema(
            code=200,
            msg="ok",
            data=[full_item],
            success=True,
            totalRows=1,
        )
        assert len(result.data) == 1

        with _pytest.raises(ValueError, match="缺少必需字段"):
            APIInterceptResponseSchema(
                code=200,
                msg="ok",
                data=[{"key": "value"}],
                success=True,
                totalRows=1,
            )
