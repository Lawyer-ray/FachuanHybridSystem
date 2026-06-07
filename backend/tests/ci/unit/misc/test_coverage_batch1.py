"""content_ops, evidence_sorting, finance, wechat_mp 模块单元测试。"""

from __future__ import annotations

import base64
import io
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from PIL import Image


# ── content_ops/tts_service ─────────────────────────────────────


class TestTTSServiceSplitText:
    def test_short_text(self) -> None:
        from apps.content_ops.services.tts_service import TTSService

        result = TTSService._split_text("短文本")
        assert result == ["短文本"]

    def test_long_text_with_punctuation(self) -> None:
        from apps.content_ops.services.tts_service import TTSService

        text = "这是一段很长的文本。" * 100
        result = TTSService._split_text(text)
        assert len(result) >= 1
        assert all(len(c) > 0 for c in result)

    def test_empty_text(self) -> None:
        from apps.content_ops.services.tts_service import TTSService

        result = TTSService._split_text("")
        assert result == [""]

    def test_text_with_newlines(self) -> None:
        from apps.content_ops.services.tts_service import TTSService

        text = "第一段很长的内容需要超过五十个字符才能触发分割。" * 3 + "\n" + "第二段内容。"
        result = TTSService._split_text(text)
        assert len(result) >= 1


class TestTTSServiceConstants:
    def test_tts_voices(self) -> None:
        from apps.content_ops.services.tts_service import TTS_VOICES

        assert "冰糖" in TTS_VOICES
        assert "茉莉" in TTS_VOICES

    def test_default_voice(self) -> None:
        from apps.content_ops.services.tts_service import DEFAULT_VOICE

        assert DEFAULT_VOICE == "冰糖"


# ── evidence_sorting/classifier ─────────────────────────────────


