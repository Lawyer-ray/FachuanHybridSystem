"""Business logic services."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.db import models
from django.db.models import Prefetch

from apps.cases.models import (
    CaseLogAttachment,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialGroupOrder,
    CaseMaterialSide,
    CaseMaterialType,
    CaseParty,
)


class CaseMaterialQueryService:
    def __init__(self, case_service: Any | None = None) -> None:
        self._case_service = case_service

    @property
    def case_service(self) -> Any:
        if self._case_service is None:
            raise RuntimeError("CaseMaterialQueryService.case_service 未注入")
        return self._case_service

    def list_bind_candidates(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[dict[str, Any]]:
        self.case_service.get_case(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        qs = (
            CaseLogAttachment.objects.filter(log__case_id=case_id)
            .select_related("log", "log__actor")
            .prefetch_related(
                Prefetch(
                    "bound_material",
                    queryset=CaseMaterial.objects.select_related("type", "supervising_authority").prefetch_related(
                        Prefetch("parties", queryset=CaseParty.objects.select_related("client"))
                    ),
                )
            )
            .order_by("uploaded_at", "id")
        )
        results: list[dict[str, Any]] = []
        for att in qs:
            material = getattr(att, "bound_material", None)
            material_payload: dict[str, Any] | None = None
            if material:
                material_payload = {
                    "id": material.id,
                    "category": material.category,
                    "type_id": material.type_id,
                    "type_name": material.type_name,
                    "side": material.side,
                    "party_ids": list(material.parties.values_list("id", flat=True)),
                    "supervising_authority_id": material.supervising_authority_id,
                }
            results.append(
                {
                    "attachment_id": att.id,
                    "file_name": (getattr(att.file, "name", "") or "").rsplit("/", 1)[-1],
                    "file_url": getattr(att.file, "url", "") or "",
                    "uploaded_at": att.uploaded_at,
                    "log_id": att.log_id,
                    "log_created_at": getattr(att.log, "created_at", None),
                    "actor_name": getattr(getattr(att.log, "actor", None), "username", "") or "",
                    "material": material_payload,
                }
            )
        return results

    def get_case_materials_view(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        case = self.case_service.get_case(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        materials = (
            CaseMaterial.objects.filter(case_id=case_id)
            .select_related(
                "type",
                "source_attachment",
                "source_attachment__log",
                "source_attachment__log__actor",
                "supervising_authority",
            )
            .prefetch_related(Prefetch("parties", queryset=CaseParty.objects.select_related("client")))
            .order_by("created_at", "id")
        )
        group_orders_qs = (
            CaseMaterialGroupOrder.objects.filter(case_id=case_id)
            .select_related("type", "supervising_authority")
            .order_by("sort_index", "id")
        )
        order_map = self._build_group_order_map(list(group_orders_qs))
        our_statuses = []
        opp_statuses = []
        for p in case.parties.select_related("client").all():
            if not p.legal_status:
                continue
            label = p.get_legal_status_display()
            if p.client and getattr(p.client, "is_our_client", False):
                our_statuses.append(label)
            else:
                opp_statuses.append(label)
        party_payload = {
            "our": {"legal_statuses": sorted(set(our_statuses)), "groups": []},
            "opponent": {"legal_statuses": sorted(set(opp_statuses)), "groups": []},
        }
        non_party_payload: list[dict[str, Any]] = []
        party_groups: dict[str, dict[int, dict[str, Any]]] = {CaseMaterialSide.OUR: {}, CaseMaterialSide.OPPONENT: {}}
        non_party_groups: dict[int, dict[int, dict[str, Any]]] = {}
        for m in materials:
            if m.category == CaseMaterialCategory.PARTY:
                side = m.side or CaseMaterialSide.OUR
                type_id = m.type_id or 0
                g = party_groups.setdefault(side, {}).get(type_id)
                if not g:
                    party_groups[side][type_id] = {"type_id": m.type_id, "type_name": m.type_name, "items": []}
                    g = party_groups[side][type_id]
                g["items"].append(self._material_item_payload(m))
            else:
                auth_id = m.supervising_authority_id
                if not auth_id:
                    continue
                type_id = m.type_id or 0
                bucket = non_party_groups.setdefault(auth_id, {})
                g = bucket.get(type_id)
                if not g:
                    bucket[type_id] = {"type_id": m.type_id, "type_name": m.type_name, "items": []}
                    g = bucket[type_id]
                g["items"].append(self._material_item_payload(m))
        party_payload["our"]["groups"] = self._sorted_groups(
            CaseMaterialCategory.PARTY, CaseMaterialSide.OUR, None, party_groups[CaseMaterialSide.OUR], order_map
        )
        party_payload["opponent"]["groups"] = self._sorted_groups(
            CaseMaterialCategory.PARTY,
            CaseMaterialSide.OPPONENT,
            None,
            party_groups[CaseMaterialSide.OPPONENT],
            order_map,
        )
        authorities = list(case.supervising_authorities.all())
        for auth in authorities:
            groups = non_party_groups.get(auth.id, {})
            non_party_payload.append(
                {
                    "supervising_authority_id": auth.id,
                    "title": str(auth),
                    "groups": self._sorted_groups(CaseMaterialCategory.NON_PARTY, None, auth.id, groups, order_map),
                }
            )
        return {"case_id": case.id, "party": party_payload, "non_party": non_party_payload}

    def get_used_type_ids(self, case_id: int) -> set[int]:
        """获取案件已使用的材料类型 ID 集合。"""
        return set(
            CaseMaterial.objects.filter(case_id=case_id, type_id__isnull=False).values_list("type_id", flat=True)
        )

    def get_material_types_by_category(
        self,
        category: str,
        law_firm_id: int | None,
        used_type_ids: set[int],
    ) -> list[dict[str, Any]]:
        """按分类获取可用的材料类型列表。"""
        qs = CaseMaterialType.objects.filter(category=category, is_active=True).filter(
            models.Q(law_firm_id=law_firm_id) | models.Q(law_firm_id__isnull=True) | models.Q(id__in=used_type_ids)
        )
        return list(qs.order_by("name").values("id", "name", "law_firm_id"))  # type: ignore[arg-type]

    def _build_group_order_map(self, rows: Sequence[CaseMaterialGroupOrder]) -> dict[tuple[str, str, int], list[int]]:
        order_map: dict[tuple[str, str, int], list[int]] = {}
        for row in rows:
            key = (row.category, row.side or "", row.supervising_authority_id or 0)
            order_map.setdefault(key, []).append(row.type_id)
        return order_map

    def _sorted_groups(
        self,
        category: str,
        side: str | None,
        supervising_authority_id: int | None,
        groups_by_type_id: dict[int, dict[str, Any]],
        order_map: dict[tuple[str, str, int], list[int]],
    ) -> list[dict[str, Any]]:
        key = (category, side or "", supervising_authority_id or 0)
        ordered_ids = order_map.get(key, [])
        ordered: list[dict[str, Any]] = []
        remaining: dict[int, dict[str, Any]] = dict(groups_by_type_id)
        for tid in ordered_ids:
            g = remaining.pop(tid, None)
            if g:
                ordered.append(g)
        tail = list(remaining.values())
        tail.sort(key=lambda x: x.get("type_name") or "")
        ordered.extend(tail)
        return ordered

    def _material_item_payload(self, m: CaseMaterial) -> dict[str, Any]:
        att = m.source_attachment
        file_name = getattr(getattr(att, "file", None), "name", "") if att else ""
        url = getattr(getattr(att, "file", None), "url", "") if att else ""
        uploaded_at = getattr(att, "uploaded_at", None)
        party_labels = []
        for p in m.parties.all():
            if p.client and p.client.name:
                party_labels.append(p.client.name)
        return {
            "material_id": m.id,
            "attachment_id": m.source_attachment_id,
            "file_name": (file_name or "").rsplit("/", 1)[-1],
            "file_url": url or "",
            "uploaded_at": uploaded_at,
            "party_labels": party_labels,
        }
