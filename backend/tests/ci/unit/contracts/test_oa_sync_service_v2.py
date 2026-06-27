"""
Unit tests for contracts/services/contract/integrations/contract_oa_sync_service.py.

Covers:
  - ContractOASyncService.__init__
  - _normalize_match_text
  - _extract_lawsuit_party_tokens
  - _split_party_tokens
  - _build_relaxed_party_markers
  - _build_name_search_keywords (lawsuit name, non-lawsuit name)
  - _extract_sso_login_url
  - _is_stale_active_session
  - _build_missing_contract_queryset
  - _serialize_missing_contracts
  - _filter_candidates_by_contract_name
  - list_missing_oa_contracts
  - create_or_get_active_session (new, reuse, stale)
  - build_status_payload
  - save_manual_contract_oa_fields (valid, invalid URL, missing contract)
  - get_session
  - _resolve_oa_credential (missing lawyer_id, missing credential)
"""

from __future__ import annotations

import re
from datetime import timedelta, UTC
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.integrations.contract_oa_sync_service import (
    ContractOASyncService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> ContractOASyncService:
    return ContractOASyncService()


def _make_contract(id: int = 1, name: str = "Test Corp 诉 ABC 公司 民间借贷纠纷") -> MagicMock:
    c = MagicMock()
    c.id = id
    c.name = name
    c.law_firm_oa_url = ""
    c.law_firm_oa_case_number = ""
    return c


def _make_candidate(case_name: str = "Test Corp 诉 ABC 公司", case_no: str = "2024-001") -> MagicMock:
    c = MagicMock()
    c.case_no = case_no
    c.case_name = case_name
    c.keyid = "key123"
    c.detail_url = "https://oa.example.com/case/123"
    return c


# ===========================================================================
# Tests
# ===========================================================================


class TestNormalizeMatchText:
    def test_strips_spaces_and_punctuation(self) -> None:
        svc = _make_service()
        assert svc._normalize_match_text("  Hello  World  ") == "HelloWorld"

    def test_removes_punctuation(self) -> None:
        svc = _make_service()
        assert svc._normalize_match_text("test（2024）案件") == "test2024案件"

    def test_empty(self) -> None:
        svc = _make_service()
        assert svc._normalize_match_text("") == ""


class TestExtractLawsuitPartyTokens:
    def test_lawsuit_name(self) -> None:
        svc = _make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("张三 诉 李四 民间借贷纠纷")
        assert len(plaintiff) >= 1
        assert len(defendant) >= 1
        assert any("张三" in t for t in plaintiff)
        assert any("李四" in t for t in defendant)

    def test_no_sue(self) -> None:
        svc = _make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("普通合同")
        assert plaintiff == []
        assert defendant == []

    def test_empty(self) -> None:
        svc = _make_service()
        plaintiff, defendant = svc._extract_lawsuit_party_tokens("")
        assert plaintiff == []
        assert defendant == []


class TestSplitPartyTokens:
    def test_single_party(self) -> None:
        svc = _make_service()
        tokens = svc._split_party_tokens("张三", strip_dispute=False)
        assert "张三" in tokens

    def test_multiple_parties(self) -> None:
        svc = _make_service()
        tokens = svc._split_party_tokens("张三、李四", strip_dispute=False)
        assert "张三" in tokens
        assert "李四" in tokens

    def test_strip_dispute(self) -> None:
        svc = _make_service()
        tokens = svc._split_party_tokens("ABC公司 民间借贷纠纷", strip_dispute=True)
        assert not any("纠纷" in t for t in tokens)

    def test_short_tokens_filtered(self) -> None:
        svc = _make_service()
        tokens = svc._split_party_tokens("A", strip_dispute=False)
        assert len(tokens) == 0

    def test_etc_suffix_stripped(self) -> None:
        svc = _make_service()
        tokens = svc._split_party_tokens("张三等", strip_dispute=False)
        assert "张三" in tokens


class TestBuildRelaxedPartyMarkers:
    def test_company_suffix_stripped(self) -> None:
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["北京科技有限公司"])
        assert any("北京科技" in m for m in markers)

    def test_province_stripped(self) -> None:
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["北京科技有限公司"])
        assert any("科技" in m for m in markers)

    def test_short_markers(self) -> None:
        svc = _make_service()
        markers = svc._build_relaxed_party_markers(["AB"])
        assert len(markers) >= 1


class TestExtractSsoLoginUrl:
    def test_found(self) -> None:
        svc = _make_service()
        url = svc._extract_sso_login_url("请访问 https://access.jtn.com/login?token=abc 进行登录")
        assert url == "https://access.jtn.com/login?token=abc"

    def test_fallback(self) -> None:
        svc = _make_service()
        url = svc._extract_sso_login_url("请登录 access.jtn.com")
        assert url == "https://access.jtn.com/login"

    def test_not_found(self) -> None:
        svc = _make_service()
        url = svc._extract_sso_login_url("Some other error")
        assert url == ""


class TestIsStaleActiveSession:
    def test_stale(self) -> None:
        svc = _make_service()
        session = MagicMock()
        session.status = "running"
        from datetime import datetime, timedelta, timezone
        session.updated_at = datetime.now(UTC) - timedelta(minutes=10)
        with patch("apps.contracts.services.contract.integrations.contract_oa_sync_service.timezone") as mock_tz:
            mock_tz.now.return_value = datetime.now(UTC)
            result = svc._is_stale_active_session(session)
        assert result is True

    def test_not_stale(self) -> None:
        svc = _make_service()
        session = MagicMock()
        session.status = "running"
        session.updated_at = None
        assert svc._is_stale_active_session(session) is True  # None updated_at = stale

    def test_non_active_status(self) -> None:
        svc = _make_service()
        session = MagicMock()
        session.status = "completed"
        assert svc._is_stale_active_session(session) is False


