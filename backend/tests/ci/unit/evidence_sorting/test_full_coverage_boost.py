"""Tests for evidence_sorting services: reconciler, classifier, exporter."""
from __future__ import annotations

import json
import zipfile
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest

from apps.evidence_sorting.services.classifier import (
    TYPE_DELIVERY,
    TYPE_OTHER,
    TYPE_RECEIPT,
    TYPE_STATEMENT,
    ClassifiedImage,
    ClassifierService,
    ClassifyResult,
)
from apps.evidence_sorting.services.reconciler import (
    FOLDER_CONFIRMED,
    FOLDER_DELIVERY_MISMATCH,
    FOLDER_DELIVERY_NOT_ENOUGH,
    FOLDER_MISSING_DELIVERY,
    FOLDER_UNSIGNED,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    DeliveryNote,
    LineItem,
    MonthGroup,
    ReconcileResult,
    ReconcilerService,
    StatementInfo,
)
from apps.evidence_sorting.services.exporter import ExporterService


# ---------------------------------------------------------------------------
# ClassifierService
# ---------------------------------------------------------------------------


class TestClassifyByKeywords:
    """Tests for ClassifierService._classify_by_keywords."""

    def _svc(self) -> ClassifierService:
        return ClassifierService()

    def test_statement_keywords(self) -> None:
        svc = self._svc()
        assert svc._classify_by_keywords("这是对账单") == TYPE_STATEMENT
        assert svc._classify_by_keywords("月度汇总报告") == TYPE_STATEMENT
        assert svc._classify_by_keywords("月结单") == TYPE_STATEMENT

    def test_delivery_keywords(self) -> None:
        svc = self._svc()
        assert svc._classify_by_keywords("出库单") == TYPE_DELIVERY
        assert svc._classify_by_keywords("发货单") == TYPE_DELIVERY
        assert svc._classify_by_keywords("承运单") == TYPE_DELIVERY
        assert svc._classify_by_keywords("提货单") == TYPE_DELIVERY

    def test_receipt_keywords(self) -> None:
        svc = self._svc()
        assert svc._classify_by_keywords("收款凭证") == TYPE_RECEIPT
        assert svc._classify_by_keywords("微信支付") == TYPE_RECEIPT
        assert svc._classify_by_keywords("支付宝") == TYPE_RECEIPT
        assert svc._classify_by_keywords("中国农业银行电子回单") == TYPE_RECEIPT

    def test_empty_text_png_is_statement(self) -> None:
        svc = self._svc()
        assert svc._classify_by_keywords("", "photo.png") == TYPE_STATEMENT

    def test_empty_text_jpg_is_other(self) -> None:
        svc = self._svc()
        assert svc._classify_by_keywords("", "scan.jpg") == TYPE_OTHER

    def test_no_keyword_match_is_other(self) -> None:
        svc = self._svc()
        assert svc._classify_by_keywords("some random text here") == TYPE_OTHER

    def test_compound_keywords_highest_score_wins(self) -> None:
        svc = self._svc()
        # Both statement and delivery keywords present, but more delivery ones
        text = "出库单 发货单 出仓单 对账单"
        result = svc._classify_by_keywords(text)
        assert result in (TYPE_STATEMENT, TYPE_DELIVERY)


class TestClassifierExtractDate:
    """Tests for ClassifierService._extract_date."""

    def _svc(self) -> ClassifierService:
        return ClassifierService()

    def test_cn_format(self) -> None:
        svc = self._svc()
        assert svc._extract_date("2023年10月5日") == "20231005"

    def test_dash_format(self) -> None:
        svc = self._svc()
        assert svc._extract_date("2023-01-15") == "20230115"

    def test_slash_format(self) -> None:
        svc = self._svc()
        assert svc._extract_date("2023/12/31") == "20231231"

    def test_no_date_found(self) -> None:
        svc = self._svc()
        assert svc._extract_date("no date here") is None

    def test_month_padding(self) -> None:
        svc = self._svc()
        assert svc._extract_date("2023年3月9日") == "20230309"


