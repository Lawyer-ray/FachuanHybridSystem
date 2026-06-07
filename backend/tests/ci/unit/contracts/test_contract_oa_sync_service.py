"""合同 OA 同步服务测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService


class TestContractOASyncServiceHelpers:
    """ContractOASyncService 纯函数测试。"""

    def _make_service(self):
        return ContractOASyncService()

    # ── _normalize_match_text ──

    def test_normalize_match_text_removes_punctuation(self):
        svc = self._make_service()
        result = svc._normalize_match_text("张某-李某，合同纠纷")
        assert "-" not in result
        assert "，" not in result

    def test_normalize_match_text_removes_spaces(self):
        svc = self._make_service()
        result = svc._normalize_match_text("  hello  world  ")
        assert " " not in result

    def test_normalize_match_text_empty(self):
        svc = self._make_service()
        assert svc._normalize_match_text("") == ""

    def test_normalize_match_text_parens(self):
        svc = self._make_service()
        result = svc._normalize_match_text("张某(原告)")
        assert "(" not in result
        assert ")" not in result

    # ── _extract_lawsuit_party_tokens ──

    def test_extract_lawsuit_party_tokens_basic(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("张某诉李某合同纠纷")
        assert len(plaintiff) > 0
        assert len(defendant) > 0

    def test_extract_lawsuit_party_tokens_no_sue(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("合同审查")
        assert plaintiff == []
        assert defendant == []

    def test_extract_lawsuit_party_tokens_empty(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("")
        assert plaintiff == []
        assert defendant == []

    def test_extract_lawsuit_party_tokens_strips_dispute(self):
        svc = self._make_service()
        _, defendant = svc._extract_lawsuit_party_tokens("张某诉李某民间借贷纠纷")
        # "民间借贷纠纷" should be stripped
        for token in defendant:
            assert "纠纷" not in token

    # ── _split_party_tokens ──

    def test_split_party_tokens_single(self):
        svc = self._make_service()
        result = svc._split_party_tokens("张某", strip_dispute=False)
        assert "张某" in result

    def test_split_party_tokens_multiple(self):
        svc = self._make_service()
        result = svc._split_party_tokens("张某、李某", strip_dispute=False)
        assert len(result) >= 2

    def test_split_party_tokens_short_filtered(self):
        svc = self._make_service()
        result = svc._split_party_tokens("张", strip_dispute=False)
        assert result == []  # too short

    def test_split_party_tokens_removes_suffix(self):
        svc = self._make_service()
        result = svc._split_party_tokens("张某等", strip_dispute=False)
        assert all("等" not in t for t in result)

    def test_split_party_tokens_strip_dispute(self):
        svc = self._make_service()
        result = svc._split_party_tokens("李某合同纠纷", strip_dispute=True)
        for token in result:
            assert "纠纷" not in token

    # ── _build_relaxed_party_markers ──

    def test_build_relaxed_party_markers_company(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers(["广州测试有限公司"])
        assert len(markers) > 0
        # Should contain original and shortened versions
        assert "广州测试有限公司" in markers or any("测试" in m for m in markers)

    def test_build_relaxed_party_markers_person(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers(["张三"])
        assert len(markers) >= 1

    def test_build_relaxed_party_markers_empty(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers([])
        assert markers == []

    # ── _build_name_search_keywords ──

    def test_build_name_search_keywords_lawsuit_name(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("张某诉李某合同纠纷", contract_id=0)
        assert len(keywords) > 0
        assert "张某诉李某合同纠纷" in keywords

    def test_build_name_search_keywords_without_brackets(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("张某（原告）诉李某合同纠纷", contract_id=0)
        # Should have a keyword without brackets
        assert any("原告" not in k for k in keywords)

    def test_build_name_search_keywords_empty(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("", contract_id=0)
        assert keywords == []

    def test_build_name_search_keywords_max_10(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("张某诉李某合同纠纷" * 5, contract_id=0)
        assert len(keywords) <= 10

    # ── _extract_sso_login_url ──

    def test_extract_sso_login_url_found(self):
        svc = self._make_service()
        text = "请访问 https://access.jtn.com/login?token=abc123 完成登录"
        result = svc._extract_sso_login_url(text)
        assert "access.jtn.com" in result

    def test_extract_sso_login_url_not_found(self):
        svc = self._make_service()
        assert svc._extract_sso_login_url("普通错误信息") == ""

    def test_extract_sso_login_url_fallback(self):
        svc = self._make_service()
        text = "access.jtn.com 出现了问题"
        result = svc._extract_sso_login_url(text)
        assert result == "https://access.jtn.com/login"

    def test_extract_sso_login_url_empty(self):
        svc = self._make_service()
        assert svc._extract_sso_login_url("") == ""

    # ── _is_stale_active_session ──

    def test_is_stale_active_session_running_old(self):
        svc = self._make_service()
        session = MagicMock()
        session.status = "running"
        from django.utils import timezone
        from datetime import timedelta
        session.updated_at = timezone.now() - timedelta(minutes=10)
        assert svc._is_stale_active_session(session) is True

    def test_is_stale_active_session_running_recent(self):
        svc = self._make_service()
        session = MagicMock()
        session.status = "running"
        from django.utils import timezone
        session.updated_at = timezone.now()
        assert svc._is_stale_active_session(session) is False

    def test_is_stale_active_session_completed(self):
        svc = self._make_service()
        session = MagicMock()
        session.status = "completed"
        assert svc._is_stale_active_session(session) is False

    def test_is_stale_active_session_no_updated_at(self):
        svc = self._make_service()
        session = MagicMock()
        session.status = "running"
        session.updated_at = None
        assert svc._is_stale_active_session(session) is True

    # ── _filter_candidates_by_contract_name ──

    def test_filter_candidates_exact_match(self):
        svc = self._make_service()
        candidate = MagicMock()
        candidate.case_name = "张某诉李某合同纠纷"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张某诉李某合同纠纷", candidates=[candidate]
        )
        assert len(result) == 1

    def test_filter_candidates_no_match(self):
        svc = self._make_service()
        candidate = MagicMock()
        candidate.case_name = "完全不同的案件"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张某诉李某合同纠纷", candidates=[candidate]
        )
        assert len(result) == 0

    def test_filter_candidates_empty(self):
        svc = self._make_service()
        result = svc._filter_candidates_by_contract_name(contract_name="test", candidates=[])
        assert result == []

    # ── _serialize_missing_contracts ──

    def test_serialize_missing_contracts(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.id = 1
        contract.name = "测试合同"
        contract.law_firm_oa_url = ""
        contract.law_firm_oa_case_number = ""
        result = svc._serialize_missing_contracts([contract])
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["name"] == "测试合同"
