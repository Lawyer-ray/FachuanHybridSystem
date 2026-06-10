"""Extended tests for evidence_sorting services - classifier, reconciler, exporter."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from apps.evidence_sorting.services.classifier import (
    ClassifierService,
    ClassifiedImage,
    ClassifyResult,
    TYPE_STATEMENT,
    TYPE_DELIVERY,
    TYPE_RECEIPT,
    TYPE_OTHER,
    _KEYWORDS,
)
from apps.evidence_sorting.services.reconciler import (
    LineItem,
    StatementInfo,
    DeliveryNote,
    MonthGroup,
    ReconcileResult,
    ReconcilerService,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    STATUS_MISSING,
    FOLDER_CONFIRMED,
)


class TestClassifierService:
    def setup_method(self):
        self.service = ClassifierService()

    def test_classify_by_keywords_statement(self):
        result = self.service._classify_by_keywords("对账单 月度汇总", "test.png")
        assert result == TYPE_STATEMENT

    def test_classify_by_keywords_delivery(self):
        result = self.service._classify_by_keywords("出库单 发货单", "test.jpg")
        assert result == TYPE_DELIVERY

    def test_classify_by_keywords_receipt(self):
        result = self.service._classify_by_keywords("收款 银行回单 转账", "test.jpg")
        assert result == TYPE_RECEIPT

    def test_classify_by_keywords_other(self):
        result = self.service._classify_by_keywords("普通文本内容", "test.jpg")
        assert result == TYPE_OTHER

    def test_classify_by_keywords_empty_png(self):
        result = self.service._classify_by_keywords("", "screenshot.png")
        assert result == TYPE_STATEMENT

    def test_classify_by_keywords_empty_jpg(self):
        result = self.service._classify_by_keywords("", "photo.jpg")
        assert result == TYPE_OTHER

    def test_extract_date_cn(self):
        result = self.service._extract_date("2024年01月15日")
        assert result == "20240115"

    def test_extract_date_iso(self):
        result = self.service._extract_date("2024-01-15")
        assert result == "20240115"

    def test_extract_date_slash(self):
        result = self.service._extract_date("2024/01/15")
        assert result == "20240115"

    def test_extract_date_none(self):
        result = self.service._extract_date("无日期")
        assert result is None

    def test_extract_amount_yuan(self):
        result = self.service._extract_amount("¥1,234.56")
        assert result == "1234.56"

    def test_extract_amount_chinese_yuan(self):
        result = self.service._extract_amount("￥65500.00")
        assert result is not None
        assert "65500" in result

    def test_extract_amount_with_unit(self):
        result = self.service._extract_amount("金额：12345元")
        assert result == "12345"

    def test_extract_amount_total(self):
        result = self.service._extract_amount("合计：99999.99")
        assert result == "99999.99"

    def test_extract_amount_none(self):
        result = self.service._extract_amount("无金额")
        assert result is None

    def test_extract_amount_integer(self):
        result = self.service._extract_amount("¥1000")
        assert result == "1000"

    def test_detect_signed_true(self):
        assert self.service._detect_signed("对账单已签名确认") is True

    def test_detect_signed_false(self):
        assert self.service._detect_signed("普通对账单内容") is False

    def test_detect_signed盖章(self):
        assert self.service._detect_signed("盖章确认") is True


class TestClassifiedImage:
    def test_defaults(self):
        img = ClassifiedImage(filename="test.jpg", category="other", ocr_text="")
        assert img.date is None
        assert img.amount is None
        assert img.signed is None
        assert img.confidence == 0.0
        assert img.rotation == 0


class TestClassifyResult:
    def test_defaults(self):
        result = ClassifyResult()
        assert result.images == []
        assert result.errors == []


class TestReconcilerService:
    def setup_method(self):
        self.service = ReconcilerService()

    def test_parse_llm_response_valid_json(self):
        text = '{"month": "2024-01", "total_amount": 1000, "signed": true, "line_items": [{"date": "20240115", "amount": 500, "description": "test"}]}'
        info = self.service._parse_llm_response(text)
        assert info.month == "2024-01"
        assert info.total_amount == 1000.0
        assert info.signed is True
        assert len(info.line_items) == 1
        assert info.line_items[0].date == "20240115"

    def test_parse_llm_response_markdown_json(self):
        text = '```json\n{"month": "2024-01", "total_amount": 1000, "signed": false, "line_items": []}\n```'
        info = self.service._parse_llm_response(text)
        assert info.month == "2024-01"

    def test_parse_llm_response_invalid_json(self):
        info = self.service._parse_llm_response("not json")
        assert info.month == ""

    def test_normalize_date_valid(self):
        assert self.service._normalize_date("20240115") == "20240115"

    def test_normalize_date_with_separators(self):
        assert self.service._normalize_date("2024-01-15") == "20240115"

    def test_normalize_date_none(self):
        assert self.service._normalize_date(None) is None

    def test_normalize_date_invalid_length(self):
        assert self.service._normalize_date("202401") is None

    def test_to_float_valid(self):
        assert self.service._to_float("1234.56") == 1234.56

    def test_to_float_with_commas(self):
        assert self.service._to_float("1,234.56") == 1234.56

    def test_to_float_none(self):
        assert self.service._to_float(None) is None

    def test_to_float_invalid(self):
        assert self.service._to_float("abc") is None

    def test_extract_month_key_standard(self):
        info = StatementInfo(month="2024-01")
        assert self.service._extract_month_key(info) == "2024年01月"

    def test_extract_month_key_range(self):
        info = StatementInfo(month="2024-01~2024-02")
        assert self.service._extract_month_key(info) == "2024年01-02月"

    def test_extract_month_key_empty(self):
        info = StatementInfo(month="")
        assert self.service._extract_month_key(info) == ""

    def test_month_key_to_yyyymm(self):
        assert self.service._month_key_to_yyyymm("2024年01月") == "202401"

    def test_month_key_to_yyyymm_invalid(self):
        assert self.service._month_key_to_yyyymm("invalid") is None

    def test_match_delivery_matching(self):
        li = LineItem(date="20240115", amount=1000.0)
        dn = DeliveryNote(date="20240115", amount="1000")
        assert self.service._match_delivery(li, dn) is True

    def test_match_delivery_date_mismatch(self):
        li = LineItem(date="20240115", amount=1000.0)
        dn = DeliveryNote(date="20240116", amount="1000")
        assert self.service._match_delivery(li, dn) is False

    def test_match_delivery_both_no_date(self):
        li = LineItem(date=None, amount=1000.0)
        dn = DeliveryNote(date=None, amount="1000")
        assert self.service._match_delivery(li, dn) is False

    def test_match_delivery_amount_tolerance(self):
        li = LineItem(date="20240115", amount=1000.0)
        dn = DeliveryNote(date="20240115", amount="1005")
        assert self.service._match_delivery(li, dn) is True

    def test_build_folder_name_confirmed(self):
        statement = StatementInfo(signed=True)
        group = MonthGroup(month="2024年01月", folder_name="", statement=statement)
        name = self.service._build_folder_name("2024年01月", statement, group, [])
        assert "已确认" in name

    def test_build_folder_name_unsigned(self):
        statement = StatementInfo(signed=False)
        group = MonthGroup(month="2024年01月", folder_name="", statement=statement)
        name = self.service._build_folder_name("2024年01月", statement, group, ["对账单未签名"])
        assert "对账单未签名" in name


class TestReconcileResult:
    def test_defaults(self):
        result = ReconcileResult()
        assert result.month_groups == []
        assert result.unsigned_statements == []
        assert result.receipts == []
        assert result.others == []
        assert result.unmatched_deliveries == []


class TestExporterService:
    def test_import(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        assert ExporterService is not None

    def test_get_ext(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        assert ExporterService._get_ext("test.jpg") == ".jpg"
        assert ExporterService._get_ext("test.pdf") == ".pdf"
        assert ExporterService._get_ext("noext") == ".jpg"

    def test_build_filename(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        filename = ExporterService._build_filename()
        assert filename.startswith("evidence_sorting_")
        assert filename.endswith(".zip")

    def test_write_image(self):
        import io
        import zipfile

        from apps.evidence_sorting.services.exporter import ExporterService

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            ExporterService._write_image(zf, "test.jpg", base64.b64encode(b"fake image").decode())
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            assert "test.jpg" in zf.namelist()

    def test_write_image_with_prefix(self):
        import io
        import zipfile

        from apps.evidence_sorting.services.exporter import ExporterService

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            data = "data:image/jpeg;base64," + base64.b64encode(b"fake image").decode()
            ExporterService._write_image(zf, "test.jpg", data)
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            assert "test.jpg" in zf.namelist()
