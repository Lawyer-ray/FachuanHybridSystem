"""contracts.services.contract.integrations.ai_classify_service 单元测试。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from apps.contracts.models import ContractFolderScanStatus
from apps.contracts.services.contract.integrations.ai_classify_service import (
    apply_suggestion,
    parse_llm_items,
    relative_parent_folder,
    select_targets,
)

_MODULE = "apps.contracts.services.contract.integrations.ai_classify_service"


def _make_service(llm_fn: Any = None) -> Any:
    from apps.contracts.services.contract.integrations.ai_classify_service import ContractScanAIClassifyService

    return ContractScanAIClassifyService(llm_complete_fn=llm_fn)


# ── select_targets ─────────────────────────────────────────────────


class TestSelectTargets:
    def test_unmatched_scope_keeps_only_case_material_without_code(self):
        from apps.contracts.services.contract.integrations.ai_classify_service import ContractScanAIClassifyService

        candidates = [
            {"source_path": "a", "suggested_category": "case_material", "archive_item_code": ""},
            {"source_path": "b", "suggested_category": "case_material", "archive_item_code": "lt_7"},
            {"source_path": "c", "suggested_category": "invoice"},
            {"source_path": "d", "suggested_category": "contract_original"},
        ]
        targets = select_targets(candidates, scope="unmatched")
        assert [t["source_path"] for t in targets] == ["a"]

    def test_excludes_skipped_and_already_imported(self):
        from apps.contracts.services.contract.integrations.ai_classify_service import ContractScanAIClassifyService

        candidates = [
            {"source_path": "a", "suggested_category": "case_material", "archive_item_code": "", "skip_reason": "跳过"},
            {
                "source_path": "b",
                "suggested_category": "case_material",
                "archive_item_code": "",
                "already_imported": True,
            },
            {"source_path": "c", "suggested_category": "case_material", "archive_item_code": ""},
        ]
        targets = select_targets(candidates, scope="unmatched")
        assert [t["source_path"] for t in targets] == ["c"]

    def test_all_scope_includes_matched_and_terminal_categories(self):
        from apps.contracts.services.contract.integrations.ai_classify_service import ContractScanAIClassifyService

        candidates = [
            {"source_path": "a", "suggested_category": "case_material", "archive_item_code": ""},
            {"source_path": "b", "suggested_category": "invoice"},
            {
                "source_path": "c",
                "suggested_category": "case_material",
                "archive_item_code": "lt_7",
                "skip_reason": "x",
            },
        ]
        targets = select_targets(candidates, scope="all")
        assert [t["source_path"] for t in targets] == ["a", "b"]


# ── parse_llm_items ────────────────────────────────────────────────


class TestParseLLMItems:
    def test_plain_array(self):
        svc = _make_service()
        payload = [{"index": 1, "category": "case_material", "archive_item_code": "lt_7"}]
        assert parse_llm_items(json.dumps(payload)) == payload

    def test_fenced_json_array(self):
        svc = _make_service()
        content = '```json\n[{"index": 1, "category": "invoice"}]\n```'
        result = parse_llm_items(content)
        assert result == [{"index": 1, "category": "invoice"}]

    def test_array_with_noise_drops_non_dict_items(self):
        svc = _make_service()
        content = '[{"index": 1}, "垃圾", {"index": 2}]'
        result = parse_llm_items(content)
        assert len(result) == 2

    def test_invalid_returns_empty(self):
        svc = _make_service()
        assert parse_llm_items("不是 JSON") == []
        assert parse_llm_items("") == []
        assert parse_llm_items('{"index": 1}') == []


# ── apply_suggestion ───────────────────────────────────────────────


class TestApplySuggestion:
    CODES = {"lt_7": "起诉书、上诉书或答辩书", "lt_10": "证据材料"}

    def test_valid_case_material_applied_and_selected(self):
        svc = _make_service()
        candidate = {"suggested_category": "case_material", "archive_item_code": "", "selected": False}
        ok = apply_suggestion(
            candidate,
            {"category": "case_material", "archive_item_code": "lt_7", "confidence": 0.9, "reason": "起诉文书"},
            code_to_name=self.CODES,
        )
        assert ok is True
        assert candidate["archive_item_code"] == "lt_7"
        assert candidate["archive_item_name"] == "起诉书、上诉书或答辩书"
        assert candidate["classified_by"] == "ai"
        assert candidate["selected"] is True
        assert candidate["reason"].startswith("AI：")

    def test_invalid_code_rejected_without_mutation(self):
        svc = _make_service()
        candidate = {"suggested_category": "case_material", "archive_item_code": "", "selected": False}
        ok = apply_suggestion(
            candidate,
            {"category": "case_material", "archive_item_code": "lt_999", "confidence": 0.9},
            code_to_name=self.CODES,
        )
        assert ok is False
        assert candidate["archive_item_code"] == ""
        assert "classified_by" not in candidate

    def test_invalid_category_rejected(self):
        svc = _make_service()
        candidate = {"suggested_category": "case_material", "archive_item_code": ""}
        ok = apply_suggestion(candidate, {"category": "unknown_type"}, code_to_name=self.CODES)
        assert ok is False

    def test_non_case_material_clears_code(self):
        svc = _make_service()
        candidate = {"suggested_category": "case_material", "archive_item_code": "lt_7", "selected": False}
        ok = apply_suggestion(
            candidate,
            {"category": "invoice", "archive_item_code": "lt_7", "confidence": 2},
            code_to_name=self.CODES,
        )
        assert ok is True
        assert candidate["suggested_category"] == "invoice"
        assert candidate["archive_item_code"] == ""
        assert candidate["confidence"] == 1.0

    def test_confidence_invalid_value_falls_to_zero(self):
        svc = _make_service()
        candidate = {"suggested_category": "case_material", "archive_item_code": ""}
        ok = apply_suggestion(
            candidate,
            {"category": "case_material", "archive_item_code": "lt_10", "confidence": "abc"},
            code_to_name=self.CODES,
        )
        assert ok is True
        assert candidate["confidence"] == 0.0


# ── _relative_parent_folder ────────────────────────────────────────


class TestRelativeParentFolder:
    def test_within_root(self):
        svc = _make_service()
        result = relative_parent_folder(
            source_path="/root/2-立案材料/起诉状.pdf",
            scan_folder="/root",
        )
        assert result == "2-立案材料"

    def test_outside_root_falls_back_to_full_parent(self):
        svc = _make_service()
        result = relative_parent_folder(source_path="/other/起诉状.pdf", scan_folder="/root")
        assert result == "other"

    def test_direct_child_returns_empty(self):
        svc = _make_service()
        result = relative_parent_folder(source_path="/root/合同.pdf", scan_folder="/root")
        assert result == ""


# ── run_ai_classify_task 全流程（注入假 LLM） ─────────────────────


def _fake_llm(payload: list[dict[str, Any]]):
    def _complete(*, prompt: str, system_prompt: str, model_id: str) -> str:
        return json.dumps(payload, ensure_ascii=False)

    return _complete


def _make_session(candidates: list[dict[str, Any]]) -> MagicMock:
    session = MagicMock()
    session.id = uuid4()
    session.contract.name = "测试合同"
    session.contract.case_type = "litigation_case"
    session.result_payload = {
        "summary": {},
        "candidates": candidates,
        "archive_category": "litigation",
        "scan_scope": {"scan_folder": "/root"},
    }
    return session


class TestRunAIClassifyTask:
    def _candidates(self) -> list[dict[str, Any]]:
        return [
            {
                "source_path": "/root/2-立案材料/起诉状.pdf",
                "filename": "起诉状.pdf",
                "suggested_category": "case_material",
                "archive_item_code": "",
                "archive_item_name": "未匹配",
                "selected": False,
            },
        ]

    @patch(f"{_MODULE}.ContractFolderScanSession")
    def test_classifies_and_writes_back(self, MockSession):
        session = _make_session(self._candidates())
        MockSession.objects.select_related.return_value.filter.return_value.first.return_value = session
        llm = _fake_llm(
            [
                {
                    "index": 1,
                    "category": "case_material",
                    "archive_item_code": "lt_7",
                    "confidence": 0.9,
                    "reason": "起诉文书",
                }
            ]
        )
        svc = _make_service(llm)

        svc.run_ai_classify_task(session_id=str(session.id))

        update_calls = MockSession.objects.filter.return_value.update.call_args_list
        final_kwargs = update_calls[-1].kwargs
        assert final_kwargs["status"] == ContractFolderScanStatus.COMPLETED
        payload = final_kwargs["result_payload"]
        candidate = payload["candidates"][0]
        assert candidate["archive_item_code"] == "lt_7"
        assert candidate["classified_by"] == "ai"
        assert candidate["selected"] is True
        assert payload["ai_classify_result"]["classified"] == 1
        assert payload["ai_classify_result"]["targets"] == 1

    @patch(f"{_MODULE}.ContractFolderScanSession")
    def test_llm_failure_keeps_candidates_and_returns_completed(self, MockSession):
        session = _make_session(self._candidates())
        MockSession.objects.select_related.return_value.filter.return_value.first.return_value = session

        def _raise(*, prompt: str, system_prompt: str, model_id: str) -> str:
            raise RuntimeError("llm down")

        svc = _make_service(_raise)
        svc.run_ai_classify_task(session_id=str(session.id))

        update_calls = MockSession.objects.filter.return_value.update.call_args_list
        final_kwargs = update_calls[-1].kwargs
        assert final_kwargs["status"] == ContractFolderScanStatus.COMPLETED
        payload = final_kwargs["result_payload"]
        assert payload["ai_classify_result"]["llm_failed"] == 1
        assert payload["candidates"][0]["archive_item_code"] == ""
        assert payload["candidates"][0]["selected"] is False

    @patch(f"{_MODULE}.ContractFolderScanSession")
    def test_invalid_suggestion_counts_as_invalid(self, MockSession):
        session = _make_session(self._candidates())
        MockSession.objects.select_related.return_value.filter.return_value.first.return_value = session
        llm = _fake_llm([{"index": 1, "category": "case_material", "archive_item_code": "lt_404"}])
        svc = _make_service(llm)

        svc.run_ai_classify_task(session_id=str(session.id))

        final_kwargs = MockSession.objects.filter.return_value.update.call_args_list[-1].kwargs
        payload = final_kwargs["result_payload"]
        assert payload["ai_classify_result"]["invalid"] == 1
        assert payload["candidates"][0]["archive_item_code"] == ""

    @patch(f"{_MODULE}.ContractFolderScanSession")
    def test_missing_session_is_noop(self, MockSession):
        MockSession.objects.select_related.return_value.filter.return_value.first.return_value = None
        svc = _make_service()
        svc.run_ai_classify_task(session_id=str(uuid4()))
        MockSession.objects.filter.return_value.update.assert_not_called()


# ── start_ai_classify 状态守卫 ─────────────────────────────────────


class TestStartAIClassify:
    @patch(f"{_MODULE}.ContractFolderScanSession")
    def test_rejects_non_completed_session(self, MockSession):
        from apps.core.exceptions import ValidationException

        session = MagicMock()
        session.status = ContractFolderScanStatus.IMPORTED
        MockSession.objects.get.return_value = session
        svc = _make_service()
        with pytest.raises(ValidationException, match="仅扫描完成"):
            svc.start_ai_classify(contract_id=1, session_id=uuid4())
