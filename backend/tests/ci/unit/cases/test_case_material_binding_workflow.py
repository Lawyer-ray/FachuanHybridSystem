"""CaseMaterialBindingWorkflow 分组排序（_ensure_group_orders）单元测试。

覆盖：新分组按绑定顺序追加 sort_index、已有分组顺序保留、
多分组维度互不影响、重复 type 去重。
"""

from __future__ import annotations

import pytest

from apps.cases.models import (
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialGroupOrder,
    CaseMaterialSide,
    CaseMaterialType,
    SupervisingAuthority,
)
from apps.cases.services.material.case_material_binding_workflow import CaseMaterialBindingWorkflow
from apps.testing.factories import CaseFactory


def _make_material(case, *, category: str, type_obj: CaseMaterialType, side: str = "", authority=None) -> CaseMaterial:
    return CaseMaterial.objects.create(
        case=case,
        category=category,
        type=type_obj,
        type_name=type_obj.name,
        side=side,
        supervising_authority=authority,
    )


@pytest.mark.django_db
class TestEnsureGroupOrders:
    def test_appends_index_in_binding_order(self) -> None:
        case = CaseFactory()
        t1 = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="起诉状")
        t2 = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="证据清单")
        materials = [
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t2, side=CaseMaterialSide.OUR),
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t1, side=CaseMaterialSide.OUR),
        ]

        CaseMaterialBindingWorkflow()._ensure_group_orders(case.id, materials)

        orders = {
            o.type_id: o.sort_index for o in CaseMaterialGroupOrder.objects.filter(case=case, side=CaseMaterialSide.OUR)
        }
        assert orders == {t2.id: 0, t1.id: 1}

    def test_existing_order_preserved_new_appended_after_max(self) -> None:
        case = CaseFactory()
        t1 = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="既有类型")
        t2 = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="新增类型")
        CaseMaterialGroupOrder.objects.create(
            case=case,
            category=CaseMaterialCategory.PARTY,
            side=CaseMaterialSide.OUR,
            supervising_authority=None,
            type=t1,
            sort_index=5,
        )
        materials = [
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t1, side=CaseMaterialSide.OUR),
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t2, side=CaseMaterialSide.OUR),
        ]

        CaseMaterialBindingWorkflow()._ensure_group_orders(case.id, materials)

        orders = {
            o.type_id: o.sort_index for o in CaseMaterialGroupOrder.objects.filter(case=case, side=CaseMaterialSide.OUR)
        }
        assert orders == {t1.id: 5, t2.id: 6}

    def test_group_dimensions_isolated(self) -> None:
        """我方/对方分组各自从 0 开始计数。"""
        case = CaseFactory()
        t_our = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="我方材料")
        t_opp = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="对方材料")
        t_non_party = CaseMaterialType.objects.create(category=CaseMaterialCategory.NON_PARTY, name="函件")
        authority = SupervisingAuthority.objects.create(case=case, name="某法院")
        materials = [
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t_our, side=CaseMaterialSide.OUR),
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t_opp, side=CaseMaterialSide.OPPONENT),
            _make_material(case, category=CaseMaterialCategory.NON_PARTY, type_obj=t_non_party, authority=authority),
        ]

        CaseMaterialBindingWorkflow()._ensure_group_orders(case.id, materials)

        all_orders = {
            (o.category, o.side, o.supervising_authority_id, o.type_id): o.sort_index
            for o in CaseMaterialGroupOrder.objects.filter(case=case)
        }
        assert all_orders[(CaseMaterialCategory.PARTY, CaseMaterialSide.OUR, None, t_our.id)] == 0
        assert all_orders[(CaseMaterialCategory.PARTY, CaseMaterialSide.OPPONENT, None, t_opp.id)] == 0
        assert all_orders[(CaseMaterialCategory.NON_PARTY, "", authority.id, t_non_party.id)] == 0

    def test_duplicate_type_in_saved_deduped(self) -> None:
        case = CaseFactory()
        t1 = CaseMaterialType.objects.create(category=CaseMaterialCategory.PARTY, name="重复类型")
        materials = [
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t1, side=CaseMaterialSide.OUR),
            _make_material(case, category=CaseMaterialCategory.PARTY, type_obj=t1, side=CaseMaterialSide.OUR),
        ]

        CaseMaterialBindingWorkflow()._ensure_group_orders(case.id, materials)

        assert CaseMaterialGroupOrder.objects.filter(case=case, type=t1).count() == 1

    def test_material_without_type_skipped(self) -> None:
        case = CaseFactory()
        material = CaseMaterial.objects.create(case=case, category=CaseMaterialCategory.PARTY, type_name="无类型材料")

        CaseMaterialBindingWorkflow()._ensure_group_orders(case.id, [material])

        assert CaseMaterialGroupOrder.objects.filter(case=case).count() == 0
