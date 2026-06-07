"""SMS 去重服务、任务恢复服务、文书重命名服务测试。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.court_sms_dedup_service import CourtSMSDedupService
from apps.automation.services.sms.task_recovery_service import TaskRecoveryService
from apps.automation.services.sms.document_renamer import DocumentRenamer
from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord, DocumentRecord, DocumentDetail, DocumentListResponse


class TestCourtSMSDedupService:
    """CourtSMSDedupService 测试。"""

    def setup_method(self) -> None:
        self.service = CourtSMSDedupService()

    def test_build_identity_with_event_id(self) -> None:
        """有 event_id 时使用 event_id 构建身份。"""
        record = DocumentDeliveryRecord(
            case_number="（2025）粤0604民初12345号",
            send_time=datetime(2025, 1, 1, 12, 0, 0),
            element_index=0,
            delivery_event_id="sdbh_123",
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_id == "sdbh_123"
        assert identity.event_key is not None
        assert identity.uses_fallback is False

    def test_build_identity_without_event_id(self) -> None:
        """无 event_id 时使用 fallback 构建身份。"""
        record = DocumentDeliveryRecord(
            case_number="（2025）粤0604民初12345号",
            send_time=datetime(2025, 1, 1, 12, 0, 0),
            element_index=0,
            court_name="佛山市禅城区人民法院",
            document_name="判决书",
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_id is None
        assert identity.event_key is not None
        assert identity.uses_fallback is True

    def test_build_identity_no_case_number(self) -> None:
        """无案号无 event_id 返回空身份。"""
        record = DocumentDeliveryRecord(
            case_number="",
            send_time=None,
            element_index=0,
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_key is None

    def test_normalize_text(self) -> None:
        """规范化文本。"""
        assert self.service._normalize_text("  hello  world  ") == "hello world"
        assert self.service._normalize_text(None) == ""
        assert self.service._normalize_text("") == ""

    def test_hash_payload(self) -> None:
        """哈希载荷。"""
        hash1 = self.service._hash_payload("test")
        hash2 = self.service._hash_payload("test")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex

    def test_build_existing_sms_result(self) -> None:
        """构建重复命中返回结构。"""
        sms = SimpleNamespace(
            case_id=1,
            case_log_id=2,
            notification_results={"feishu": {"success": True}},
            feishu_sent_at=None,
        )
        result = self.service.build_existing_sms_result(sms, "/path/file.pdf")
        assert result["success"] is True
        assert result["deduplicated"] is True
        assert result["case_id"] == 1
        assert result["renamed_path"] == "/path/file.pdf"


class TestDocumentRecord:
    """DocumentRecord 数据类测试。"""

    def test_from_api_response(self) -> None:
        data = {
            "ah": "（2025）粤0604民初12345号",
            "sdbh": "123",
            "ajzybh": "456",
            "fssj": "2025-01-01 12:00:00",
            "fymc": "佛山市禅城区人民法院",
        }
        record = DocumentRecord.from_api_response(data)
        assert record.ah == "（2025）粤0604民初12345号"
        assert record.sdbh == "123"

    def test_parse_fssj(self) -> None:
        record = DocumentRecord(
            ah="", sdbh="", ajzybh="", fssj="2025-01-01 12:00:00", fymc=""
        )
        dt = record.parse_fssj()
        assert dt is not None
        assert dt.year == 2025

    def test_parse_fssj_empty(self) -> None:
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="", fymc="")
        assert record.parse_fssj() is None

    def test_parse_fssj_invalid(self) -> None:
        record = DocumentRecord(ah="", sdbh="", ajzybh="", fssj="invalid", fymc="")
        assert record.parse_fssj() is None

    def test_to_dict(self) -> None:
        record = DocumentRecord(ah="test", sdbh="1", ajzybh="2", fssj="2025-01-01 12:00:00", fymc="法院")
        d = record.to_dict()
        assert d["ah"] == "test"
        assert d["sdbh"] == "1"


class TestDocumentDetail:
    """DocumentDetail 数据类测试。"""

    def test_from_api_response(self) -> None:
        data = {
            "c_sdbh": "123",
            "c_wsmc": "判决书",
            "c_wjgs": "pdf",
            "wjlj": "https://example.com/file.pdf",
        }
        detail = DocumentDetail.from_api_response(data)
        assert detail.c_sdbh == "123"
        assert detail.c_wsmc == "判决书"

    def test_to_dict(self) -> None:
        detail = DocumentDetail(c_sdbh="123", c_wsmc="test", c_wjgs="pdf", wjlj="url")
        d = detail.to_dict()
        assert d["c_sdbh"] == "123"


class TestDocumentListResponse:
    """DocumentListResponse 数据类测试。"""

    def test_from_api_response(self) -> None:
        data = {
            "data": {
                "total": 19,
                "data": [
                    {"ah": "test1", "sdbh": "1", "ajzybh": "2", "fssj": "", "fymc": ""},
                ],
            }
        }
        response = DocumentListResponse.from_api_response(data)
        assert response.total == 19
        assert len(response.documents) == 1

    def test_to_dict(self) -> None:
        response = DocumentListResponse(total=0, documents=[])
        d = response.to_dict()
        assert d["total"] == 0


class TestDocumentDeliveryRecord:
    """DocumentDeliveryRecord 数据类测试。"""

    def test_to_dict(self) -> None:
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=datetime(2025, 1, 1, 12, 0, 0),
            element_index=0,
        )
        d = record.to_dict()
        assert d["case_number"] == "test"
        assert d["send_time"] is not None

    def test_from_dict(self) -> None:
        data = {
            "case_number": "test",
            "send_time": "2025-01-01T12:00:00",
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.case_number == "test"
        assert record.send_time is not None

    def test_from_dict_none_send_time(self) -> None:
        data = {
            "case_number": "test",
            "send_time": None,
            "element_index": 0,
        }
        record = DocumentDeliveryRecord.from_dict(data)
        assert record.send_time is None


class TestDocumentRenamer:
    """DocumentRenamer 测试（规则模式）。"""

    def setup_method(self) -> None:
        self.renamer = DocumentRenamer()

    def test_normalize_title_candidate(self) -> None:
        """清理标题候选文本。"""
        assert self.renamer._normalize_title_candidate("") == ""
        assert self.renamer._normalize_title_candidate("  test  ") == "test"
        # 移除法院前缀
        result = self.renamer._normalize_title_candidate("佛山市禅城区人民法院民事判决书")
        assert "人民法院" not in result
        assert "民事判决书" in result

    def test_match_title_from_text_known_titles(self) -> None:
        """从已知标题列表匹配。"""
        result = self.renamer._match_title_from_text("民事判决书")
        assert result == "民事判决书"

    def test_match_title_from_text_longest_match(self) -> None:
        """选择最长匹配。"""
        result = self.renamer._match_title_from_text("裁判文书生效证明")
        assert result == "裁判文书生效证明"

    def test_match_title_from_text_pattern(self) -> None:
        """正则模式匹配。"""
        result = self.renamer._match_title_from_text("财产保全裁定书")
        assert result == "财产保全裁定书"

    def test_match_title_from_text_no_match(self) -> None:
        """无法匹配返回 None。"""
        result = self.renamer._match_title_from_text("随机文本内容")
        assert result is None

    def test_sanitize_filename_part(self) -> None:
        """清理文件名非法字符。"""
        assert self.renamer._sanitize_filename_part("") == ""
        assert self.renamer._sanitize_filename_part("test<>:\"/\\|?*file") == "testfile"
        assert self.renamer._sanitize_filename_part("  test.  ") == "test"

    def test_extract_title_from_filename(self) -> None:
        """从文件名提取标题。"""
        result = self.renamer._extract_title_from_filename("/path/民事判决书.pdf")
        assert result == "民事判决书"

    def test_extract_title_from_filename_no_match(self) -> None:
        """文件名无法匹配时使用原始文件名。"""
        result = self.renamer._extract_title_from_filename("/path/random_doc.pdf")
        assert result == "random_doc"

    def test_generate_filename(self) -> None:
        """生成规范文件名。"""
        from datetime import date

        result = self.renamer.generate_filename("民事判决书", "张三诉李四", date(2025, 1, 1))
        assert "民事判决书" in result
        assert result.endswith(".pdf")

    def test_generate_filename_empty_title(self) -> None:
        """空标题使用默认值。"""
        from datetime import date

        result = self.renamer.generate_filename("", "案件", date(2025, 1, 1))
        assert "司法文书" in result

    def test_generate_filename_empty_case_name(self) -> None:
        """空案件名使用默认值。"""
        from datetime import date

        result = self.renamer.generate_filename("判决书", "", date(2025, 1, 1))
        assert "未知案件" in result


class TestCaseFolderArchiveService:
    """CaseFolderArchiveService 测试。"""

    def setup_method(self) -> None:
        self.service = CaseFolderArchiveService()

    def test_mail_keyword_score_exact(self) -> None:
        """精确匹配邮件往来。"""
        assert self.service._mail_keyword_score("邮件往来") == 120
        assert self.service._mail_keyword_score("2-邮件往来") == 100
        assert self.service._mail_keyword_score("邮寄材料") == 80
        assert self.service._mail_keyword_score("邮件发送") == 60
        assert self.service._mail_keyword_score("其他") == 0

    def test_extract_leading_number(self) -> None:
        """提取文件夹名前缀数字。"""
        assert self.service._extract_leading_number("3-邮件往来") == 3
        assert self.service._extract_leading_number("12-邮寄材料") == 12
        assert self.service._extract_leading_number("邮件往来") == 0

    def test_sanitize_folder_name(self) -> None:
        """清理文件夹名。"""
        assert self.service._sanitize_folder_name("收到法院通知") == "收到法院通知"
        assert self.service._sanitize_folder_name("test<>:\"/\\|?*file") == "testfile"
        assert self.service._sanitize_folder_name("") == "收到材料"
        assert self.service._sanitize_folder_name("  ") == "收到材料"

    def test_infer_summary(self) -> None:
        """推断事件摘要。"""
        priority, summary = self.service._infer_summary("民事判决书")
        assert priority > 0
        assert "判决书" in summary

    def test_infer_summary_filing(self) -> None:
        """立案材料。"""
        priority, summary = self.service._infer_summary("立案通知书")
        assert priority >= 100

    def test_infer_summary_empty(self) -> None:
        """空文本。"""
        priority, summary = self.service._infer_summary("")
        assert priority == 0

    def test_extract_title_from_filename(self) -> None:
        """从文件名提取标题。"""
        result = self.service._extract_title_from_filename("/path/民事判决书（张三诉李四）_20250101收.pdf")
        assert "民事判决书" in result

    def test_extract_title_from_filename_with_underscore(self) -> None:
        """下划线分隔的文件名。"""
        result = self.service._extract_title_from_filename("/path/判决书_20250101.pdf")
        assert result == "判决书"

    def test_ensure_unique_directory(self) -> None:
        """确保目录名唯一。"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            result = self.service._ensure_unique_directory(parent, "test_folder")
            assert result.name == "test_folder"

            # 创建同名目录后再次调用
            result.mkdir()
            result2 = self.service._ensure_unique_directory(parent, "test_folder")
            assert result2.name == "test_folder_2"

    def test_ensure_unique_file_path(self) -> None:
        """确保文件路径唯一。"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            target = parent / "test.pdf"
            result = self.service._ensure_unique_file_path(target)
            assert result.name == "test.pdf"

            target.write_text("test")
            result2 = self.service._ensure_unique_file_path(target)
            assert result2.name == "test_2.pdf"

    def test_archive_sms_documents_no_case_id(self) -> None:
        """无案件 ID 跳过归档。"""
        sms = SimpleNamespace(id=1, case_id=None)
        result = self.service.archive_sms_documents(sms, ["/path/doc.pdf"])
        assert result is False

    def test_archive_sms_documents_no_paths(self) -> None:
        """无文书路径跳过归档。"""
        sms = SimpleNamespace(id=1, case_id=1)
        result = self.service.archive_sms_documents(sms, [])
        assert result is False
