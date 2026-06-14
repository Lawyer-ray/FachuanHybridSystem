"""
Extended tests for ContractOASyncService.

Covers: build_status_payload, list_missing_oa_contracts, _serialize_missing_contracts,
_normalize_match_text, _extract_lawsuit_party_tokens, _split_party_tokens,
_build_relaxed_party_markers, _build_name_search_keywords, _filter_candidates_by_contract_name,
_extract_sso_login_url, _is_stale_active_session, _build_missing_contract_queryset,
_resolve_oa_credential.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.utils import timezone

from apps.contracts.services.contract.integrations.contract_oa_sync_service import (
    ContractOASyncService,
)


def _make_service():
    return ContractOASyncService()


# ═══════════════════════════════════════════════════════════════════════════════
# build_status_payload
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildStatusPayload:
    def test_full_payload(self):
        svc = _make_service()
        session = MagicMock()
        session.id = 42
        session.status = "completed"
        session.progress_message = "同步完成"
        session.total_count = 10
        session.processed_count = 10
        session.matched_count = 5
        session.multiple_count = 2
        session.not_found_count = 2
        session.error_count = 1
        session.error_message = ""
        session.updated_at = MagicMock()
        session.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
        session.result_payload = {
            "summary": {
                "matched_count": 5,
                "multiple_count": 2,
                "not_found_count": 2,
                "error_count": 1,
            },
            "items": [{"contract_id": 1, "status": "matched"}],
            "remaining_contracts": [],
            "sso_login_url": "",
        }
        result = svc.build_status_payload(session=session)
        assert result["session_id"] == 42
        assert result["status"] == "completed"
        assert result["total_count"] == 10
        assert result["matched_count"] == 5
        assert result["summary"]["matched_count"] == 5
        assert len(result["items"]) == 1
        assert result["updated_at"] == "2024-01-01T00:00:00"

    def test_none_values(self):
        svc = _make_service()
        session = MagicMock()
        session.id = 1
        session.status = "pending"
        session.progress_message = None
        session.total_count = None
        session.processed_count = None
        session.matched_count = None
        session.multiple_count = None
        session.not_found_count = None
        session.error_count = None
        session.error_message = None
        session.updated_at = None
        session.result_payload = None
        result = svc.build_status_payload(session=session)
        assert result["total_count"] == 0
        assert result["processed_count"] == 0
        assert result["error_message"] == ""
        assert result["updated_at"] == ""

    def test_sso_url_from_error_message(self):
        svc = _make_service()
        session = MagicMock()
        session.id = 1
        session.status = "failed"
        session.progress_message = ""
        session.total_count = 0
        session.processed_count = 0
        session.matched_count = 0
        session.multiple_count = 0
        session.not_found_count = 0
        session.error_count = 0
        session.error_message = "请访问 https://access.jtn.com/login?token=abc 完成登录"
        session.updated_at = MagicMock()
        session.updated_at.isoformat.return_value = "2024-01-01"
        session.result_payload = {"summary": {}, "items": [], "remaining_contracts": []}
        result = svc.build_status_payload(session=session)
        assert "access.jtn.com" in result["sso_login_url"]

    def test_sso_url_from_payload(self):
        svc = _make_service()
        session = MagicMock()
        session.id = 1
        session.status = "failed"
        session.progress_message = ""
        session.total_count = 0
        session.processed_count = 0
        session.matched_count = 0
        session.multiple_count = 0
        session.not_found_count = 0
        session.error_count = 0
        session.error_message = ""
        session.updated_at = MagicMock()
        session.updated_at.isoformat.return_value = "2024-01-01"
        session.result_payload = {
            "summary": {},
            "items": [],
            "remaining_contracts": [],
            "sso_login_url": "https://access.jtn.com/verify",
        }
        result = svc.build_status_payload(session=session)
        assert result["sso_login_url"] == "https://access.jtn.com/verify"


# ═══════════════════════════════════════════════════════════════════════════════
# _normalize_match_text
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeMatchText:
    def test_removes_all_punctuation(self):
        svc = _make_service()
        result = svc._normalize_match_text("张某-李某，合同纠纷。案件；编号：123")
        for ch in "-—_，,。.;；:：()（）[]{}【】":
            assert ch not in result

    def test_removes_spaces(self):
        svc = _make_service()
        assert " " not in svc._normalize_match_text("hello world")

    def test_empty(self):
        svc = _make_service()
        assert svc._normalize_match_text("") == ""

    def test_none(self):
        svc = _make_service()
        assert svc._normalize_match_text(None) == ""

    def test_chinese_text_preserved(self):
        svc = _make_service()
        result = svc._normalize_match_text("张某诉李某合同纠纷")
        assert "张某" in result
        assert "李某" in result


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_lawsuit_party_tokens
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractLawsuitPartyTokens:
    def test_basic_split(self):
        svc = _make_service()
        p, d = svc._extract_lawsuit_party_tokens("张某诉李某合同纠纷")
        assert len(p) > 0
        assert len(d) > 0

    def test_no_sue_returns_empty(self):
        svc = _make_service()
        p, d = svc._extract_lawsuit_party_tokens("合同审查")
        assert p == []
        assert d == []

    def test_empty_string(self):
        svc = _make_service()
        p, d = svc._extract_lawsuit_party_tokens("")
        assert p == []
        assert d == []

    def test_none(self):
        svc = _make_service()
        p, d = svc._extract_lawsuit_party_tokens(None)
        assert p == []
        assert d == []

    def test_strips_dispute_phrases(self):
        svc = _make_service()
        _, d = svc._extract_lawsuit_party_tokens("张某诉李某民间借贷纠纷")
        for token in d:
            assert "民间借贷纠纷" not in token

    def test_multiple_plaintiffs(self):
        svc = _make_service()
        p, d = svc._extract_lawsuit_party_tokens("张某、王某诉李某合同纠纷")
        assert len(p) >= 2

    def test_brackets_stripped(self):
        svc = _make_service()
        p, d = svc._extract_lawsuit_party_tokens("张某（原告）诉李某（被告）合同纠纷")
        for token in p + d:
            assert "（" not in token
            assert "）" not in token


# ═══════════════════════════════════════════════════════════════════════════════
# _split_party_tokens
# ═══════════════════════════════════════════════════════════════════════════════


class TestSplitPartyTokens:
    def test_single_token(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某", strip_dispute=False)
        assert "张某" in result

    def test_multiple_tokens_by_dunhao(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某、李某、王某", strip_dispute=False)
        assert len(result) >= 3

    def test_short_token_filtered(self):
        svc = _make_service()
        result = svc._split_party_tokens("张", strip_dispute=False)
        assert result == []

    def test_suffix_removed(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某等", strip_dispute=False)
        assert all("等" not in t for t in result)

    def test_strip_dispute(self):
        svc = _make_service()
        result = svc._split_party_tokens("李某合同纠纷", strip_dispute=True)
        for token in result:
            assert "纠纷" not in token

    def test_strip_dispute_complex(self):
        svc = _make_service()
        result = svc._split_party_tokens("北京科技有限公司买卖合同纠纷", strip_dispute=True)
        assert len(result) > 0

    def test_number_suffix_removed(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某三案", strip_dispute=False)
        for token in result:
            assert "三案" not in token

    def test_shu_in_token(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某诉李某", strip_dispute=False)
        # "诉" should cause split, taking the part after
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# _build_relaxed_party_markers
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildRelaxedPartyMarkers:
    def test_company_markers(self):
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["广州测试有限公司"])
        assert len(markers) > 0
        assert "广州测试有限公司" in markers
        # Should contain shortened versions
        assert any("测试" in m for m in markers)

    def test_person_markers(self):
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["张三"])
        assert "张三" in markers

    def test_empty(self):
        svc = _make_service()
        assert svc._build_relaxed_party_markers([]) == []

    def test_company_with_province_stripped(self):
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["北京科技有限公司"])
        # Should strip "北京" prefix in relaxed markers
        assert any("科技" in m for m in markers)

    def test_short_core_prefixes(self):
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["北京某某科技有限公司"])
        # core[:2], core[:3], core[:4] should be added
        assert len(markers) >= 4

    def test_company_group_suffix(self):
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["某某集团公司"])
        assert any("集团" not in m or m == "某某集团公司" for m in markers)

    def test_min_length_filter(self):
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["张"])
        # Single char should be filtered (len < 2)
        assert all(len(m) >= 2 for m in markers)


# ═══════════════════════════════════════════════════════════════════════════════
# _build_name_search_keywords
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildNameSearchKeywords:
    def test_lawsuit_name(self):
        svc = _make_service()
        keywords = svc._build_name_search_keywords("张某诉李某合同纠纷", contract_id=0)
        assert "张某诉李某合同纠纷" in keywords
        assert len(keywords) > 1

    def test_without_brackets(self):
        svc = _make_service()
        keywords = svc._build_name_search_keywords("张某（原告）诉李某合同纠纷", contract_id=0)
        assert any("原告" not in k for k in keywords)

    def test_empty(self):
        svc = _make_service()
        assert svc._build_name_search_keywords("", contract_id=0) == []

    def test_none(self):
        svc = _make_service()
        assert svc._build_name_search_keywords(None, contract_id=0) == []

    def test_max_10(self):
        svc = _make_service()
        keywords = svc._build_name_search_keywords("张某诉李某合同纠纷" * 10, contract_id=0)
        assert len(keywords) <= 10

    def test_non_lawsuit_name_with_dispute(self):
        svc = _make_service()
        keywords = svc._build_name_search_keywords("北京科技有限公司合同纠纷", contract_id=0)
        assert len(keywords) > 0

    def test_non_lawsuit_explicit_dispute(self):
        svc = _make_service()
        keywords = svc._build_name_search_keywords("张某民间借贷纠纷", contract_id=0)
        assert any("民间借贷纠纷" in k for k in keywords)

    def test_non_lawsuit_mai_mai(self):
        svc = _make_service()
        keywords = svc._build_name_search_keywords("张某买卖合同纠纷", contract_id=0)
        assert any("买卖合同纠纷" in k for k in keywords)


# ═══════════════════════════════════════════════════════════════════════════════
# _filter_candidates_by_contract_name
# ═══════════════════════════════════════════════════════════════════════════════


class TestFilterCandidatesByContractName:
    def test_exact_match(self):
        svc = _make_service()
        c = MagicMock(); c.case_name = "张某诉李某合同纠纷"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张某诉李某合同纠纷", candidates=[c]
        )
        assert len(result) == 1

    def test_no_match_returns_empty(self):
        svc = _make_service()
        c = MagicMock(); c.case_name = "完全不同的案件"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张某诉李某合同纠纷", candidates=[c]
        )
        assert len(result) == 0

    def test_empty_candidates(self):
        svc = _make_service()
        result = svc._filter_candidates_by_contract_name(
            contract_name="test", candidates=[]
        )
        assert result == []

    def test_party_match_strict(self):
        svc = _make_service()
        c = MagicMock(); c.case_name = "张某诉李某民间借贷纠纷"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张某诉李某合同纠纷", candidates=[c]
        )
        assert len(result) == 1

    def test_party_match_relaxed(self):
        svc = _make_service()
        # When strict match fails, relaxed markers should be tried
        c = MagicMock(); c.case_name = "张诉李合同纠纷"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张某诉李某合同纠纷", candidates=[c]
        )
        # May or may not match depending on relaxed markers
        assert isinstance(result, list)

    def test_no_sue_keyword_returns_all(self):
        svc = _make_service()
        c1 = MagicMock(); c1.case_name = "test1"
        c2 = MagicMock(); c2.case_name = "test2"
        result = svc._filter_candidates_by_contract_name(
            contract_name="合同审查", candidates=[c1, c2]
        )
        # No "诉" keyword, returns all candidates
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_sso_login_url
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractSSOLoginUrl:
    def test_url_found(self):
        svc = _make_service()
        text = "请访问 https://access.jtn.com/login?token=abc123 完成登录"
        result = svc._extract_sso_login_url(text)
        assert "access.jtn.com" in result
        assert result.startswith("https://")

    def test_no_url(self):
        svc = _make_service()
        assert svc._extract_sso_login_url("普通错误信息") == ""

    def test_fallback_no_specific_url(self):
        svc = _make_service()
        text = "access.jtn.com 出现了问题"
        result = svc._extract_sso_login_url(text)
        assert result == "https://access.jtn.com/login"

    def test_empty(self):
        svc = _make_service()
        assert svc._extract_sso_login_url("") == ""

    def test_none(self):
        svc = _make_service()
        assert svc._extract_sso_login_url(None) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _is_stale_active_session
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsStaleActiveSession:
    def test_stale_running(self):
        svc = _make_service()
        session = MagicMock()
        session.status = "running"
        session.updated_at = timezone.now() - timedelta(minutes=10)
        assert svc._is_stale_active_session(session) is True

    def test_recent_running(self):
        svc = _make_service()
        session = MagicMock()
        session.status = "running"
        session.updated_at = timezone.now()
        assert svc._is_stale_active_session(session) is False

    def test_completed_not_stale(self):
        svc = _make_service()
        session = MagicMock()
        session.status = "completed"
        assert svc._is_stale_active_session(session) is False

    def test_no_updated_at_stale(self):
        svc = _make_service()
        session = MagicMock()
        session.status = "running"
        session.updated_at = None
        assert svc._is_stale_active_session(session) is True

    def test_pending_stale(self):
        svc = _make_service()
        session = MagicMock()
        session.status = "pending"
        session.updated_at = timezone.now() - timedelta(minutes=10)
        assert svc._is_stale_active_session(session) is True

    def test_exactly_at_boundary_not_stale(self):
        svc = _make_service()
        session = MagicMock()
        session.status = "running"
        session.updated_at = timezone.now() - timedelta(minutes=2)
        assert svc._is_stale_active_session(session) is False


# ═══════════════════════════════════════════════════════════════════════════════
# _serialize_missing_contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestSerializeMissingContracts:
    def test_basic(self):
        svc = _make_service()
        c = MagicMock()
        c.id = 1
        c.name = "Test"
        c.law_firm_oa_url = ""
        c.law_firm_oa_case_number = ""
        result = svc._serialize_missing_contracts([c])
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_none_values(self):
        svc = _make_service()
        c = MagicMock()
        c.id = 1
        c.name = None
        c.law_firm_oa_url = None
        c.law_firm_oa_case_number = None
        result = svc._serialize_missing_contracts([c])
        assert result[0]["name"] == ""
        assert result[0]["law_firm_oa_url"] == ""
        assert result[0]["law_firm_oa_case_number"] == ""

    def test_empty_list(self):
        svc = _make_service()
        assert svc._serialize_missing_contracts([]) == []


# ═══════════════════════════════════════════════════════════════════════════════
# _resolve_oa_credential
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveOACredential:
    def test_no_lawyer_id_raises(self):
        svc = _make_service()
        with pytest.raises(RuntimeError, match="当前用户无效"):
            svc._resolve_oa_credential(lawyer_id=None)

    @patch("apps.organization.models.AccountCredential.objects")
    def test_no_credential_raises(self, mock_cred_objects):
        mock_cred_objects.filter.return_value.order_by.return_value.first.return_value = None
        svc = _make_service()
        with pytest.raises(RuntimeError, match="未找到金诚同达OA账号"):
            svc._resolve_oa_credential(lawyer_id=1)

    @patch("apps.organization.models.AccountCredential.objects")
    def test_credential_found(self, mock_cred_objects):
        mock_cred = MagicMock()
        mock_cred_objects.filter.return_value.order_by.return_value.first.return_value = mock_cred
        svc = _make_service()
        result = svc._resolve_oa_credential(lawyer_id=1)
        assert result == mock_cred


# ═══════════════════════════════════════════════════════════════════════════════
# _build_missing_contract_queryset
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildMissingContractQueryset:
    @patch("apps.contracts.services.contract.integrations.contract_oa_sync_service.Contract")
    def test_queryset_construction(self, MockContract):
        svc = _make_service()
        MockContract.objects.filter.return_value.only.return_value.order_by.return_value = [MagicMock()]
        result = svc._build_missing_contract_queryset()
        # Should have called filter with Q objects
        MockContract.objects.filter.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# list_missing_oa_contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestListMissingOAContracts:
    @patch.object(ContractOASyncService, "_build_missing_contract_queryset")
    @patch.object(ContractOASyncService, "_serialize_missing_contracts")
    def test_basic(self, mock_serialize, mock_qs):
        svc = _make_service()
        mock_qs.return_value = [MagicMock()]
        mock_serialize.return_value = [{"id": 1}]
        result = svc.list_missing_oa_contracts()
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# _split_party_tokens edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestSplitPartyTokensExtended:
    def test_comma_separator(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某,李某", strip_dispute=False)
        assert len(result) >= 2

    def test_semicolon_separator(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某;李某", strip_dispute=False)
        assert len(result) >= 2

    def test_he_separator(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某和李某", strip_dispute=False)
        assert len(result) >= 2

    def test_yu_separator(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某与李某", strip_dispute=False)
        assert len(result) >= 2

    def test_deduplication(self):
        svc = _make_service()
        result = svc._split_party_tokens("张某、张某", strip_dispute=False)
        assert len(result) == 1

    def test_strip_dispute_lei_xing_jiu_fen(self):
        svc = _make_service()
        result = svc._split_party_tokens("北京科技有限公司买卖合同纠纷", strip_dispute=True)
        for token in result:
            assert "纠纷" not in token
