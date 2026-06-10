"""SMS 去重、案件匹配、文书重命名测试 - 真实执行代码。"""

from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.sms.court_sms_dedup_service import (
    CourtSMSDedupIdentity,
    CourtSMSDedupResult,
    CourtSMSDedupService,
)
from apps.automation.services.sms.case_matcher import CaseMatcher
from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord
from apps.automation.services.sms.document_renamer import DocumentRenamer


class TestCourtSMSDedupService:
    """测试 CourtSMS 去重服务。"""

    def setup_method(self) -> None:
        self.service = CourtSMSDedupService()

    def test_normalize_text(self) -> None:
        assert self.service._normalize_text("  hello   world  ") == "hello world"
        assert self.service._normalize_text(None) == ""
        assert self.service._normalize_text("") == ""

    def test_hash_payload(self) -> None:
        h = self.service._hash_payload("test")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_hash_payload_deterministic(self) -> None:
        assert self.service._hash_payload("test") == self.service._hash_payload("test")

    def test_hash_payload_different_inputs(self) -> None:
        assert self.service._hash_payload("a") != self.service._hash_payload("b")

    def test_build_identity_with_event_id(self) -> None:
        """有 delivery_event_id 时使用 event_id 生成身份。"""
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=datetime(2025, 1, 1),
            element_index=0,
            delivery_event_id="SD001",
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_id == "SD001"
        assert identity.event_key is not None
        assert identity.uses_fallback is False

    def test_build_identity_fallback(self) -> None:
        """无 delivery_event_id 时使用 case_number + send_time 生成身份。"""
        record = DocumentDeliveryRecord(
            case_number="（2025）粤0604民初1号",
            send_time=datetime(2025, 1, 1, 12, 0, 0),
            element_index=0,
            court_name="测试法院",
            document_name="判决书",
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_id is None
        assert identity.event_key is not None
        assert identity.uses_fallback is True

    def test_build_identity_no_event_id_no_send_time(self) -> None:
        """无 event_id 且无 send_time 时返回空身份。"""
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=None,
            element_index=0,
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_id is None
        assert identity.event_key is None
        assert identity.uses_fallback is False

    def test_build_identity_no_case_number(self) -> None:
        """无 case_number 且无 send_time 时返回空身份。"""
        record = DocumentDeliveryRecord(
            case_number="",
            send_time=None,
            element_index=0,
        )
        identity = self.service.build_document_delivery_identity(record)
        assert identity.event_key is None

    def test_build_identity_deterministic(self) -> None:
        """相同输入生成相同身份。"""
        record = DocumentDeliveryRecord(
            case_number="test",
            send_time=datetime(2025, 1, 1),
            element_index=0,
            delivery_event_id="SD001",
        )
        id1 = self.service.build_document_delivery_identity(record)
        id2 = self.service.build_document_delivery_identity(record)
        assert id1.event_key == id2.event_key

    def test_build_existing_sms_result_with_notification(self) -> None:
        """有通知结果时 notification_sent=True。"""
        sms = SimpleNamespace(
            case_id=1,
            case_log_id=1,
            notification_results={"feishu": {"success": True}},
            feishu_sent_at=None,
        )
        result = self.service.build_existing_sms_result(sms, "/tmp/test.pdf")
        assert result["success"] is True
        assert result["notification_sent"] is True
        assert result["renamed_path"] == "/tmp/test.pdf"
        assert result["deduplicated"] is True

    def test_build_existing_sms_result_no_notification(self) -> None:
        """无通知结果时 notification_sent=False。"""
        sms = SimpleNamespace(
            case_id=1,
            case_log_id=1,
            notification_results=None,
            feishu_sent_at=None,
        )
        result = self.service.build_existing_sms_result(sms, "/tmp/test.pdf")
        assert result["notification_sent"] is False

    def test_build_existing_sms_result_feishu_sent_at(self) -> None:
        """旧字段 feishu_sent_at 也视为已通知。"""
        sms = SimpleNamespace(
            case_id=1,
            case_log_id=1,
            notification_results=None,
            feishu_sent_at=datetime(2025, 1, 1),
        )
        result = self.service.build_existing_sms_result(sms, "/tmp/test.pdf")
        assert result["notification_sent"] is True


class TestCourtSMSDedupIdentity:
    """测试 CourtSMSDedupIdentity 数据类。"""

    def test_frozen(self) -> None:
        identity = CourtSMSDedupIdentity(event_id="SD001", event_key="abc", canonical_payload="{}")
        with pytest.raises(AttributeError):
            identity.event_id = "SD002"  # type: ignore[misc]

    def test_defaults(self) -> None:
        identity = CourtSMSDedupIdentity(event_id=None, event_key=None, canonical_payload=None)
        assert identity.uses_fallback is False


class TestCaseMatcher:
    """测试 CaseMatcher。"""

    def setup_method(self) -> None:
        self.matcher = CaseMatcher(
            case_service=MagicMock(),
            document_parser_service=MagicMock(),
            party_matching_service=MagicMock(),
        )

    def test_detect_case_type_civil(self) -> None:
        assert self.matcher._detect_case_type_from_number("（2025）粤0604民初1号") == "civil"

    def test_detect_case_type_criminal(self) -> None:
        assert self.matcher._detect_case_type_from_number("（2025）粤0604刑初1号") == "criminal"

    def test_detect_case_type_administrative(self) -> None:
        assert self.matcher._detect_case_type_from_number("（2025）粤0604行初1号") == "administrative"

    def test_detect_case_type_empty(self) -> None:
        assert self.matcher._detect_case_type_from_number("") is None

    def test_detect_case_stage_first_trial(self) -> None:
        assert self.matcher._detect_case_stage_from_number("（2025）粤0604民初1号") == "first_trial"

    def test_detect_case_stage_second_trial(self) -> None:
        assert self.matcher._detect_case_stage_from_number("（2025）粤0604民终1号") == "second_trial"

    def test_detect_case_stage_enforcement(self) -> None:
        assert self.matcher._detect_case_stage_from_number("（2025）粤0604执1号") == "enforcement"

    def test_detect_case_stage_zhibao(self) -> None:
        """执保案件不返回执行阶段。"""
        assert self.matcher._detect_case_stage_from_number("（2025）粤0604执保1号") is None

    def test_detect_case_stage_empty(self) -> None:
        assert self.matcher._detect_case_stage_from_number("") is None

    def test_is_bankruptcy_case_number(self) -> None:
        assert self.matcher._is_bankruptcy_case_number("（2025）粤0604破1号") is True

    def test_is_not_bankruptcy_case_number(self) -> None:
        assert self.matcher._is_bankruptcy_case_number("（2025）粤0604民初1号") is False

    def test_is_bankruptcy_empty(self) -> None:
        assert self.matcher._is_bankruptcy_case_number("") is False

    def test_select_latest_case(self) -> None:
        case1 = SimpleNamespace(id=1, name="案件1", current_stage="first_trial")
        case2 = SimpleNamespace(id=3, name="案件3", current_stage="first_trial")
        case3 = SimpleNamespace(id=2, name="案件2", current_stage="first_trial")
        result = self.matcher._select_latest_case([case1, case2, case3])
        assert result.id == 3

    def test_select_latest_case_single(self) -> None:
        case = SimpleNamespace(id=1, name="案件1", current_stage="first_trial")
        result = self.matcher._select_latest_case([case])
        assert result.id == 1

    def test_select_latest_case_empty(self) -> None:
        assert self.matcher._select_latest_case([]) is None

    def test_extract_features_from_numbers(self) -> None:
        case_type, case_stage, is_bankruptcy = self.matcher._extract_features_from_numbers(
            ["（2025）粤0604民初1号"]
        )
        assert case_type == "civil"
        assert case_stage == "first_trial"
        assert is_bankruptcy is False

    def test_extract_features_bankruptcy(self) -> None:
        case_type, case_stage, is_bankruptcy = self.matcher._extract_features_from_numbers(
            ["（2025）粤0604破1号"]
        )
        assert is_bankruptcy is True

    def test_apply_type_filter(self) -> None:
        case1 = SimpleNamespace(case_type="civil", name="民事案件")
        case2 = SimpleNamespace(case_type="criminal", name="刑事案件")
        result = self.matcher._apply_type_filter([case1, case2], "civil")
        assert len(result) == 1
        assert result[0].case_type == "civil"

    def test_apply_type_filter_none(self) -> None:
        cases = [SimpleNamespace(case_type="civil"), SimpleNamespace(case_type="criminal")]
        result = self.matcher._apply_type_filter(cases, None)
        assert len(result) == 2

    def test_apply_stage_filter(self) -> None:
        case1 = SimpleNamespace(current_stage="first_trial")
        case2 = SimpleNamespace(current_stage="second_trial")
        result = self.matcher._apply_stage_filter([case1, case2], "first_trial")
        assert len(result) == 1

    def test_apply_stage_filter_none(self) -> None:
        cases = [SimpleNamespace(current_stage="first_trial")]
        result = self.matcher._apply_stage_filter(cases, None)
        assert len(result) == 1

    def test_extract_party_names_from_sms(self) -> None:
        """短信有2个以上当事人时直接使用。"""
        sms = SimpleNamespace(party_names=["张三", "李四"])
        result = self.matcher._extract_party_names(sms)
        assert result == ["张三", "李四"]

    def test_extract_party_names_single_party_tries_document(self) -> None:
        """短信只有1个当事人时尝试从文书提取。"""
        self.matcher._document_parser_service.get_all_document_paths.return_value = []
        sms = SimpleNamespace(party_names=["张三"])
        result = self.matcher._extract_party_names(sms)
        assert result == ["张三"]

    def test_extract_party_names_no_parties(self) -> None:
        """无当事人返回空列表。"""
        self.matcher._document_parser_service.get_all_document_paths.return_value = []
        sms = SimpleNamespace(party_names=[])
        result = self.matcher._extract_party_names(sms)
        assert result == []

    def test_match_exits_gracefully_on_exception(self) -> None:
        """匹配过程中的异常被捕获。"""
        sms = SimpleNamespace(case_numbers=[], party_names=[])
        self.matcher._document_parser_service.get_all_document_paths.side_effect = Exception("test error")
        with pytest.raises(Exception):
            self.matcher.match(sms)


class TestDocumentRenamer:
    """测试文书重命名服务。"""

    def setup_method(self) -> None:
        with patch("apps.automation.services.sms.document_renamer.get_config", return_value=50):
            self.renamer = DocumentRenamer()

    def test_normalize_title_candidate(self) -> None:
        result = self.renamer._normalize_title_candidate("  \"判决书\"  ")
        assert result == "判决书"

    def test_normalize_title_candidate_removes_court_prefix(self) -> None:
        result = self.renamer._normalize_title_candidate("佛山市禅城区人民法院判决书")
        assert "判决书" in result

    def test_normalize_title_candidate_removes_pdf(self) -> None:
        result = self.renamer._normalize_title_candidate("判决书.pdf")
        assert result == "判决书"

    def test_match_title_judgment(self) -> None:
        result = self.renamer._match_title_from_text("民事判决书")
        assert result == "民事判决书"

    def test_match_title_ruling(self) -> None:
        result = self.renamer._match_title_from_text("民事裁定书")
        assert result == "民事裁定书"

    def test_match_title_mediation(self) -> None:
        result = self.renamer._match_title_from_text("民事调解书")
        assert result == "民事调解书"

    def test_match_title_notice(self) -> None:
        result = self.renamer._match_title_from_text("受理案件通知书")
        assert result == "受理案件通知书"

    def test_match_title_longest_match(self) -> None:
        """最长匹配优先。"""
        result = self.renamer._match_title_from_text("裁判文书生效证明")
        assert result == "裁判文书生效证明"

    def test_match_title_no_match(self) -> None:
        result = self.renamer._match_title_from_text("这是一段无法识别的文本")
        assert result is None

    def test_match_title_empty(self) -> None:
        result = self.renamer._match_title_from_text("")
        assert result is None

    def test_sanitize_filename_part(self) -> None:
        result = self.renamer._sanitize_filename_part("test<>:\"/\\|?*file")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_sanitize_filename_part_empty(self) -> None:
        assert self.renamer._sanitize_filename_part("") == ""
        assert self.renamer._sanitize_filename_part(None) == ""

    def test_sanitize_filename_part_removes_control_chars(self) -> None:
        result = self.renamer._sanitize_filename_part("test\x00file")
        assert "\x00" not in result

    def test_sanitize_filename_part_removes_parens(self) -> None:
        result = self.renamer._sanitize_filename_part("test(1)file")
        assert "(" not in result
        assert ")" not in result

    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    def test_generate_filename(self, mock_fts: MagicMock) -> None:
        mock_fts.render_court_doc.return_value = "判决书（张三与李四合同纠纷）_20250101收"
        filename = self.renamer.generate_filename("判决书", "张三与李四合同纠纷", date(2025, 1, 1))
        assert filename.endswith(".pdf")
        assert "20250101" in filename

    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    def test_generate_filename_empty_title(self, mock_fts: MagicMock) -> None:
        mock_fts.render_court_doc.return_value = "司法文书（案件名称）_20250101收"
        filename = self.renamer.generate_filename("", "案件名称", date(2025, 1, 1))
        assert filename.endswith(".pdf")

    @patch("apps.automation.services.sms.document_renamer.FilenameTemplateService")
    def test_generate_filename_empty_case_name(self, mock_fts: MagicMock) -> None:
        mock_fts.render_court_doc.return_value = "判决书（未知案件）_20250101收"
        filename = self.renamer.generate_filename("判决书", "", date(2025, 1, 1))
        assert filename.endswith(".pdf")

    def test_extract_title_from_filename_with_known_title(self) -> None:
        result = self.renamer._extract_title_from_filename("/tmp/判决书.pdf")
        assert result == "判决书"

    def test_extract_title_from_filename_fallback(self) -> None:
        result = self.renamer._extract_title_from_filename("/tmp/unknown_file.pdf")
        assert result != ""

    def test_extract_title_from_filename_with_court_prefix(self) -> None:
        result = self.renamer._extract_title_from_filename("/tmp/佛山市禅城区人民法院判决书.pdf")
        assert "判决书" in result
