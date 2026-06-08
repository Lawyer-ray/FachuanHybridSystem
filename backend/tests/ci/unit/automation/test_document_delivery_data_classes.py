"""测试文书送达数据类

覆盖: apps/automation/services/document_delivery/data_classes.py
重点: from_api_response, to_dict, parse_fssj, from_dict
"""

from __future__ import annotations

from datetime import datetime

import pytest

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentDetail,
    DocumentListResponse,
    DocumentRecord,
)


# ============================================================
# DocumentRecord
# ============================================================


class TestDocumentRecord:
    """测试文书记录数据类"""

    def test_from_api_response_full(self) -> None:
        data = {
            "ah": "（2025）粤0604民初41257号",
            "sdbh": "SD001",
            "ajzybh": "AJ001",
            "fssj": "2025-12-10 16:25:37",
            "fymc": "佛山市禅城区人民法院",
            "ahdm": "AHDM001",
            "fybh": "FY001",
            "ssdrxm": "张三",
            "ssdrsjhm": "13812345678",  # allowlist secret
            "ssdrzjhm": "440100199001011234",  # allowlist secret
            "wsmc": "传票,起诉状副本",
            "sdzt": "已送达",
            "qdzt": "已签到",
            "qdbh": "QD001",
            "fqr": "法院系统",
            "cjsj": "2025-12-10",
            "zhxgsj": "2025-12-11",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初41257号"
        assert record.sdbh == "SD001"
        assert record.fymc == "佛山市禅城区人民法院"
        assert record.ssdrxm == "张三"

    def test_from_api_response_defaults(self) -> None:
        data = {
            "ah": "AH",
            "sdbh": "SD",
            "ajzybh": "AJ",
            "fssj": "2025-12-10",
            "fymc": "法院",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ahdm == ""
        assert record.fybh == ""
        assert record.ssdrxm == ""
        assert record.wsmc == ""

    def test_parse_fssj_valid(self) -> None:
        record = DocumentRecord(
            ah="", sdbh="", ajzybh="", fssj="2025-12-10 16:25:37", fymc=""
        )
        result = record.parse_fssj()
        assert result == datetime(2025, 12, 10, 16, 25, 37)

    def test_parse_fssj_empty(self) -> None:
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert record.parse_fssj() is None

    def test_parse_fssj_invalid_format(self) -> None:
        record = DocumentRecord(
            ah="", sdbh="", ajzybh="", fssj="not-a-date", fymc=""
        )
        assert record.parse_fssj() is None

    def test_parse_fssj_iso_format(self) -> None:
        record = DocumentRecord(
            ah="", sdbh="", ajzybh="", fssj="2025-12-10T16:25:37", fymc=""
        )
        result = record.parse_fssj()
        assert result == datetime(2025, 12, 10, 16, 25, 37)

    def test_to_dict(self) -> None:
        record = DocumentRecord(
            ah="AH", sdbh="SD", ajzybh="AJ", fssj="2025-12-10", fymc="法院"
        )
        d = record.to_dict()
        assert d["ah"] == "AH"
        assert d["sdbh"] == "SD"
        assert d["ajzybh"] == "AJ"
        assert d["fssj"] == "2025-12-10"
        assert d["fymc"] == "法院"
        # Verify all expected keys present
        for key in (
            "ahdm", "fybh", "ssdrxm", "ssdrsjhm", "ssdrzjhm",
            "wsmc", "sdzt", "qdzt", "qdbh", "fqr", "cjsj", "zhxgsj",
        ):
            assert key in d


# ============================================================
# DocumentDetail
# ============================================================


class TestDocumentDetail:
    """测试文书详情数据类"""

    def test_from_api_response(self) -> None:
        data = {
            "c_sdbh": "SD001",
            "c_wsmc": "传票",
            "c_wjgs": "pdf",
            "wjlj": "https://example.com/doc.pdf",
            "c_stbh": "ST001",
            "c_wsbh": "WS001",
            "c_fybh": "FY001",
            "c_fymc": "法院",
            "dt_cjsj": "2025-12-10",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "SD001"
        assert detail.c_wsmc == "传票"
        assert detail.wjlj == "https://example.com/doc.pdf"

    def test_from_api_response_defaults(self) -> None:
        data = {
            "c_sdbh": "SD",
            "c_wsmc": "传票",
            "c_wjgs": "pdf",
            "wjlj": "https://example.com",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_stbh == ""
        assert detail.c_wsbh == ""

    def test_to_dict(self) -> None:
        detail = DocumentDetail(
            c_sdbh="SD", c_wsmc="传票", c_wjgs="pdf", wjlj="https://example.com"
        )
        d = detail.to_dict()
        assert d["c_sdbh"] == "SD"
        assert d["wjlj"] == "https://example.com"


# ============================================================
# DocumentListResponse
# ============================================================


class TestDocumentListResponse:
    """测试文书列表响应"""

    def test_from_api_response(self) -> None:
        data = {
            "code": 200,
            "msg": "成功！",
            "success": True,
            "data": {
                "total": 2,
                "data": [
                    {
                        "ah": "AH1", "sdbh": "SD1", "ajzybh": "AJ1",
                        "fssj": "2025-12-10", "fymc": "法院1",
                    },
                    {
                        "ah": "AH2", "sdbh": "SD2", "ajzybh": "AJ2",
                        "fssj": "2025-12-11", "fymc": "法院2",
                    },
                ],
            },
        }
        response = DocumentListResponse.from_api_response(data)
        assert response.total == 2
        assert len(response.documents) == 2
        assert response.documents[0].ah == "AH1"

    def test_from_api_response_empty(self) -> None:
        data = {"data": {"total": 0, "data": []}}
        response = DocumentListResponse.from_api_response(data)
        assert response.total == 0
        assert response.documents == []

    def test_from_api_response_missing_inner_data(self) -> None:
        data = {}
        response = DocumentListResponse.from_api_response(data)
        assert response.total == 0
        assert response.documents == []

    def test_to_dict(self) -> None:
        response = DocumentListResponse(
            total=1,
            documents=[
                DocumentRecord(
                    ah="AH", sdbh="SD", ajzybh="AJ",
                    fssj="2025-12-10", fymc="法院",
                )
            ],
        )
        d = response.to_dict()
        assert d["total"] == 1
        assert len(d["documents"]) == 1
        assert d["documents"][0]["ah"] == "AH"


# ============================================================
# DocumentDeliveryRecord
# ============================================================


class TestDocumentDeliveryRecord:
    """测试文书送达记录"""

    def test_to_dict_with_time(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="AH",
            send_time=datetime(2025, 12, 10, 16, 25),
            element_index=0,
            document_name="传票",
            court_name="法院",
        )
        d = record.to_dict()
        assert d["case_number"] == "AH"
        assert d["send_time"] == "2025-12-10T16:25:00"
        assert d["document_name"] == "传票"

    def test_to_dict_no_time(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="AH", send_time=None, element_index=0
        )
        d = record.to_dict()
        assert d["send_time"] is None

    def test_from_dict(self) -> None:
        data = {
            "case_number": "AH",
            "send_time": "2025-12-10T16:25:00",
            "element_index": 1,
            "document_name": "传票",
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.case_number == "AH"
        assert record.send_time == datetime(2025, 12, 10, 16, 25)
        assert record.element_index == 1
        assert record.document_name == "传票"

    def test_from_dict_no_send_time(self) -> None:
        data = {"case_number": "AH", "send_time": None, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time is None

    def test_from_dict_defaults(self) -> None:
        data = {"case_number": "AH", "send_time": None, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.document_name == ""
        assert record.court_name == ""
        assert record.delivery_event_id == ""

    def test_from_dict_datetime_object(self) -> None:
        """当 send_time 已经是 datetime 对象时"""
        dt = datetime(2025, 12, 10, 16, 25)
        data = {"case_number": "AH", "send_time": dt, "element_index": 0}
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time == dt
