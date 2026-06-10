"""Batch 6 coverage tests for evidence_sorting module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestClassifierService:
    def _make_service(self):
        from apps.evidence_sorting.services.classifier import ClassifierService

        return ClassifierService()

    def test_classify_by_keywords_statement(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("这是一份对账单", "") == "statement"

    def test_classify_by_keywords_delivery(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("出库单 送货单", "") == "delivery"

    def test_classify_by_keywords_receipt(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("银行回单 转账成功", "") == "receipt"

    def test_classify_by_keywords_empty_text_png(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("", "screenshot.png") == "statement"

    def test_classify_by_keywords_empty_text_jpg(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("", "photo.jpg") == "other"

    def test_classify_by_keywords_no_match(self):
        svc = self._make_service()
        assert svc._classify_by_keywords("一些无关的文本", "") == "other"

    def test_extract_date_cn_format(self):
        svc = self._make_service()
        assert svc._extract_date("2023年08月15日") == "20230815"

    def test_extract_date_iso_format(self):
        svc = self._make_service()
        assert svc._extract_date("2023-08-15") == "20230815"

    def test_extract_date_slash_format(self):
        svc = self._make_service()
        assert svc._extract_date("2023/08/15") == "20230815"

    def test_extract_date_none(self):
        svc = self._make_service()
        assert svc._extract_date("没有日期") is None

    def test_extract_amount_yuan(self):
        svc = self._make_service()
        assert svc._extract_amount("金额：12345.67") == "12345.67"

    def test_extract_amount_rmb(self):
        svc = self._make_service()
        assert svc._extract_amount("¥1,234.56") == "1234.56"

    def test_extract_amount_yuan_unit(self):
        svc = self._make_service()
        result = svc._extract_amount("500元")
        assert result is not None

    def test_extract_amount_none(self):
        svc = self._make_service()
        assert svc._extract_amount("没有金额") is None

    def test_extract_amount_integer(self):
        svc = self._make_service()
        result = svc._extract_amount("¥1000.00")
        assert result == "1000"

    def test_detect_signed_true(self):
        svc = self._make_service()
        assert svc._detect_signed("已签名确认无误") is True

    def test_detect_signed_false(self):
        svc = self._make_service()
        assert svc._detect_signed("普通对账单内容") is False


class TestClassifierDataClasses:
    def test_classified_image(self):
        from apps.evidence_sorting.services.classifier import ClassifiedImage

        img = ClassifiedImage(filename="test.jpg", category="other", ocr_text="text")
        assert img.filename == "test.jpg"
        assert img.date is None
        assert img.amount is None
        assert img.confidence == 0.0

    def test_classify_result(self):
        from apps.evidence_sorting.services.classifier import ClassifyResult

        result = ClassifyResult()
        assert result.images == []
        assert result.errors == []


class TestReconcilerService:
    def _make_service(self):
        from apps.evidence_sorting.services.reconciler import ReconcilerService

        return ReconcilerService()

    def test_parse_llm_response_json(self):
        svc = self._make_service()
        json_text = '{"month": "2023-08", "total_amount": 10000, "signed": true, "line_items": [{"date": "20230815", "amount": 5000, "description": "test"}]}'
        result = svc._parse_llm_response(json_text)
        assert result.month == "2023-08"
        assert result.signed is True
        assert len(result.line_items) == 1

    def test_parse_llm_response_code_block(self):
        svc = self._make_service()
        json_text = '```json\n{"month": "2023-09", "total_amount": 5000, "signed": false, "line_items": []}\n```'
        result = svc._parse_llm_response(json_text)
        assert result.month == "2023-09"

    def test_parse_llm_response_invalid_json(self):
        svc = self._make_service()
        result = svc._parse_llm_response("not json")
        assert result.month == ""

    def test_normalize_date(self):
        svc = self._make_service()
        assert svc._normalize_date("2023-08-15") == "20230815"
        assert svc._normalize_date("20230815") == "20230815"
        assert svc._normalize_date(None) is None
        assert svc._normalize_date("") is None
        assert svc._normalize_date("invalid") is None

    def test_to_float(self):
        svc = self._make_service()
        assert svc._to_float(1234.56) == 1234.56
        assert svc._to_float("1,234.56") == 1234.56
        assert svc._to_float(None) is None
        assert svc._to_float("abc") is None

    def test_extract_month_key(self):
        from apps.evidence_sorting.services.reconciler import StatementInfo

        svc = self._make_service()
        st = StatementInfo(month="2023-08")
        assert svc._extract_month_key(st) == "2023年08月"

    def test_extract_month_key_range(self):
        from apps.evidence_sorting.services.reconciler import StatementInfo

        svc = self._make_service()
        st = StatementInfo(month="2023-01~2023-02")
        assert svc._extract_month_key(st) == "2023年01-02月"

    def test_extract_month_key_empty(self):
        from apps.evidence_sorting.services.reconciler import StatementInfo

        svc = self._make_service()
        st = StatementInfo(month="")
        assert svc._extract_month_key(st) == ""

    def test_month_key_to_yyyymm(self):
        svc = self._make_service()
        assert svc._month_key_to_yyyymm("2023年08月") == "202308"
        assert svc._month_key_to_yyyymm("invalid") is None

    def test_match_delivery_date_and_amount(self):
        from apps.evidence_sorting.services.reconciler import (
            DeliveryNote,
            LineItem,
        )

        svc = self._make_service()
        li = LineItem(date="20230815", amount=5000.0)
        dn = DeliveryNote(date="20230815", amount="5000")
        assert svc._match_delivery(li, dn) is True

    def test_match_delivery_mismatched_date(self):
        from apps.evidence_sorting.services.reconciler import (
            DeliveryNote,
            LineItem,
        )

        svc = self._make_service()
        li = LineItem(date="20230815", amount=5000.0)
        dn = DeliveryNote(date="20230816", amount="5000")
        assert svc._match_delivery(li, dn) is False

    def test_match_delivery_no_dates(self):
        from apps.evidence_sorting.services.reconciler import (
            DeliveryNote,
            LineItem,
        )

        svc = self._make_service()
        li = LineItem(amount=5000.0)
        dn = DeliveryNote(amount="5000")
        assert svc._match_delivery(li, dn) is False

    def test_build_folder_name_confirmed(self):
        from apps.evidence_sorting.services.reconciler import (
            MonthGroup,
            StatementInfo,
        )

        svc = self._make_service()
        st = StatementInfo(signed=True)
        group = MonthGroup(month="2023年08月", folder_name="", statement=st, deliveries=[])
        result = svc._build_folder_name("2023年08月", st, group, [])
        assert "已确认" in result

    def test_build_folder_name_unsigned(self):
        from apps.evidence_sorting.services.reconciler import (
            FOLDER_UNSIGNED,
            MonthGroup,
            StatementInfo,
        )

        svc = self._make_service()
        st = StatementInfo(signed=False)
        group = MonthGroup(month="2023年08月", folder_name="", statement=st, deliveries=[])
        result = svc._build_folder_name("2023年08月", st, group, [FOLDER_UNSIGNED])
        assert "未签名" in result


class TestReconcilerDataClasses:
    def test_line_item(self):
        from apps.evidence_sorting.services.reconciler import LineItem

        li = LineItem()
        assert li.date is None
        assert li.amount is None
        assert li.description == ""

    def test_statement_info(self):
        from apps.evidence_sorting.services.reconciler import StatementInfo

        si = StatementInfo()
        assert si.month == ""
        assert si.signed is False
        assert si.line_items == []

    def test_delivery_note(self):
        from apps.evidence_sorting.services.reconciler import DeliveryNote

        dn = DeliveryNote()
        assert dn.match_status == "unmatched"

    def test_reconcile_result(self):
        from apps.evidence_sorting.services.reconciler import ReconcileResult

        result = ReconcileResult()
        assert result.month_groups == []
        assert result.unsigned_statements == []