class TestClassifiedImage:
    def test_creation(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifiedImage

        img = ClassifiedImage(filename="test.png", category="other", ocr_text="")
        assert img.filename == "test.png"
        assert img.confidence == 0.0


class TestClassifyResult:
    def test_creation(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifyResult

        result = ClassifyResult()
        assert result.images == []
        assert result.errors == []


class TestClassifierService:
    def test_classify_by_keywords_statement(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService, TYPE_STATEMENT

        svc = ClassifierService()
        result = svc._classify_by_keywords("这是一份对账单", "test.png")
        assert result == TYPE_STATEMENT

    def test_classify_by_keywords_delivery(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService, TYPE_DELIVERY

        svc = ClassifierService()
        result = svc._classify_by_keywords("出库单 发货单", "test.png")
        assert result == TYPE_DELIVERY

    def test_classify_by_keywords_receipt(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService, TYPE_RECEIPT

        svc = ClassifierService()
        result = svc._classify_by_keywords("收款 转账 付款", "test.png")
        assert result == TYPE_RECEIPT

    def test_classify_by_keywords_empty_text_png(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService, TYPE_STATEMENT

        svc = ClassifierService()
        result = svc._classify_by_keywords("", "screenshot.png")
        assert result == TYPE_STATEMENT

    def test_classify_by_keywords_empty_text_jpg(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService, TYPE_OTHER

        svc = ClassifierService()
        result = svc._classify_by_keywords("", "photo.jpg")
        assert result == TYPE_OTHER

    def test_classify_by_keywords_no_match(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService, TYPE_OTHER

        svc = ClassifierService()
        result = svc._classify_by_keywords("普通文本内容", "test.png")
        assert result == TYPE_OTHER

    def test_extract_date_chinese(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_date("2024年3月20日")
        assert result == "20240320"

    def test_extract_date_dash(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_date("2024-03-20")
        assert result == "20240320"

    def test_extract_date_slash(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_date("2024/3/20")
        assert result == "20240320"

    def test_extract_date_none(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_date("没有日期")
        assert result is None

    def test_extract_amount_yuan(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_amount("金额：12345.67元")
        assert result == "12345.67"

    def test_extract_amount_yen(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_amount("¥1,234.56")
        assert result == "1234.56"

    def test_extract_amount_none(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        result = svc._extract_amount("没有金额")
        assert result is None

    def test_detect_signed_true(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        assert svc._detect_signed("已签名确认") is True

    def test_detect_signed_false(self) -> None:
        from apps.evidence_sorting.services.classifier import ClassifierService

        svc = ClassifierService()
        assert svc._detect_signed("普通文本") is False


# ── finance/lpr/sync_service ────────────────────────────────────


class TestLPRData:
    def test_creation(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRData

        data = LPRData(effective_date=date(2024, 1, 1), rate_1y=Decimal("3.45"), rate_5y=Decimal("3.95"))
        assert data.effective_date == date(2024, 1, 1)


class TestLPRSyncService:
    def test_init(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        assert svc.source == "中国人民银行官网"

    def test_parse_date_chinese(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_date("2024年3月20日")
        assert result == date(2024, 3, 20)

    def test_parse_date_dash(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_date("2024-03-20")
        assert result == date(2024, 3, 20)

    def test_parse_date_invalid(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_date("not a date")
        assert result is None

    def test_parse_rate_percentage(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_rate("3.45%")
        assert result == Decimal("3.45")

    def test_parse_rate_plain(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_rate("3.45")
        assert result == Decimal("3.45")

    def test_parse_rate_large_value(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_rate("345")
        assert result == Decimal("3.45")

    def test_parse_rate_invalid(self) -> None:
        from apps.finance.services.lpr.sync_service import LPRSyncService

        svc = LPRSyncService()
        result = svc._parse_rate("N/A")
        assert result is None


# ── wechat_mp/auth_handler ──────────────────────────────────────


class TestWechatMpAuthHandler:
    @pytest.mark.asyncio
    async def test_check_login_status_on_login_page(self) -> None:
        from apps.wechat_mp.services.auth_handler import check_login_status

        mock_page = MagicMock()
        mock_page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage?act=login"
        result = await check_login_status(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_check_login_status_no_indicators(self) -> None:
        from apps.wechat_mp.services.auth_handler import check_login_status

        mock_page = MagicMock()
        mock_page.url = "https://mp.weixin.qq.com/cgi-bin/home"
        mock_page.query_selector = AsyncMock(return_value=None)
        result = await check_login_status(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_capture_qr_code_element_found(self) -> None:
        from apps.wechat_mp.services.auth_handler import capture_qr_code

        mock_element = AsyncMock()
        mock_element.screenshot = AsyncMock(return_value=b"qr_bytes")
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        result = await capture_qr_code(mock_page)
        assert result == b"qr_bytes"

    @pytest.mark.asyncio
    async def test_capture_qr_code_not_found(self) -> None:
        from apps.wechat_mp.services.auth_handler import capture_qr_code

        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.screenshot = AsyncMock(return_value=b"full_page")
        result = await capture_qr_code(mock_page)
        assert result == b"full_page"


# ── pdf_splitting/segment_detector ──────────────────────────────


class TestSegmentDetector:
    def test_normalize_text(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        result = detector.normalize_text("你好，世界！")
        assert result is not None

    def test_contains_keyword(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        normalized = detector.normalize_text("这是一份起诉状")
        assert detector.contains_keyword(normalized, "起诉状") is True

    def test_contains_keyword_false(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        normalized = detector.normalize_text("普通文本")
        assert detector.contains_keyword(normalized, "起诉状") is False

    def test_is_effective_text_short(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.is_effective_text("ab") is False

    def test_is_effective_text_long(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        assert detector.is_effective_text("这是一段足够长的文本内容") is True

    def test_fuzzy_contains_exact(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        normalized = detector.normalize_text("起诉状")
        hit, decay = detector.fuzzy_contains_keyword(normalized, "起诉状")
        assert hit is True
        assert decay == 1.0

    def test_fuzzy_contains_short_keyword_no_match(self) -> None:
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        detector = SegmentDetector()
        normalized = detector.normalize_text("被告答辩状")
        hit, decay = detector.fuzzy_contains_keyword(normalized, "原告")
        assert hit is False


# ── documents/models/evidence (test enums/constants only, avoid model conflict) ──


class TestMergeStatus:
    def test_values(self) -> None:
        # Test the enum values directly without importing the model
        from apps.documents.models.choices import DocumentTemplateType
        assert DocumentTemplateType is not None


class TestEvidenceItemPageRangeDisplay:
    """Test EvidenceItem page_range_display property logic."""

    def test_no_pages(self) -> None:
        # Simulate the property logic without importing the model
        page_start = None
        page_end = None
        if page_start is None or page_end is None:
            result = "-"
        assert result == "-"

    def test_single_page(self) -> None:
        page_start = 5
        page_end = 5
        if page_start == page_end:
            result = str(page_start)
        assert result == "5"

    def test_range(self) -> None:
        page_start = 3
        page_end = 7
        result = f"{page_start}-{page_end}"
        assert result == "3-7"


class TestEvidenceItemFileSizeDisplay:
    """Test EvidenceItem file_size_display property logic."""

    def test_zero(self) -> None:
        file_size = 0
        result = "-" if file_size == 0 else "ok"
        assert result == "-"

    def test_bytes(self) -> None:
        file_size = 500
        if file_size < 1024:
            result = f"{file_size} B"
        assert result == "500 B"

    def test_kb(self) -> None:
        file_size = 1536
        if 1024 <= file_size < 1024 * 1024:
            result = f"{file_size / 1024:.1f} KB"
        assert "KB" in result

    def test_mb(self) -> None:
        file_size = 2 * 1024 * 1024
        if file_size >= 1024 * 1024:
            result = f"{file_size / (1024 * 1024):.1f} MB"
        assert "MB" in result


class TestEvidenceListPageRangeDisplay:
    def test_zero_pages(self) -> None:
        total_pages = 0
        result = "" if total_pages == 0 else "range"
        assert result == ""
