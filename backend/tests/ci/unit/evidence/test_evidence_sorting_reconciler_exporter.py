"""evidence_sorting/services/reconciler.py + exporter.py 单元测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence_sorting.services.reconciler import (
    DeliveryNote,
    LineItem,
    MonthGroup,
    ReconcileResult,
    ReconcilerService,
    StatementInfo,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    STATUS_MISSING,
    FOLDER_CONFIRMED,
    FOLDER_UNSIGNED,
    STATEMENT_PARSE_PROMPT,
)


class TestLineItem:
    def test_defaults(self) -> None:
        li = LineItem()
        assert li.date is None
        assert li.amount is None
        assert li.description == ""

    def test_with_values(self) -> None:
        li = LineItem(date="20260601", amount=100.5, description="发货")
        assert li.date == "20260601"
        assert li.amount == 100.5


class TestStatementInfo:
    def test_defaults(self) -> None:
        si = StatementInfo()
        assert si.month == ""
        assert si.total_amount is None
        assert si.signed is False
        assert si.line_items == []

    def test_with_values(self) -> None:
        items = [LineItem(date="20260601", amount=100)]
        si = StatementInfo(month="2026-06", total_amount=100.0, signed=True, line_items=items)
        assert si.month == "2026-06"
        assert len(si.line_items) == 1


class TestDeliveryNote:
    def test_defaults(self) -> None:
        dn = DeliveryNote()
        assert dn.match_status == STATUS_UNMATCHED
        assert dn.filename == ""
        assert dn.remark == ""


class TestMonthGroup:
    def test_defaults(self) -> None:
        mg = MonthGroup(month="2026年06月", folder_name="test")
        assert mg.statement is None
        assert mg.deliveries == []
        assert mg.issues == []


class TestReconcileResult:
    def test_defaults(self) -> None:
        rr = ReconcileResult()
        assert rr.month_groups == []
        assert rr.unsigned_statements == []
        assert rr.receipts == []
        assert rr.others == []
        assert rr.unmatched_deliveries == []


class TestReconcilerServiceNormalizeDate:
    def test_valid_8_digit_date(self) -> None:
        assert ReconcilerService._normalize_date("20260601") == "20260601"

    def test_date_with_separators(self) -> None:
        assert ReconcilerService._normalize_date("2026-06-01") == "20260601"

    def test_none_returns_none(self) -> None:
        assert ReconcilerService._normalize_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert ReconcilerService._normalize_date("") is None

    def test_non_8_digits_returns_none(self) -> None:
        assert ReconcilerService._normalize_date("202606") is None

    def test_numeric_input(self) -> None:
        assert ReconcilerService._normalize_date(20260601) == "20260601"


class TestReconcilerServiceToFloat:
    def test_none_returns_none(self) -> None:
        assert ReconcilerService._to_float(None) is None

    def test_float_value(self) -> None:
        assert ReconcilerService._to_float(100.5) == 100.5

    def test_string_number(self) -> None:
        assert ReconcilerService._to_float("123.45") == 123.45

    def test_string_with_commas(self) -> None:
        assert ReconcilerService._to_float("1,234.56") == 1234.56

    def test_invalid_string_returns_none(self) -> None:
        assert ReconcilerService._to_float("abc") is None


class TestReconcilerServiceExtractMonthKey:
    def setup_method(self) -> None:
        self.svc = ReconcilerService()

    def test_standard_format(self) -> None:
        si = StatementInfo(month="2022-08")
        assert self.svc._extract_month_key(si) == "2022年08月"

    def test_single_digit_month(self) -> None:
        si = StatementInfo(month="2022-1")
        assert self.svc._extract_month_key(si) == "2022年01月"

    def test_empty_month(self) -> None:
        si = StatementInfo(month="")
        assert self.svc._extract_month_key(si) == ""


class TestReconcilerServiceMonthKeyToYyyymm:
    def setup_method(self) -> None:
        self.svc = ReconcilerService()

    def test_standard_format(self) -> None:
        assert self.svc._month_key_to_yyyymm("2022年08月") == "202208"

    def test_invalid_format(self) -> None:
        assert self.svc._month_key_to_yyyymm("invalid") is None


class TestReconcilerServiceMatchDelivery:
    def setup_method(self) -> None:
        self.svc = ReconcilerService()

    def test_exact_match(self) -> None:
        li = LineItem(date="20260601", amount=100.0)
        dn = DeliveryNote(date="20260601", amount="100")
        assert self.svc._match_delivery(li, dn) is True

    def test_date_mismatch(self) -> None:
        li = LineItem(date="20260601", amount=100.0)
        dn = DeliveryNote(date="20260602", amount="100")
        assert self.svc._match_delivery(li, dn) is False

    def test_both_dates_none_returns_false(self) -> None:
        li = LineItem(amount=100.0)
        dn = DeliveryNote(amount="100")
        assert self.svc._match_delivery(li, dn) is False

    def test_invalid_delivery_amount_still_date_match(self) -> None:
        li = LineItem(date="20260601", amount=100.0)
        dn = DeliveryNote(date="20260601", amount="abc")
        assert self.svc._match_delivery(li, dn) is True


class TestReconcilerServiceParseLlmResponse:
    def setup_method(self) -> None:
        self.svc = ReconcilerService()

    def test_valid_json(self) -> None:
        data = {
            "month": "2022-08",
            "total_amount": 187480,
            "signed": True,
            "line_items": [{"date": "20220801", "amount": 10000, "description": "发货"}],
        }
        result = self.svc._parse_llm_response(json.dumps(data))
        assert result.month == "2022-08"
        assert result.total_amount == 187480.0
        assert result.signed is True
        assert len(result.line_items) == 1

    def test_json_in_markdown_block(self) -> None:
        data = {"month": "2022-09", "signed": False}
        text = f"```json\n{json.dumps(data)}\n```"
        result = self.svc._parse_llm_response(text)
        assert result.month == "2022-09"

    def test_invalid_json(self) -> None:
        result = self.svc._parse_llm_response("not json")
        assert result.month == ""

    def test_empty_line_items(self) -> None:
        data = {"month": "2022-08", "line_items": None}
        result = self.svc._parse_llm_response(json.dumps(data))
        assert result.line_items == []


class TestReconcilerServiceBuildFolderName:
    def setup_method(self) -> None:
        self.svc = ReconcilerService()

    def test_confirmed_with_deliveries(self) -> None:
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[DeliveryNote()])
        result = self.svc._build_folder_name("2022年08月", StatementInfo(signed=True), group, [])
        assert "对账单与出库单" in result
        assert FOLDER_CONFIRMED in result

    def test_unsigned_issue(self) -> None:
        group = MonthGroup(month="2022年08月", folder_name="")
        result = self.svc._build_folder_name("2022年08月", StatementInfo(signed=False), group, [FOLDER_UNSIGNED])
        assert FOLDER_UNSIGNED in result


class TestExporterServiceHelpers:
    def test_get_ext_with_extension(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        assert ExporterService._get_ext("test.jpg") == ".jpg"

    def test_get_ext_no_extension(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        assert ExporterService._get_ext("noext") == ".jpg"

    def test_get_ext_multiple_dots(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        assert ExporterService._get_ext("file.backup.pdf") == ".pdf"

    def test_write_image_normal_data(self) -> None:
        import base64, io, zipfile
        from apps.evidence_sorting.services.exporter import ExporterService
        data = base64.b64encode(b"fake image data").decode()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            ExporterService._write_image(zf, "test/img.jpg", data)
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            assert "test/img.jpg" in zf.namelist()

    def test_write_image_with_data_url_prefix(self) -> None:
        import base64, io, zipfile
        from apps.evidence_sorting.services.exporter import ExporterService
        raw = base64.b64encode(b"image bytes").decode()
        data = f"data:image/jpeg;base64,{raw}"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            ExporterService._write_image(zf, "test.jpg", data)
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            content = zf.read("test.jpg")
            assert content == b"image bytes"

    def test_build_filename_format(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        fn = ExporterService._build_filename()
        assert fn.startswith("evidence_sorting_")
        assert fn.endswith(".zip")


class TestExporterBuildDeliveryFilename:
    def test_basic_filename(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        dn = DeliveryNote(date="20260601", amount="100", filename="test.jpg", ocr_text="出库单明细")
        counter: dict[str, int] = {}
        svc = ExporterService()
        name = svc._build_delivery_filename(dn, counter)
        assert "20260601" in name
        assert "出库单" in name
        assert name.endswith(".jpg")

    def test_same_date_counter(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        dn1 = DeliveryNote(date="20260601", amount="100", filename="a.jpg", ocr_text="出库单")
        dn2 = DeliveryNote(date="20260601", amount="200", filename="b.jpg", ocr_text="出库单")
        counter: dict[str, int] = {}
        svc = ExporterService()
        svc._build_delivery_filename(dn1, counter)
        name2 = svc._build_delivery_filename(dn2, counter)
        assert "_2" in name2

    def test_no_date(self) -> None:
        from apps.evidence_sorting.services.exporter import ExporterService
        dn = DeliveryNote(amount="100", filename="test.jpg", ocr_text="出库单")
        counter: dict[str, int] = {}
        svc = ExporterService()
        name = svc._build_delivery_filename(dn, counter)
        assert "未知日期" in name


class TestStatementParsePrompt:
    def test_contains_placeholder(self) -> None:
        assert "{ocr_text}" in STATEMENT_PARSE_PROMPT