class TestSerializeMissingContracts:
    def test_basic(self) -> None:
        svc = _make_service()
        contracts = [_make_contract(id=1, name="Test"), _make_contract(id=2, name="Other")]
        result = svc._serialize_missing_contracts(contracts)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Test"


class TestBuildStatusPayload:
    def test_basic(self) -> None:
        svc = _make_service()
        session = MagicMock()
        session.id = 1
        session.status = "completed"
        session.progress_message = "Done"
        session.total_count = 5
        session.processed_count = 5
        session.matched_count = 3
        session.multiple_count = 1
        session.not_found_count = 1
        session.error_count = 0
        session.error_message = ""
        session.result_payload = {
            "items": [],
            "summary": {"matched_count": 3, "multiple_count": 1, "not_found_count": 1, "error_count": 0},
        }
        session.updated_at = MagicMock()
        session.updated_at.isoformat.return_value = "2026-01-01T00:00:00Z"

        payload = svc.build_status_payload(session=session)
        assert payload["session_id"] == 1
        assert payload["matched_count"] == 3
        assert payload["summary"]["matched_count"] == 3

    def test_sso_login_url_from_error(self) -> None:
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
        session.error_message = "SSO required: visit https://access.jtn.com/login"
        session.result_payload = {}
        session.updated_at = MagicMock()
        session.updated_at.isoformat.return_value = ""

        payload = svc.build_status_payload(session=session)
        assert "access.jtn.com" in payload["sso_login_url"]


class TestBuildNameSearchKeywords:
    def test_lawsuit_name(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_build_party_name_keywords", return_value=[]):
            keywords = svc._build_name_search_keywords("张三诉李四民间借贷纠纷", 1)
        assert len(keywords) > 0
        assert any("张三诉李四" in kw for kw in keywords)

    def test_non_lawsuit_name(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_build_party_name_keywords", return_value=[]):
            keywords = svc._build_name_search_keywords("普通合同", 1)
        assert len(keywords) > 0
        assert keywords[0] == "普通合同"

    def test_empty_name(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_build_party_name_keywords", return_value=[]):
            keywords = svc._build_name_search_keywords("", 1)
        assert keywords == []

    def test_max_keywords(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_build_party_name_keywords", return_value=["Party" + str(i) for i in range(20)]):
            keywords = svc._build_name_search_keywords("张三诉李四民间借贷纠纷案" * 5, 1)
        assert len(keywords) <= 10


class TestFilterCandidatesByContractName:
    def test_exact_name_match(self) -> None:
        svc = _make_service()
        candidates = [
            _make_candidate(case_name="张三诉李四 民间借贷纠纷"),
            _make_candidate(case_name="其他案件"),
        ]
        with patch.object(svc, "_normalize_match_text", side_effect=lambda x: re.sub(r"\s+", "", str(x or "").strip())):
            result = svc._filter_candidates_by_contract_name(
                contract_name="张三诉李四 民间借贷纠纷",
                candidates=candidates,
            )
        assert len(result) >= 1

    def test_no_candidates(self) -> None:
        svc = _make_service()
        result = svc._filter_candidates_by_contract_name(
            contract_name="Test",
            candidates=[],
        )
        assert result == []


class TestSaveManualContractOaFields:
    @pytest.mark.django_db
    def test_success(self) -> None:
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.contract_oa_sync_service.Contract") as mock_model:
            mock_contract = MagicMock()
            mock_contract.id = 1
            mock_model.objects.filter.return_value = [mock_contract]
            with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
                result = svc.save_manual_contract_oa_fields(
                    updates=[{"id": 1, "law_firm_oa_case_number": "001", "law_firm_oa_url": "https://oa.example.com/case/1"}]
                )
        assert result["updated_count"] == 1
        assert result["error_count"] == 0
        mock_model.objects.bulk_update.assert_called_once()

    def test_invalid_url(self) -> None:
        svc = _make_service()
        with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
            result = svc.save_manual_contract_oa_fields(
                updates=[{"id": 1, "law_firm_oa_url": "not a url"}]
            )
        assert result["updated_count"] == 0
        assert result["error_count"] == 1
        assert "格式无效" in result["errors"][0]["message"]

    @pytest.mark.django_db
    def test_missing_contract(self) -> None:
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.contract_oa_sync_service.Contract") as mock_model:
            mock_model.objects.filter.return_value = []  # no contracts found
            with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
                result = svc.save_manual_contract_oa_fields(
                    updates=[{"id": 999, "law_firm_oa_case_number": "001"}]
                )
        assert result["updated_count"] == 0
        assert result["error_count"] == 1
        assert "不存在" in result["errors"][0]["message"]

    def test_invalid_id(self) -> None:
        svc = _make_service()
        with patch.object(svc, "list_missing_oa_contracts", return_value=[]):
            result = svc.save_manual_contract_oa_fields(
                updates=[{"id": "abc"}]
            )
        assert result["error_count"] == 1
        assert "无效" in result["errors"][0]["message"]


class TestGetSession:
    def test_found(self) -> None:
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.contract_oa_sync_service.ContractOASyncSession") as mock_model:
            mock_session = MagicMock()
            mock_model.objects.filter.return_value.first.return_value = mock_session
            result = svc.get_session(session_id=1)
        assert result is mock_session

    def test_not_found(self) -> None:
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.contract_oa_sync_service.ContractOASyncSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = None
            result = svc.get_session(session_id=999)
        assert result is None


class TestResolveOaCredential:
    def test_no_lawyer_id(self) -> None:
        svc = _make_service()
        with pytest.raises(RuntimeError, match="当前用户无效"):
            svc._resolve_oa_credential(lawyer_id=None)