class TestClassifierExtractAmount:
    """Tests for ClassifierService._extract_amount."""

    def _svc(self) -> ClassifierService:
        return ClassifierService()

    def test_yuan_symbol(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("¥123,456.78") == "123456.78"

    def test_yuan_char(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("123456.78元") == "123456.78"

    def test_label_colon(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("金额：50000") == "50000"

    def test_heji(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("合计：88,000") == "88000"

    def test_zongji(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("总计: 100000") == "100000"

    def test_largest_amount_wins(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("金额：1000 合计：5000") == "5000"

    def test_no_amount(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("no numbers here") is None

    def test_integer_amount_no_decimal(self) -> None:
        svc = self._svc()
        assert svc._extract_amount("金额：10000元") == "10000"


class TestClassifierDetectSigned:
    """Tests for ClassifierService._detect_signed."""

    def _svc(self) -> ClassifierService:
        return ClassifierService()

    def test_signed(self) -> None:
        svc = self._svc()
        assert svc._detect_signed("本对账单已签名确认") is True

    def test_unsigned(self) -> None:
        svc = self._svc()
        assert svc._detect_signed("本月对账单内容如下") is False

    def test_gaizhang(self) -> None:
        svc = self._svc()
        assert svc._detect_signed("已盖章") is True


# ---------------------------------------------------------------------------
# ReconcilerService
# ---------------------------------------------------------------------------


class TestReconcilerParseLlmResponse:
    """Tests for ReconcilerService._parse_llm_response."""

    def _svc(self) -> ReconcilerService:
        return ReconcilerService()

    def test_valid_json(self) -> None:
        svc = self._svc()
        text = json.dumps({
            "month": "2023-08",
            "total_amount": 187480,
            "signed": True,
            "line_items": [
                {"date": "20230801", "amount": 50000, "description": "item1"},
                {"date": "20230815", "amount": 60000, "description": "item2"},
            ],
        })
        info = svc._parse_llm_response(text)
        assert info.month == "2023-08"
        assert info.total_amount == 187480.0
        assert info.signed is True
        assert len(info.line_items) == 2
        assert info.line_items[0].date == "20230801"

    def test_json_in_code_block(self) -> None:
        svc = self._svc()
        text = '```json\n{"month": "2023-01", "total_amount": 100, "signed": false, "line_items": []}\n```'
        info = svc._parse_llm_response(text)
        assert info.month == "2023-01"

    def test_json_in_braces(self) -> None:
        svc = self._svc()
        text = 'here is {"month": "2023-06", "signed": true, "line_items": []} done'
        info = svc._parse_llm_response(text)
        assert info.month == "2023-06"

    def test_invalid_json_returns_empty(self) -> None:
        svc = self._svc()
        info = svc._parse_llm_response("not json at all")
        assert info.month == ""
        assert info.line_items == []

    def test_null_line_items(self) -> None:
        svc = self._svc()
        text = json.dumps({"month": "2023-05", "signed": False, "line_items": None})
        info = svc._parse_llm_response(text)
        assert info.line_items == []


class TestReconcilerNormalizeDate:
    def test_valid(self) -> None:
        assert ReconcilerService._normalize_date("20231005") == "20231005"

    def test_with_dashes(self) -> None:
        assert ReconcilerService._normalize_date("2023-10-05") == "20231005"

    def test_short(self) -> None:
        assert ReconcilerService._normalize_date("2023105") is None

    def test_none(self) -> None:
        assert ReconcilerService._normalize_date(None) is None

    def test_empty(self) -> None:
        assert ReconcilerService._normalize_date("") is None


class TestReconcilerToFloat:
    def test_none(self) -> None:
        assert ReconcilerService._to_float(None) is None

    def test_int(self) -> None:
        assert ReconcilerService._to_float(100) == 100.0

    def test_str_with_comma(self) -> None:
        assert ReconcilerService._to_float("123,456") == 123456.0

    def test_invalid(self) -> None:
        assert ReconcilerService._to_float("abc") is None

    def test_decimal_str(self) -> None:
        assert ReconcilerService._to_float("3.14") == 3.14


class TestReconcilerExtractMonthKey:
    def _svc(self) -> ReconcilerService:
        return ReconcilerService()

    def test_single_month(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-08")
        assert svc._extract_month_key(st) == "2022年08月"

    def test_cross_month(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-01~2022-02")
        result = svc._extract_month_key(st)
        assert result == "2022年01-02月"

    def test_empty_month(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="")
        assert svc._extract_month_key(st) == ""

    def test_single_digit_month(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-3")
        assert svc._extract_month_key(st) == "2022年03月"


class TestReconcilerMonthKeyToYyyymm:
    def _svc(self) -> ReconcilerService:
        return ReconcilerService()

    def test_valid(self) -> None:
        assert self._svc()._month_key_to_yyyymm("2022年08月") == "202208"

    def test_invalid(self) -> None:
        assert self._svc()._month_key_to_yyyymm("abc") is None


class TestReconcilerMatchDelivery:
    def _svc(self) -> ReconcilerService:
        return ReconcilerService()

    def test_exact_match(self) -> None:
        svc = self._svc()
        li = LineItem(date="20230801", amount=50000.0)
        dn = DeliveryNote(date="20230801", amount="50000")
        assert svc._match_delivery(li, dn) is True

    def test_date_mismatch(self) -> None:
        svc = self._svc()
        li = LineItem(date="20230801", amount=50000.0)
        dn = DeliveryNote(date="20230802", amount="50000")
        assert svc._match_delivery(li, dn) is False

    def test_both_dates_none(self) -> None:
        svc = self._svc()
        li = LineItem(date=None, amount=50000.0)
        dn = DeliveryNote(date=None, amount="50000")
        assert svc._match_delivery(li, dn) is False

    def test_date_only_match(self) -> None:
        svc = self._svc()
        li = LineItem(date="20230801", amount=50000.0)
        dn = DeliveryNote(date="20230801", amount="99999")
        # Amount doesn't match but date does
        assert svc._match_delivery(li, dn) is True

    def test_tolerance_match(self) -> None:
        svc = self._svc()
        li = LineItem(date="20230801", amount=50000.0)
        dn = DeliveryNote(date="20230801", amount="50400")
        # Within 1% tolerance
        assert svc._match_delivery(li, dn) is True

    def test_invalid_amount_text(self) -> None:
        svc = self._svc()
        li = LineItem(date="20230801", amount=50000.0)
        dn = DeliveryNote(date="20230801", amount="abc")
        # Amount parsing fails, but date matches
        assert svc._match_delivery(li, dn) is True

    def test_no_line_date_no_delivery_date(self) -> None:
        svc = self._svc()
        li = LineItem(date=None, amount=100.0)
        dn = DeliveryNote(date="20230801", amount="100")
        # line_item has no date, delivery has date -> not matching
        assert svc._match_delivery(li, dn) is True


class TestReconcilerBuildFolderName:
    def _svc(self) -> ReconcilerService:
        return ReconcilerService()

    def test_confirmed(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-08", signed=True)
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[])
        result = svc._build_folder_name("2022年08月", st, group, [])
        assert FOLDER_CONFIRMED in result

    def test_unsigned(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-08", signed=False)
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[])
        result = svc._build_folder_name("2022年08月", st, group, [FOLDER_UNSIGNED])
        assert FOLDER_UNSIGNED in result

    def test_with_deliveries(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-08", signed=True)
        dn = DeliveryNote(filename="d1.pdf", date="20220801", amount="100")
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[dn])
        result = svc._build_folder_name("2022年08月", st, group, [])
        assert "对账单与出库单" in result

    def test_unmatched_count(self) -> None:
        svc = self._svc()
        st = StatementInfo(month="2022-08", signed=True)
        dn = DeliveryNote(filename="d1.pdf", date="20220801", amount="100", match_status=STATUS_UNMATCHED)
        group = MonthGroup(month="2022年08月", folder_name="", deliveries=[dn])
        result = svc._build_folder_name(
            "2022年08月", st, group, [FOLDER_DELIVERY_MISMATCH]
        )
        assert "出库单无法确认" in result


# ---------------------------------------------------------------------------
# ExporterService
# ---------------------------------------------------------------------------


class TestExporterGetExt:
    def test_with_extension(self) -> None:
        assert ExporterService._get_ext("file.pdf") == ".pdf"

    def test_no_extension(self) -> None:
        assert ExporterService._get_ext("noext") == ".jpg"

    def test_multiple_dots(self) -> None:
        assert ExporterService._get_ext("file.name.pdf") == ".pdf"


class TestExporterBuildDeliveryFilename:
    def test_basic(self) -> None:
        svc = ExporterService()
        dn = DeliveryNote(filename="test.pdf", date="20230801", amount="50000", ocr_text="出库单内容")
        counter: dict[str, int] = {}
        name = svc._build_delivery_filename(dn, counter)
        assert "20230801" in name
        assert "出库单" in name

    def test_no_date(self) -> None:
        svc = ExporterService()
        dn = DeliveryNote(filename="test.pdf", date=None, amount="50000", ocr_text="出库单")
        name = svc._build_delivery_filename(dn, {})
        assert "未知日期" in name

    def test_no_amount(self) -> None:
        svc = ExporterService()
        dn = DeliveryNote(filename="test.pdf", date="20230801", amount=None, ocr_text="出库单")
        name = svc._build_delivery_filename(dn, {})
        assert "_50000" not in name

    def test_same_date_counter(self) -> None:
        svc = ExporterService()
        dn = DeliveryNote(filename="test.pdf", date="20230801", amount="50000", ocr_text="出库单")
        counter: dict[str, int] = {}
        name1 = svc._build_delivery_filename(dn, counter)
        name2 = svc._build_delivery_filename(dn, counter)
        assert name1 != name2  # second one should have _2

    def test_unmatched_remark(self) -> None:
        svc = ExporterService()
        dn = DeliveryNote(
            filename="test.pdf",
            date="20230801",
            amount="50000",
            ocr_text="出库单",
            match_status=STATUS_UNMATCHED,
            remark="这张单未出现在对账单中",
        )
        name = svc._build_delivery_filename(dn, {})
        assert "这张单未出现在对账单中" in name

    def test_出仓单_type(self) -> None:
        svc = ExporterService()
        dn = DeliveryNote(filename="test.pdf", date="20230801", amount="50000", ocr_text="出仓单内容")
        name = svc._build_delivery_filename(dn, {})
        assert "出仓单" in name


class TestExporterBuildFilename:
    def test_format(self) -> None:
        name = ExporterService._build_filename()
        assert name.startswith("evidence_sorting_")
        assert name.endswith(".zip")


class TestExporterWriteImage:
    def test_valid_base64(self) -> None:
        import base64

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            b64 = base64.b64encode(b"fake image").decode()
            ExporterService._write_image(zf, "test.jpg", b64)

        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            assert zf.read("test.jpg") == b"fake image"

    def test_with_prefix(self) -> None:
        import base64

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            b64 = base64.b64encode(b"test data").decode()
            ExporterService._write_image(zf, "test.jpg", f"data:image/png;base64,{b64}")

        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            assert zf.read("test.jpg") == b"test data"

    def test_invalid_base64_does_not_crash(self) -> None:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            ExporterService._write_image(zf, "bad.jpg", "not-valid-base64!")


class TestExporterExportZipIntegration:
    def test_empty_result_produces_valid_zip(self) -> None:
        result = ReconcileResult()
        svc = ExporterService()
        # Mock _ensure_output_dir and _build_filename to avoid disk writes
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        tmpdir = Path(tempfile.mkdtemp())
        with patch.object(ExporterService, "_ensure_output_dir", return_value=tmpdir), \
             patch.object(ExporterService, "_build_filename", return_value="test.zip"):
            output = svc.export_zip(result)
            assert output["success"] is True
            assert (tmpdir / "test.zip").exists()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class TestReconcileResultDataclass:
    def test_defaults(self) -> None:
        r = ReconcileResult()
        assert r.month_groups == []
        assert r.unsigned_statements == []
        assert r.receipts == []
        assert r.others == []
        assert r.unmatched_deliveries == []


class TestMonthGroupDataclass:
    def test_defaults(self) -> None:
        g = MonthGroup(month="2023-01", folder_name="test")
        assert g.statement is None
        assert g.deliveries == []
        assert g.issues == []


class TestStatementInfoDataclass:
    def test_defaults(self) -> None:
        si = StatementInfo()
        assert si.month == ""
        assert si.signed is False
        assert si.line_items == []
