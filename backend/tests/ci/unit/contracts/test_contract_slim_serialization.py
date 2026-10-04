"""合同列表 slim 序列化的性能契约。

slim 此前是「from_orm 全量构建嵌套 DTO 后 data.pop()」——只省响应体，DB 取数
（prefetch）与 pydantic 构建成本一点没省。本文件锁定两件事：
1. slim 序列化对 finalized_materials / client_payment_records 零 SQL、零 DTO 构建
2. 非 slim（详情口径）行为不变：仍能读到关联数据
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.contracts.api.contract_api import _serialize_contract, _SlimContractView
from apps.contracts.models import Contract, FinalizedMaterial
from apps.contracts.models.contract import CaseType


@pytest.mark.django_db
class TestContractSlimSerialization:
    def _make_contract(self) -> Contract:
        contract = Contract.objects.create(name="slim 测试合同", case_type=CaseType.CIVIL)
        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/test/material.pdf",
            original_filename="material.pdf",
        )
        return contract

    def test_slim_view_hides_heavy_fields_only(self) -> None:
        contract = SimpleNamespace(name="甲合同", finalized_materials="HEAVY", client_payment_records="HEAVY")
        view = _SlimContractView(contract)
        assert view.name == "甲合同"  # 其余属性透传
        with pytest.raises(AttributeError):
            _ = view.finalized_materials
        with pytest.raises(AttributeError):
            _ = view.client_payment_records

    def test_slim_serialization_issues_no_query_for_heavy_relations(self) -> None:
        contract = self._make_contract()
        with CaptureQueriesContext(connection) as ctx:
            data = _serialize_contract(contract, slim=True)
        assert data["finalized_materials"] == []
        assert data["client_payment_records"] == []
        heavy_sqls = [
            q["sql"]
            for q in ctx.captured_queries
            if "finalizedmaterial" in q["sql"] or "clientpaymentrecord" in q["sql"].lower()
        ]
        assert not heavy_sqls, f"slim 序列化不应触碰重关系，实际执行: {heavy_sqls}"

    def test_full_serialization_still_loads_heavy_relations(self) -> None:
        contract = self._make_contract()
        data = _serialize_contract(contract, slim=False)
        assert len(data["finalized_materials"]) == 1

    def test_service_slim_queryset_skips_heavy_prefetch(self) -> None:
        from apps.contracts.services.contract.query.service import ContractQueryService

        self._make_contract()
        service = ContractQueryService()

        def _heavy_prefetch_sqls(*, slim: bool) -> list[str]:
            with CaptureQueriesContext(connection) as ctx:
                list(service.get_contract_queryset(slim=slim))
            return [q["sql"] for q in ctx.captured_queries if "finalizedmaterial" in q["sql"]]

        assert not _heavy_prefetch_sqls(slim=True), "slim queryset 不应预取归档材料"
        assert _heavy_prefetch_sqls(slim=False), "详情口径应保持归档材料预取"
