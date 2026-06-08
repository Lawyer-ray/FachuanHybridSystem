"""快递查询运单号提取服务测试。"""

from __future__ import annotations

from apps.express_query.services.tracking_extraction_service import (
    TrackingExtractionService,
    TrackingExtractionResult,
)


class TestTrackingExtractionService:
    """TrackingExtractionService 纯函数测试。"""

    def setup_method(self) -> None:
        self.service = TrackingExtractionService.__new__(TrackingExtractionService)

    def test_pick_tracking_number_sf(self) -> None:
        """识别顺丰单号。"""
        result = self.service._pick_tracking_number("运单号 SF1234567890123 已发出")
        assert result is not None
        assert result["carrier"] == "sf"
        assert result["tracking_number"] == "SF1234567890123"

    def test_pick_tracking_number_ems(self) -> None:
        """识别 EMS 单号。"""
        result = self.service._pick_tracking_number("运单号 1234567890123 已发出")
        assert result is not None
        assert result["carrier"] == "ems"
        assert result["tracking_number"] == "1234567890123"

    def test_pick_tracking_number_sf_priority(self) -> None:
        """顺丰单号优先于 EMS。"""
        result = self.service._pick_tracking_number("SF1234567890123 1234567890124")
        assert result is not None
        assert result["carrier"] == "sf"

    def test_pick_tracking_number_no_match(self) -> None:
        """无运单号。"""
        result = self.service._pick_tracking_number("这是一段普通文本")
        assert result is None

    def test_pick_tracking_number_empty(self) -> None:
        """空文本。"""
        result = self.service._pick_tracking_number("")
        assert result is None

    def test_pick_tracking_number_sf_with_pipe(self) -> None:
        """包含竖线的文本（OCR 常见）。"""
        result = self.service._pick_tracking_number("运单号|SF1234567890123|已发出")
        assert result is not None
        assert result["carrier"] == "sf"

    def test_pick_tracking_number_ems_no_overlap_with_sf(self) -> None:
        """EMS 不与顺丰单号重叠。"""
        result = self.service._pick_tracking_number("SF1234567890123")
        assert result is not None
        assert result["carrier"] == "sf"
        # EMS 的正则不应匹配到顺丰单号中的数字部分

    def test_pick_tracking_number_multiple_sf(self) -> None:
        """多个顺丰单号，选择第一个。"""
        result = self.service._pick_tracking_number("SF1234567890123 和 SF9876543210987")
        assert result is not None
        assert result["tracking_number"] == "SF1234567890123"

    def test_pick_tracking_number_lowercase_sf(self) -> None:
        """小写顺丰单号。"""
        result = self.service._pick_tracking_number("运单号 sf1234567890123 已发出")
        assert result is not None
        assert result["carrier"] == "sf"
        assert result["tracking_number"] == "SF1234567890123"


class TestTrackingExtractionResult:
    """TrackingExtractionResult 数据类测试。"""

    def test_creation(self) -> None:
        result = TrackingExtractionResult(
            carrier_type="sf",
            tracking_number="SF1234567890123",
            ocr_text="原始文本",
        )
        assert result.carrier_type == "sf"
        assert result.tracking_number == "SF1234567890123"
        assert result.ocr_text == "原始文本"
