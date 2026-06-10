"""文书送达数据类测试 - 真实执行代码。"""

from __future__ import annotations

from datetime import datetime

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDetail,
    DocumentDeliveryRecord,
    DocumentListResponse,
    DocumentProcessResult,
    DocumentQueryResult,
    DocumentRecord,
)


class TestDocumentRecord:
    """测试 DocumentRecord 数据类。"""

    def test_from_api_response_full(self) -> None:
        """从完整 API 响应创建。"""
        data = {
            "ah": "（2025）粤0604民初41257号",
            "sdbh": "SD001",
            "ajzybh": "AJ001",
            "fssj": "2025-12-10 16:25:37",
            "fymc": "佛山市禅城区人民法院",
            "ahdm": "Y0604",
            "fybh": "FY001",
            "ssdrxm": "张三",
            "ssdrsjhm": "13800138000",
            "ssdrzjhm": "440000000000000000",
            "wsmc": "判决书,裁定书",
            "sdzt": "1",
            "qdzt": "1",
            "qdbh": "QD001",
            "fqr": "系统",
            "cjsj": "2025-12-10 16:00:00",
            "zhxgsj": "2025-12-10 17:00:00",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初41257号"
        assert record.sdbh == "SD001"
        assert record.fssj == "2025-12-10 16:25:37"
        assert record.fymc == "佛山市禅城区人民法院"

    def test_from_api_response_minimal(self) -> None:
        """从最小 API 响应创建（只有必填字段）。"""
        data = {
            "ah": "（2025）粤0604民初1号",
            "sdbh": "SD002",
            "ajzybh": "AJ002",
            "fssj": "2025-01-01 00:00:00",
            "fymc": "测试法院",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初1号"
        assert record.ahdm == ""
        assert record.wsmc == ""

    def test_from_api_response_empty(self) -> None:
        """从空字典创建。"""
        record = DocumentRecord.from_api_response({})
        assert record.ah == ""
        assert record.sdbh == ""

    def test_parse_fssj_valid(self) -> None:
        """解析有效时间字符串。"""
        record = DocumentRecord(
            ah="test", sdbh="test", ajzybh="test", fssj="2025-12-10 16:25:37", fymc="test"
        )
        dt = record.parse_fssj()
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 10
        assert dt.hour == 16
        assert dt.minute == 25
        assert dt.second == 37

    def test_parse_fssj_empty(self) -> None:
        """空时间字符串返回 None。"""
        record = DocumentRecord(ah="test", sdbh="test", ajzybh="test", fssj="", fymc="test")
        assert record.parse_fssj() is None

    def test_parse_fssj_invalid(self) -> None:
        """无效时间字符串返回 None。"""
        record = DocumentRecord(ah="test", sdbh="test", ajzybh="test", fssj="not-a-date", fymc="test")
        assert record.parse_fssj() is None

    def test_to_dict(self) -> None:
        """序列化为字典。"""
        record = DocumentRecord(
            ah="（2025）粤0604民初1号",
            sdbh="SD001",
            ajzybh="AJ001",
            fssj="2025-01-01 00:00:00",
            fymc="测试法院",
        )
        d = record.to_dict()
        assert d["ah"] == "（2025）粤0604民初1号"
        assert d["sdbh"] == "SD001"
        assert "fymc" in d


class TestDocumentDetail:
    """测试 DocumentDetail 数据类。"""

    def test_from_api_response(self) -> None:
        data = {
            "c_sdbh": "SD001",
            "c_wsmc": "判决书",
            "c_wjgs": "pdf",
            "wjlj": "https://oss.court.gov.cn/file.pdf",
            "c_stbh": "ST001",
            "c_wsbh": "WS001",
            "c_fybh": "FY001",
            "c_fymc": "测试法院",
            "dt_cjsj": "2025-01-01T00:00:00",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "SD001"
        assert detail.c_wsmc == "判决书"
        assert detail.wjlj == "https://oss.court.gov.cn/file.pdf"

    def test_from_api_response_empty(self) -> None:
        detail = DocumentDetail.from_api_response({})
        assert detail.c_sdbh == ""
        assert detail.wjlj == ""

    def test_to_dict(self) -> None:
        detail = DocumentDetail(
            c_sdbh="SD001", c_wsmc="判决书", c_wjgs="pdf", wjlj="https://example.com/file.pdf"
        )
        d = detail.to_dict()
        assert d["c_sdbh"] == "SD001"
        assert d["wjlj"] == "https://example.com/file.pdf"


class TestDocumentListResponse:
    """测试 DocumentListResponse 数据类。"""

    def test_from_api_response(self) -> None:
        data = {
            "data": {
                "total": 2,
                "data": [
                    {"ah": "（2025）粤0604民初1号", "sdbh": "SD1", "ajzybh": "AJ1", "fssj": "2025-01-01 00:00:00", "fymc": "法院A"},
                    {"ah": "（2025）粤0604民初2号", "sdbh": "SD2", "ajzybh": "AJ2", "fssj": "2025-01-02 00:00:00", "fymc": "法院B"},
                ],
            }
        }
        resp = DocumentListResponse.from_api_response(data)
        assert resp.total == 2
        assert len(resp.documents) == 2
        assert resp.documents[0].ah == "（2025）粤0604民初1号"

    def test_from_api_response_empty(self) -> None:
        resp = DocumentListResponse.from_api_response({"data": {"total": 0, "data": []}})
        assert resp.total == 0
        assert resp.documents == []

    def test_from_api_response_no_data_key(self) -> None:
        resp = DocumentListResponse.from_api_response({})
        assert resp.total == 0
        assert resp.documents == []

    def test_to_dict(self) -> None:
        resp = DocumentListResponse(
            total=1,
            documents=[
                DocumentRecord(ah="test", sdbh="SD1", ajzybh="AJ1", fssj="2025-01-01 00:00:00", fymc="法院")
            ],
        )
        d = resp.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1


class TestDocumentDeliveryRecord:
    """测试 DocumentDeliveryRecord 数据类。"""

    def test_to_dict_with_send_time(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="（2025）粤0604民初1号",
            send_time=datetime(2025, 1, 1, 12, 0, 0),
            element_index=0,
            document_name="判决书",
            court_name="测试法院",
        )
        d = record.to_dict()
        assert d["case_number"] == "（2025）粤0604民初1号"
        assert d["send_time"] == "2025-01-01T12:00:00"
        assert d["element_index"] == 0

    def test_to_dict_without_send_time(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="test", send_time=None, element_index=1
        )
        d = record.to_dict()
        assert d["send_time"] is None

    def test_from_dict_with_string_time(self) -> None:
        data = {
            "case_number": "test",
            "send_time": "2025-01-01T12:00:00",
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time == datetime(2025, 1, 1, 12, 0, 0)

    def test_from_dict_with_none_time(self) -> None:
        data = {
            "case_number": "test",
            "send_time": None,
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time is None

    def test_from_dict_with_datetime_time(self) -> None:
        dt = datetime(2025, 6, 1, 10, 0, 0)
        data = {
            "case_number": "test",
            "send_time": dt,
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time == dt

    def test_from_dict_defaults(self) -> None:
        data = {"case_number": "test", "send_time": None, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.document_name == ""
        assert record.court_name == ""
        assert record.delivery_event_id == ""


class TestDocumentQueryResult:
    """测试 DocumentQueryResult 数据类。"""

    def test_creation(self) -> None:
        result = DocumentQueryResult(
            total_found=10,
            processed_count=8,
            skipped_count=1,
            failed_count=1,
            case_log_ids=[1, 2, 3],
            errors=["error1"],
        )
        assert result.total_found == 10
        assert result.processed_count == 8
        assert len(result.case_log_ids) == 3


class TestDocumentProcessResult:
    """测试 DocumentProcessResult 数据类。"""

    def test_success_result(self) -> None:
        result = DocumentProcessResult(
            success=True,
            case_id=1,
            case_log_id=1,
            renamed_path="/tmp/renamed.pdf",
            notification_sent=True,
            error_message=None,
        )
        assert result.success is True
        assert result.error_message is None

    def test_failure_result(self) -> None:
        result = DocumentProcessResult(
            success=False,
            case_id=None,
            case_log_id=None,
            renamed_path=None,
            notification_sent=False,
            error_message="匹配失败",
        )
        assert result.success is False
        assert result.error_message == "匹配失败"
