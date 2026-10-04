"""litigation_ai/session/context_service.py 单元测试（wiring 全 mock）.

覆盖案件信息映射（当事人 / 金额 / 案由）、NotFoundError 分支、
证据列表映射与 ownership 透传、同步与异步双版本一致性。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.litigation_ai.services.session.context_service import LitigationContextService


def _case_details() -> dict[str, Any]:
    return {
        "name": "张三诉李四民间借贷",
        "cause_of_action": "民间借贷纠纷",
        "target_amount": 150000,
        "current_stage": "一审",
        "status": "active",
        "case_parties": [
            {"client_name": "张三", "client_type": "个人", "legal_status": "原告", "is_our_client": True},
            {"client_name": "李四", "client_type": "个人", "legal_status": "被告", "is_our_client": False},
            {"client_name": "", "client_type": None, "legal_status": None, "is_our_client": None},
        ],
    }


def _mock_case_service(details: dict[str, Any] | None) -> Any:
    svc = SimpleNamespace(get_case_with_details_internal=lambda _cid: details)
    return svc


class TestGetCaseInfoForAgent:
    def test_maps_details_fields(self) -> None:
        svc = LitigationContextService()
        with patch(
            "apps.litigation_ai.services.wiring.get_case_service",
            return_value=_mock_case_service(_case_details()),
        ):
            info = svc.get_case_info_for_agent(3)

        assert info["case_id"] == 3
        assert info["case_name"] == "张三诉李四民间借贷"
        assert info["cause_of_action"] == "民间借贷纠纷"
        assert info["target_amount"] == "150000"  # 金额转字符串
        assert info["case_stage"] == "一审"
        assert info["case_status"] == "active"
        assert info["court_info"] is None
        assert info["our_legal_status"] is None
        # 当事人映射 + 空值容错
        assert info["parties"][0] == {
            "name": "张三",
            "party_type": "个人",
            "legal_status": "原告",
            "is_our_side": True,
        }
        assert info["parties"][1]["is_our_side"] is False
        assert info["parties"][2] == {"name": "", "party_type": "", "legal_status": "", "is_our_side": False}

    def test_not_found_raises(self) -> None:
        svc = LitigationContextService()
        with (
            patch("apps.litigation_ai.services.wiring.get_case_service", return_value=_mock_case_service(None)),
            pytest.raises(NotFoundError, match="案件不存在"),
        ):
            svc.get_case_info_for_agent(999)

    def test_none_amount_stays_none(self) -> None:
        details = _case_details()
        details["target_amount"] = None
        svc = LitigationContextService()
        with patch(
            "apps.litigation_ai.services.wiring.get_case_service",
            return_value=_mock_case_service(details),
        ):
            info = svc.get_case_info_for_agent(1)
        assert info["target_amount"] is None

    def test_missing_parties_key_tolerated(self) -> None:
        svc = LitigationContextService()
        with patch(
            "apps.litigation_ai.services.wiring.get_case_service",
            return_value=_mock_case_service({"name": "x"}),
        ):
            info = svc.get_case_info_for_agent(1)
        assert info["parties"] == []
        assert info["case_name"] == "x"


class TestAgetCaseInfoForAgent:
    @pytest.mark.asyncio
    async def test_async_version_maps_same_fields(self) -> None:
        svc = LitigationContextService()
        with patch(
            "apps.litigation_ai.services.wiring.get_case_service",
            return_value=_mock_case_service(_case_details()),
        ):
            info = await svc.aget_case_info_for_agent(3)
        assert info["case_name"] == "张三诉李四民间借贷"
        assert info["target_amount"] == "150000"
        assert len(info["parties"]) == 3

    @pytest.mark.asyncio
    async def test_async_not_found_raises(self) -> None:
        svc = LitigationContextService()
        with (
            patch("apps.litigation_ai.services.wiring.get_case_service", return_value=_mock_case_service(None)),
            pytest.raises(NotFoundError, match="案件不存在"),
        ):
            await svc.aget_case_info_for_agent(404)


def _evidence_items() -> list[Any]:
    return [
        SimpleNamespace(id=11, name="借条", purpose="证明借款事实", file_path="/data/borrow.pdf"),
        SimpleNamespace(id=12, name=None, purpose=None, file_path=None),
    ]


class TestGetEvidenceListForAgent:
    def test_maps_items(self) -> None:
        svc = LitigationContextService()
        query_svc = SimpleNamespace(list_evidence_items_for_case_internal=lambda _cid: _evidence_items())
        with patch(
            "apps.litigation_ai.services.wiring.get_evidence_query_service",
            return_value=query_svc,
        ):
            items = svc.get_evidence_list_for_agent(3, ownership="our")

        assert items[0] == {
            "evidence_item_id": 11,
            "name": "借条",
            "evidence_type": None,
            "ownership": "our",
            "description": "证明借款事实",
            "has_content": True,
        }
        assert items[1]["name"] == ""
        assert items[1]["has_content"] is False

    def test_ownership_none_passes_through(self) -> None:
        svc = LitigationContextService()
        query_svc = SimpleNamespace(list_evidence_items_for_case_internal=lambda _cid: [])
        with patch(
            "apps.litigation_ai.services.wiring.get_evidence_query_service",
            return_value=query_svc,
        ):
            assert svc.get_evidence_list_for_agent(3) == []


class TestAgetEvidenceListForAgent:
    @pytest.mark.asyncio
    async def test_async_version_maps_items(self) -> None:
        svc = LitigationContextService()
        query_svc = SimpleNamespace(list_evidence_items_for_case_internal=lambda _cid: _evidence_items())
        with patch(
            "apps.litigation_ai.services.wiring.get_evidence_query_service",
            return_value=query_svc,
        ):
            items = await svc.aget_evidence_list_for_agent(3, ownership="opponent")
        assert items[0]["evidence_item_id"] == 11
        assert items[0]["ownership"] == "opponent"


class TestGetPartiesForAgent:
    def test_uses_case_parties_relation(self) -> None:
        party = SimpleNamespace(name="王五", party_type="个人", legal_status="证人", is_our_side=True)
        case = SimpleNamespace(parties=SimpleNamespace(all=lambda: [party]))
        result = LitigationContextService()._get_parties_for_agent(case)
        assert result == [{"name": "王五", "party_type": "个人", "legal_status": "证人", "is_our_side": True}]

    def test_case_without_parties_attr(self) -> None:
        assert LitigationContextService()._get_parties_for_agent(SimpleNamespace()) == []

    def test_missing_attributes_default_empty(self) -> None:
        party = SimpleNamespace()  # getattr 全部落空
        case = SimpleNamespace(parties=SimpleNamespace(all=lambda: [party]))
        result = LitigationContextService()._get_parties_for_agent(case)
        assert result == [{"name": "", "party_type": "", "legal_status": "", "is_our_side": False}]
