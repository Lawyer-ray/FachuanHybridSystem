"""contract_oa_sync_service 补充覆盖测试。"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ── _normalize_match_text ────────────────────────────────────────

class TestNormalizeMatchText:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_strips_whitespace(self):
        svc = self._make_service()
        assert svc._normalize_match_text("  hello  world  ") == "helloworld"

    def test_strips_punctuation(self):
        svc = self._make_service()
        assert svc._normalize_match_text("test-case_name,。;：()") == "testcasename"

    def test_empty_input(self):
        svc = self._make_service()
        assert svc._normalize_match_text("") == ""
        assert svc._normalize_match_text(None) == ""  # type: ignore[arg-type]

    def test_chinese_punctuation(self):
        svc = self._make_service()
        result = svc._normalize_match_text("张三（原告）—诉")
        assert "（" not in result
        assert "）" not in result

    def test_brackets_removed(self):
        svc = self._make_service()
        result = svc._normalize_match_text("[test]{value}")
        assert "[" not in result
        assert "]" not in result


# ── _extract_lawsuit_party_tokens ─────────────────────────────────

class TestExtractLawsuitPartyTokens:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_no_sue_keyword(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("某合同纠纷")
        assert plaintiff == []
        assert defendant == []

    def test_basic_split(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("张三诉李四买卖合同纠纷")
        assert len(plaintiff) > 0
        assert len(defendant) > 0

    def test_multiple_plaintiffs(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("张三、李四诉王五合同纠纷")
        assert len(plaintiff) >= 2

    def test_empty_input(self):
        svc = self._make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("")
        assert plaintiff == []
        assert defendant == []


# ── _split_party_tokens ──────────────────────────────────────────

class TestSplitPartyTokens:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_basic_split_by_comma(self):
        svc = self._make_service()
        tokens = svc._split_party_tokens("张三、李四", strip_dispute=False)
        assert "张三" in tokens
        assert "李四" in tokens

    def test_strip_dispute_keywords(self):
        svc = self._make_service()
        tokens = svc._split_party_tokens("某公司买卖合同纠纷", strip_dispute=True)
        for t in tokens:
            assert "纠纷" not in t

    def test_empty(self):
        svc = self._make_service()
        tokens = svc._split_party_tokens("", strip_dispute=False)
        assert tokens == []

    def test_short_tokens_filtered(self):
        svc = self._make_service()
        tokens = svc._split_party_tokens("张、李四", strip_dispute=False)
        for t in tokens:
            assert len(t) >= 2


# ── _build_relaxed_party_markers ──────────────────────────────────

class TestBuildRelaxedPartyMarkers:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_company_suffix_stripped(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers(["北京科技有限公司"])
        assert any("科技" in m for m in markers)

    def test_province_stripped(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers(["北京科技有限公司"])
        # "北京科技" should appear without the province prefix
        assert any("科技" in m for m in markers)

    def test_empty_tokens(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers([])
        assert markers == []

    def test_dedup_markers(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers(["测试公司", "测试公司"])
        assert len(markers) == len(set(markers))

    def test_short_prefix_markers(self):
        svc = self._make_service()
        markers = svc._build_relaxed_party_markers(["北京某有限公司"])
        # Should generate 2-4 char prefixes
        assert len(markers) > 0


# ── _extract_sso_login_url ────────────────────────────────────────

class TestExtractSSOLoginURL:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_no_jtn_in_message(self):
        svc = self._make_service()
        assert svc._extract_sso_login_url("some error") == ""

    def test_url_extracted(self):
        svc = self._make_service()
        result = svc._extract_sso_login_url("请访问 https://access.jtn.com/sso/login?token=abc")
        assert result.startswith("https://access.jtn.com/")

    def test_fallback_url(self):
        svc = self._make_service()
        result = svc._extract_sso_login_url("access.jtn.com 需要登录但没有完整URL")
        assert result == "https://access.jtn.com/login"

    def test_empty_input(self):
        svc = self._make_service()
        assert svc._extract_sso_login_url("") == ""


# ── _is_stale_active_session ──────────────────────────────────────

class TestIsStaleActiveSession:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_non_active_status(self):
        svc = self._make_service()
        session = MagicMock()
        session.status = "completed"
        assert svc._is_stale_active_session(session) is False

    def test_no_updated_at(self):
        from apps.contracts.models import ContractOASyncStatus
        svc = self._make_service()
        session = MagicMock()
        session.status = ContractOASyncStatus.RUNNING
        session.updated_at = None
        assert svc._is_stale_active_session(session) is True

    def test_recent_session_not_stale(self):
        from apps.contracts.models import ContractOASyncStatus
        svc = self._make_service()
        session = MagicMock()
        session.status = ContractOASyncStatus.RUNNING
        session.updated_at = timezone.now()
        assert svc._is_stale_active_session(session) is False

    def test_old_session_is_stale(self):
        from apps.contracts.models import ContractOASyncStatus
        svc = self._make_service()
        session = MagicMock()
        session.status = ContractOASyncStatus.PENDING
        session.updated_at = timezone.now() - timedelta(minutes=10)
        assert svc._is_stale_active_session(session) is True


# ── build_status_payload ──────────────────────────────────────────

class TestBuildStatusPayload:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_basic_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = 1
        session.status = "running"
        session.progress_message = "处理中"
        session.total_count = 5
        session.processed_count = 2
        session.matched_count = 1
        session.multiple_count = 0
        session.not_found_count = 1
        session.error_count = 0
        session.error_message = ""
        session.result_payload = {"summary": {"matched_count": 1}, "items": [], "remaining_contracts": []}
        session.updated_at = timezone.now()

        payload = svc.build_status_payload(session=session)
        assert payload["session_id"] == 1
        assert payload["status"] == "running"
        assert payload["total_count"] == 5

    def test_sso_url_from_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = 1
        session.status = "failed"
        session.progress_message = "failed"
        session.total_count = 0
        session.processed_count = 0
        session.matched_count = 0
        session.multiple_count = 0
        session.not_found_count = 0
        session.error_count = 0
        session.error_message = ""
        session.result_payload = {
            "sso_login_url": "https://access.jtn.com/sso",
            "summary": {},
            "items": [],
            "remaining_contracts": [],
        }
        session.updated_at = timezone.now()

        payload = svc.build_status_payload(session=session)
        assert payload["sso_login_url"] == "https://access.jtn.com/sso"


# ── _update_session ───────────────────────────────────────────────

class TestUpdateSession:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_empty_fields_noop(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = 1
        svc._update_session(session)
        # Should not crash

    @pytest.mark.django_db
    def test_updates_set_on_session(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        from unittest.mock import patch as _patch

        svc = ContractOASyncService()
        session = MagicMock()
        session.id = 1
        with _patch("apps.contracts.models.ContractOASyncSession") as mock_model:
            svc._update_session(session, status="completed", progress_message="done")
            assert session.status == "completed"
            assert session.progress_message == "done"


# ── _serialize_missing_contracts ──────────────────────────────────

class TestSerializeMissingContracts:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_empty_list(self):
        svc = self._make_service()
        assert svc._serialize_missing_contracts([]) == []

    def test_serializes_fields(self):
        svc = self._make_service()
        contract = MagicMock()
        contract.id = 42
        contract.name = "Test Contract"
        contract.law_firm_oa_url = ""
        contract.law_firm_oa_case_number = ""
        result = svc._serialize_missing_contracts([contract])
        assert len(result) == 1
        assert result[0]["id"] == 42
        assert result[0]["name"] == "Test Contract"


# ── save_manual_contract_oa_fields ────────────────────────────────

class TestSaveManualContractOAFields:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_invalid_contract_id(self):
        svc = self._make_service()
        with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
            result = svc.save_manual_contract_oa_fields(updates=[{"id": "abc"}])
            assert result["error_count"] == 1
            assert result["updated_count"] == 0

    def test_invalid_url(self):
        svc = self._make_service()
        with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
            result = svc.save_manual_contract_oa_fields(
                updates=[{"id": 1, "law_firm_oa_url": "not-a-url"}]
            )
            assert result["error_count"] == 1

    @pytest.mark.django_db
    def test_contract_not_found(self):
        svc = self._make_service()
        with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
            result = svc.save_manual_contract_oa_fields(
                updates=[{"id": 999999, "law_firm_oa_case_number": "CN-001"}]
            )
            assert result["error_count"] == 1

    @pytest.mark.django_db
    def test_successful_update(self):
        from apps.contracts.models import Contract

        # Create a minimal contract
        contract = Contract.objects.create(name="Test Contract for OA")
        svc = self._make_service()
        with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
            result = svc.save_manual_contract_oa_fields(
                updates=[{"id": contract.id, "law_firm_oa_case_number": "CN-001"}]
            )
            assert result["updated_count"] == 1
            assert result["error_count"] == 0


# ── _filter_candidates_by_contract_name ───────────────────────────

class TestFilterCandidatesByContractName:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_empty_candidates(self):
        svc = self._make_service()
        result = svc._filter_candidates_by_contract_name(contract_name="test", candidates=[])
        assert result == []

    def test_exact_match(self):
        svc = self._make_service()
        candidate = MagicMock()
        candidate.case_name = "张三诉李四买卖合同纠纷"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张三诉李四买卖合同纠纷",
            candidates=[candidate],
        )
        assert len(result) == 1

    def test_party_filtering(self):
        svc = self._make_service()
        c1 = MagicMock()
        c1.case_name = "张三诉李四买卖合同纠纷"
        c2 = MagicMock()
        c2.case_name = "王五诉赵六借贷纠纷"
        result = svc._filter_candidates_by_contract_name(
            contract_name="张三诉李四合同纠纷",
            candidates=[c1, c2],
        )
        assert len(result) >= 1


# ── _build_name_search_keywords ───────────────────────────────────

class TestBuildNameSearchKeywords:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.contract_oa_sync_service import ContractOASyncService
        return ContractOASyncService()

    def test_empty_name(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("", contract_id=0)
        assert keywords == []

    def test_lawsuit_name_keywords(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("张三诉李四买卖合同纠纷", contract_id=0)
        assert len(keywords) > 0
        assert any("张三诉李四" in kw or "李四" in kw for kw in keywords)

    def test_non_lawsuit_name_with_dispute(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("某民间借贷纠纷案", contract_id=0)
        assert len(keywords) > 0

    def test_short_tail_keyword(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords("北京某公司与上海某公司合同纠纷案件委托代理合同", contract_id=0)
        assert len(keywords) > 0

    def test_max_10_keywords(self):
        svc = self._make_service()
        keywords = svc._build_name_search_keywords(
            "张三诉李四、王五、赵六、钱七、孙八买卖合同纠纷案件",
            contract_id=0,
        )
        assert len(keywords) <= 10
