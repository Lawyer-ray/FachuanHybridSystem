"""工作人员联系方式服务."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.db import transaction
from django.db.models import Count, QuerySet

from apps.contacts.models import CaseContact
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
    ) -> CaseContact:
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
    ) -> CaseContact:
        self.ensure_admin(user, perm_open_access=perm_open_access)

        try:
            contact = CaseContact.objects.get(id=contact_id)
        except CaseContact.DoesNotExist:
            raise NotFoundError(
                message="工作人员不存在",
                code="CONTACT_NOT_FOUND",
                errors={"contact_id": f"ID 为 {contact_id} 的工作人员不存在"},
            ) from None

        for key, value in data.items():
            if hasattr(contact, key):
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

        results = cast(
            list[dict[str, Any]],
            list(
                qs.values("authority__name", "name", "role")
                .annotate(occurrence_count=Count("id"))
                .order_by("-occurrence_count")[:limit]
            ),
        )

        # 为每组结果收集 case_ids
        grouped: list[dict[str, Any]] = []
        for row in results:
            case_ids = list(
                CaseContact.objects.filter(
                    name=row["name"],
                    role=row["role"],
                    authority__name=row["authority__name"],
                )
                .values_list("case_id", flat=True)
                .distinct()
            )
            # 获取最新的联系信息
            latest = (
                CaseContact.objects.filter(
                    name=row["name"],
                    role=row["role"],
                    authority__name=row["authority__name"],
                )
                .select_related("authority")
                .order_by("-updated_at")
                .first()
            )
            grouped.append(
                {
                    "authority_name": row["authority__name"],
                    "name": row["name"],
                    "role": row["role"],
                    "role_display": latest.get_role_display() if latest else None,
                    "phone": latest.phone if latest else None,
                    "address": latest.address if latest else None,
                    "occurrence_count": row["occurrence_count"],
                    "case_ids": case_ids,
                }
            )

        return grouped
