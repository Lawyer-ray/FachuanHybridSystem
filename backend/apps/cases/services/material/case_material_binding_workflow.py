"""Business workflow orchestration."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from collections.abc import Sequence
from typing import Any

from django.db import models, transaction

from apps.cases.models import (
    CaseLogAttachment,
    CaseMaterial,
    CaseMaterialCategory,
    CaseMaterialSide,
    CaseMaterialType,
    CaseParty,
    SupervisingAuthority,
)
from apps.core.exceptions import NotFoundError, ValidationException


class CaseMaterialBindingWorkflow:
    def __init__(self, case_service: Any | None = None) -> None:
        self._case_service = case_service

    @property
    def case_service(self) -> Any:
        if self._case_service is None:
            raise RuntimeError("CaseMaterialBindingWorkflow.case_service 未注入")
        return self._case_service

    def bind_materials(
        self,
        case_id: int,
        items: Sequence[dict[str, Any]],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseMaterial]:
        self.case_service.get_case(case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        attachment_ids = [int(x["attachment_id"]) for x in items if x.get("attachment_id") is not None]
        attachments = {
            a.id: a
            for a in CaseLogAttachment.objects.filter(log__case_id=case_id, id__in=attachment_ids).select_related("log")
        }
        missing = [aid for aid in attachment_ids if aid not in attachments]
        if missing:
            raise NotFoundError(_("部分附件不存在或不属于该案件"))
        parties_by_id = {p.id: p for p in CaseParty.objects.filter(case_id=case_id).select_related("client").all()}
        authorities_by_id = {a.id: a for a in SupervisingAuthority.objects.filter(case_id=case_id).all()}
        law_firm_id = getattr(user, "law_firm_id", None) if user else None
        type_cache: dict[str, CaseMaterialType] = {}
        saved: list[CaseMaterial] = []
        with transaction.atomic():
            for payload in items:
                att_id_raw = payload.get("attachment_id")
                att_id = int(att_id_raw) if att_id_raw is not None else 0
                category = (payload.get("category") or "").strip()
                type_id = payload.get("type_id")
                type_name = (payload.get("type_name") or "").strip()
                side = payload.get("side")
                party_ids = payload.get("party_ids") or []
                supervising_authority_id = payload.get("supervising_authority_id")
                if category not in {CaseMaterialCategory.PARTY, CaseMaterialCategory.NON_PARTY}:
                    raise ValidationException(message=_("材料大类不合法"), errors={"category": category})
                if not type_name:
                    raise ValidationException(message=_("类型名称不能为空"), errors={"type_name": "required"})
                if category == CaseMaterialCategory.PARTY:
                    if side not in {CaseMaterialSide.OUR, CaseMaterialSide.OPPONENT}:
                        raise ValidationException(message=_("当事人方向不合法"), errors={"side": side})
                    supervising_authority_id = None
                else:
                    side = None
                    if not supervising_authority_id:
                        raise ValidationException(
                            message=_("必须选择主管机关"), errors={"supervising_authority_id": "required"}
                        )
                    supervising_authority_id = int(supervising_authority_id)
                    if supervising_authority_id not in authorities_by_id:
                        raise ValidationException(
                            message=_("主管机关不属于该案件"),
                            errors={"supervising_authority_id": supervising_authority_id},
                        )
                resolved_type = self._resolve_type_cached(
                    cache=type_cache, category=category, type_id=type_id, type_name=type_name, law_firm_id=law_firm_id
                )
                material, _created = CaseMaterial.objects.update_or_create(
                    source_attachment=attachments[att_id],
                    defaults={
                        "case_id": case_id,
                        "category": category,
                        "type": resolved_type,
                        "type_name": resolved_type.name,
                        "side": side,
                        "supervising_authority_id": supervising_authority_id,
                    },
                )
                if category == CaseMaterialCategory.PARTY:
                    validated_party_ids = self._validate_party_ids(party_ids, parties_by_id, side)
                    material.parties.set(validated_party_ids)
                else:
                    material.parties.clear()
                saved.append(material)
        return saved

    def _resolve_type_cached(
        self,
        cache: dict[str, CaseMaterialType],
        *,
        category: str,
        type_id: int | None,
        type_name: str,
        law_firm_id: int | None,
    ) -> CaseMaterialType:
        cache_key = f"id:{type_id}" if type_id else f"name:{category}:{type_name}:{law_firm_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        resolved = self._resolve_type(category=category, type_id=type_id, type_name=type_name, law_firm_id=law_firm_id)
        cache[cache_key] = resolved
        return resolved

    def _resolve_type(
        self, *, category: str, type_id: int | None, type_name: str, law_firm_id: int | None
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
        t: CaseMaterialType | None = qs.first() # type: ignore
        if t is not None:
            return t
        return CaseMaterialType.objects.create(
            category=category, name=type_name, law_firm_id=law_firm_id, is_active=True
        )

    def _validate_party_ids(
        self, party_ids: Sequence[Any], parties_by_id: dict[int, CaseParty], side: str
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
            if side == CaseMaterialSide.OUR and (not is_our):
                raise ValidationException(message=_("当事人不属于我方"), errors={"party_ids": pid_int})
            if side == CaseMaterialSide.OPPONENT and is_our:
                raise ValidationException(message=_("当事人不属于对方"), errors={"party_ids": pid_int})
            validated.append(pid_int)
        return validated
