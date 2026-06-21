"""工作人员联系方式服务."""

from __future__ import annotations

import logging
import operator
from functools import reduce
from typing import Any, cast

from django.db import transaction
from django.db.models import Count, Q, QuerySet

from apps.contacts.models import CaseContact
from apps.contacts.schemas.contact_schemas import CaseContactUpdate
from apps.core.exceptions import NotFoundError
from apps.core.security import DjangoPermsMixin

logger = logging.getLogger("apps.contacts")


class CaseContactService(DjangoPermsMixin):
    """案件工作人员联系方式服务"""

    def list_contacts(
        self,
        case_id: int | None = None,
        stage: str | None = None,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[CaseContact]:
        self.ensure_admin(user, perm_open_access=perm_open_access)

        qs = CaseContact.objects.select_related("authority").order_by("-id")
        if case_id:
            qs = qs.filter(case_id=case_id)
        if stage:
            qs = qs.filter(stage=stage)
        return qs

    def get_contact(
        self,
        contact_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> CaseContact:
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            return CaseContact.objects.select_related("authority").get(id=contact_id)
        except CaseContact.DoesNotExist:
            raise NotFoundError(
                message="工作人员不存在",
                code="CONTACT_NOT_FOUND",
                errors={"contact_id": f"ID 为 {contact_id} 的工作人员不存在"},
            ) from None

    @transaction.atomic
    def create_contact(
        self,
        case_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> CaseContact:  # pragma: no cover
        self.ensure_admin(user, perm_open_access=perm_open_access)

        contact = CaseContact.objects.create(case_id=case_id, **data)

        logger.info(
            "创建工作人员成功",
            extra={
                "action": "create_contact",
                "contact_id": contact.id,
                "case_id": case_id,
            },
        )
        return contact

    @transaction.atomic
    def update_contact(
        self,
        contact_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> CaseContact:  # pragma: no cover
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            contact = CaseContact.objects.get(id=contact_id)
        except CaseContact.DoesNotExist:
            raise NotFoundError(
                message="工作人员不存在",
                code="CONTACT_NOT_FOUND",
                errors={"contact_id": f"ID 为 {contact_id} 的工作人员不存在"},
            ) from None

        allowed_keys = CaseContactUpdate.model_fields.keys()
        for key, value in data.items():
            if key in allowed_keys:
                setattr(contact, key, value)
        contact.save()

        logger.info(
            "更新工作人员成功",
            extra={"action": "update_contact", "contact_id": contact_id},
        )
        return contact

    @transaction.atomic
    def delete_contact(
        self,
        contact_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            contact = CaseContact.objects.get(id=contact_id)
        except CaseContact.DoesNotExist:
            raise NotFoundError(
                message="工作人员不存在",
                code="CONTACT_NOT_FOUND",
                errors={"contact_id": f"ID 为 {contact_id} 的工作人员不存在"},
            ) from None

        contact.delete()

        logger.info(
            "删除工作人员成功",
            extra={"action": "delete_contact", "contact_id": contact_id},
        )
        return {"success": True}

    def search_contacts_public(
        self,
        q: str | None = None,
        court: str | None = None,
        role: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """跨案件搜索工作人员（公共接口，无需认证）"""
        qs = CaseContact.objects.select_related("authority")

        if q:
            qs = qs.filter(name__icontains=q)
        if court:
            qs = qs.filter(authority__name__icontains=court)
        if role:
            qs = qs.filter(role=role)

        grouped: list[dict[str, Any]] = cast(
            list[dict[str, Any]],
            list(
                qs.values("authority__name", "name", "role")
                .annotate(occurrence_count=Count("id"))
                .order_by("-occurrence_count")[:limit]
            ),
        )

        if not grouped:
            return []

        # Build a single Q filter covering all (name, role, authority__name) combos
        combo_q = reduce(
            operator.or_,
            [
                Q(name=r["name"], role=r["role"], authority__name=r["authority__name"])
                for r in grouped
            ],
        )

        # Batch query 1: collect all case_ids per group
        all_contacts = (
            CaseContact.objects.filter(combo_q)
            .values("name", "role", "authority__name", "case_id")
            .distinct()
        )
        case_id_map: dict[tuple[str, str, str], list[int]] = {}
        for cc in all_contacts:
            key: tuple[str, str, str] = (
                cc["name"],
                cc["role"],
                cc["authority__name"] or "",
            )
            case_id_map.setdefault(key, []).append(cc["case_id"])

        # Batch query 2: fetch latest contact per group (one query, keep first per group)
        latest_qs = (
            CaseContact.objects.filter(combo_q)
            .select_related("authority")
            .order_by("name", "role", "authority__name", "-updated_at")
        )
        latest_map: dict[tuple[str, str, str], CaseContact] = {}
        for contact in latest_qs:
            auth_name = contact.authority.name if contact.authority else ""
            key = (contact.name, contact.role, auth_name)
            if key not in latest_map:
                latest_map[key] = contact

        # Assemble final results
        results: list[dict[str, Any]] = []
        for row in grouped:
            key = (row["name"], row["role"], row["authority__name"] or "")
            latest = latest_map.get(key)
            role_display = latest.get_role_display() if latest is not None else None
            phone = latest.phone if latest is not None else None
            address = latest.address if latest is not None else None
            results.append(
                {
                    "authority_name": row["authority__name"],
                    "name": row["name"],
                    "role": row["role"],
                    "role_display": role_display,
                    "phone": phone,
                    "address": address,
                    "occurrence_count": row["occurrence_count"],
                    "case_ids": case_id_map.get(key, []),
                }
            )

        return results
