"""Business logic services."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import (
    CaseLogAttachment,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialGroupOrder,
    CaseMaterialSide,
    CaseMaterialType,
    CaseParty,
)
from apps.core.exceptions import NotFoundError, ValidationException

if TYPE_CHECKING:
    from apps.cases.services.case.case_query_service import CaseQueryService

logger = logging.getLogger(__name__)


class CaseMaterialService:
    def __init__(
        self,
        case_service: CaseQueryService | None = None,
        query_service: Any | None = None,
        binding_workflow: Any | None = None,
    ) -> None:
        if case_service is None:
            raise RuntimeError("CaseMaterialService.case_service 未注入")
        self._case_service = case_service
        self._query_service = query_service
        self._binding_workflow = binding_workflow

    @property
    def query_service(self) -> Any:
        if self._query_service is None:
            from .case_material_query_service import CaseMaterialQueryService

            self._query_service = CaseMaterialQueryService(case_service=self._case_service)
        return self._query_service

    @property
    def binding_workflow(self) -> Any:
        if self._binding_workflow is None:
            from .case_material_binding_workflow import CaseMaterialBindingWorkflow

            self._binding_workflow = CaseMaterialBindingWorkflow(case_service=self._case_service)
        return self._binding_workflow

    def list_bind_candidates(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self.query_service.list_bind_candidates(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def bind_materials(
        self,
        case_id: int,
        items: Sequence[dict[str, Any]],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseMaterial]:
        return cast(
            list[CaseMaterial],
            self.binding_workflow.bind_materials(
                case_id=case_id,
                items=items,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def get_case_materials_view(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.query_service.get_case_materials_view(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def get_used_type_ids(self, case_id: int) -> set[int]:
        """获取案件已使用的材料类型 ID 集合。"""
        return cast(
            set[int],
            self.query_service.get_used_type_ids(case_id=case_id),
        )

    def get_material_types_by_category(
        self,
        category: str,
        law_firm_id: int | None,
        used_type_ids: set[int],
    ) -> list[dict[str, Any]]:
        """按分类获取可用的材料类型列表。"""
        return cast(
            list[dict[str, Any]],
            self.query_service.get_material_types_by_category(
                category=category,
                law_firm_id=law_firm_id,
                used_type_ids=used_type_ids,
            ),
        )

    def save_group_order(
        self,
        case_id: int,
        category: str,
        ordered_type_ids: Sequence[int],
        side: str | None = None,
        supervising_authority_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        self._case_service.get_case(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

        category = (category or "").strip()
        if category not in {CaseMaterialCategory.PARTY, CaseMaterialCategory.NON_PARTY}:
            raise ValidationException(message=_("材料大类不合法"), errors={"category": category})

        if category == CaseMaterialCategory.PARTY:
            if side not in {CaseMaterialSide.OUR, CaseMaterialSide.OPPONENT}:
                raise ValidationException(message=_("当事人方向不合法"), errors={"side": side})
            supervising_authority_id = None
        else:
            side = None
            if not supervising_authority_id:
                raise ValidationException(
                    message=_("必须选择主管机关"),
                    errors={"supervising_authority_id": "required"},
                )

        types = {
            t.id: t
            for t in CaseMaterialType.objects.filter(id__in=list(ordered_type_ids), category=category, is_active=True)
        }
        missing = [tid for tid in ordered_type_ids if tid not in types]
        if missing:
            raise ValidationException(message=_("包含无效的材料类型"), errors={"type_ids": missing})

        with transaction.atomic():
            for idx, type_id in enumerate(ordered_type_ids):
                CaseMaterialGroupOrder.objects.update_or_create(
                    case_id=case_id,
                    category=category,
                    side=side,
                    supervising_authority_id=supervising_authority_id,
                    type_id=type_id,
                    defaults={"sort_index": idx},
                )

    def _resolve_type(
        self,
        category: str,
        type_id: int | None,
        type_name: str,
        law_firm_id: int | None,
    ) -> CaseMaterialType:
        if type_id:
            try:
                t = CaseMaterialType.objects.get(id=int(type_id), category=category, is_active=True)
            except CaseMaterialType.DoesNotExist:
                raise ValidationException(message=_("材料类型不存在"), errors={"type_id": type_id}) from None
            return t

        qs = CaseMaterialType.objects.filter(category=category, name=type_name, is_active=True).order_by(
            models.Case(
                models.When(law_firm_id=law_firm_id, then=0),
                models.When(law_firm_id=None, then=1),
                default=2,
                output_field=models.IntegerField(),
            )
        )
        t = qs.first()  # type: ignore
        if t:
            return t

        return CaseMaterialType.objects.create(
            category=category,
            name=type_name,
            law_firm_id=law_firm_id,
            is_active=True,
        )

    def _validate_party_ids(
        self,
        party_ids: Sequence[Any],
        parties_by_id: dict[int, CaseParty],
        side: str,
    ) -> list[int]:
        validated: list[int] = []
        for pid in party_ids:
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                continue
            party = parties_by_id.get(pid_int)
            if not party:
                raise ValidationException(message=_("包含无效当事人"), errors={"party_ids": pid_int})
            is_our = bool(getattr(getattr(party, "client", None), "is_our_client", False))
            if side == CaseMaterialSide.OUR and not is_our:
                raise ValidationException(message=_("当事人不属于我方"), errors={"party_ids": pid_int})
            if side == CaseMaterialSide.OPPONENT and is_our:
                raise ValidationException(message=_("当事人不属于对方"), errors={"party_ids": pid_int})
            validated.append(pid_int)
        return validated

    def _build_group_order_map(self, rows: Sequence[CaseMaterialGroupOrder]) -> dict[tuple[str, str, int], list[int]]:
        order_map: dict[tuple[str, str, int], list[int]] = {}
        for row in rows:
            key = (
                row.category,
                row.side or "",
                row.supervising_authority_id or 0,
            )
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
        remaining = dict[str, Any](groups_by_type_id)  # type: ignore

        for tid in ordered_ids:
            g = remaining.pop(tid, None)  # type: ignore
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

    def replace_material_file(
        self,
        case_id: int,
        material_id: int,
        new_attachment_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """替换材料对应的附件文件。

        将 CaseMaterial 的 source_attachment 从旧附件切换到新附件，
        同时旧附件仍保留在日志中（不删除）。
        """
        self._case_service.get_case(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

        try:
            material = CaseMaterial.objects.select_related("source_attachment").get(id=material_id, case_id=case_id)
        except CaseMaterial.DoesNotExist:
            raise NotFoundError(_("材料不存在")) from None

        old_attachment_id = material.source_attachment_id

        if old_attachment_id == new_attachment_id:
            raise ValidationException(message=_("新附件与当前附件相同"), errors={"new_attachment_id": new_attachment_id})

        try:
            new_attachment = CaseLogAttachment.objects.select_related("log").get(
                id=new_attachment_id, log__case_id=case_id
            )
        except CaseLogAttachment.DoesNotExist:
            raise NotFoundError(_("新附件不存在或不属于该案件")) from None

        # 检查新附件是否已被其他材料绑定
        existing = CaseMaterial.objects.filter(source_attachment_id=new_attachment_id).first()
        if existing and existing.id != material_id:
            raise ValidationException(
                message=_("新附件已被其他材料绑定"), errors={"new_attachment_id": new_attachment_id}
            )

        old_attachment_id_val = material.source_attachment_id
        material.source_attachment = new_attachment
        material.save(update_fields=["source_attachment"])

        logger.info(
            "材料文件已替换: material_id=%s, old_attachment_id=%s, new_attachment_id=%s",
            material_id,
            old_attachment_id_val,
            new_attachment_id,
        )

        return {
            "material_id": material.id,
            "old_attachment_id": old_attachment_id_val,
            "new_attachment_id": new_attachment_id,
        }

    def rename_group(
        self,
        case_id: int,
        type_id: int,
        new_type_name: str,
        update_global: bool = False,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """重命名材料分组。

        默认仅更新本案件下所有 CaseMaterial.type_name；
        如果 update_global=True，同时更新 CaseMaterialType.name（影响所有案件）。
        """
        self._case_service.get_case(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

        new_type_name = new_type_name.strip()
        if not new_type_name:
            raise ValidationException(message=_("类型名称不能为空"), errors={"new_type_name": "required"})

        try:
            material_type = CaseMaterialType.objects.get(id=type_id)
        except CaseMaterialType.DoesNotExist:
            raise NotFoundError(_("材料类型不存在")) from None

        old_type_name = material_type.name

        if old_type_name == new_type_name:
            return {"type_id": type_id, "old_type_name": old_type_name, "new_type_name": new_type_name}

        with transaction.atomic():
            # 更新本案件下该分组的所有材料
            updated_count = CaseMaterial.objects.filter(case_id=case_id, type_id=type_id).update(
                type_name=new_type_name
            )

            if update_global:
                # 更新全局类型名称
                material_type.name = new_type_name
                material_type.save(update_fields=["name"])
                # 同时更新所有使用该类型的材料 type_name
                CaseMaterial.objects.filter(type_id=type_id).exclude(type_name=new_type_name).update(
                    type_name=new_type_name
                )

        logger.info(
            "材料分组已重命名: type_id=%s, old_name=%s, new_name=%s, update_global=%s, updated_count=%s",
            type_id,
            old_type_name,
            new_type_name,
            update_global,
            updated_count,
        )

        return {"type_id": type_id, "old_type_name": old_type_name, "new_type_name": new_type_name}
