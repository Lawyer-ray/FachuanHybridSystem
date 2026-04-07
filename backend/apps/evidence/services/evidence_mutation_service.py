"""Business logic services."""

from __future__ import annotations

import contextlib
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException
from apps.core.exceptions.error_catalog import case_not_found


class EvidenceMutationService:
    @transaction.atomic
    def create_evidence_list(
        self, *, case: Any, title: str, list_type: str | None = None, user: Any | None = None
    ) -> EvidenceList:
        """
        创建证据清单

        Args:
            case: 案件对象
            title: 标题(如果为空且提供了 list_type,则自动生成)
            list_type: 清单类型(可选)
            user: 创建人

        Returns:
            创建的证据清单对象
        """
        from apps.evidence.models import LIST_TYPE_ORDER, ListType

        # 如果没有提供标题但提供了 list_type,自动生成标题
        if (not title or not title.strip()) and list_type:
            title = dict(ListType.choices).get(list_type, list_type)

        if not title or not title.strip():
            raise ValidationException(
                message=_("证据清单标题不能为空"),
                code="EVIDENCE_LIST_TITLE_EMPTY",
                errors={"title": "标题不能为空"},
            )

        # 自动设置顺序
        order = LIST_TYPE_ORDER.get(ListType(list_type), 1) if list_type else 1
        if not list_type:
            # 如果没有 list_type,使用最大 order + 1
            max_order = EvidenceList.objects.filter(case_id=case.id).aggregate(max_order=Max("order"))["max_order"]
            order = (max_order or 0) + 1

        evidence_list = EvidenceList.objects.create(
            case=case,
            title=title.strip(),
            list_type=list_type or ListType.LIST_1,
            order=order,
            created_by=user,
        )

        return evidence_list

    def validate_list_type_creation(
        self, *, case_id: int, list_type: str
    ) -> tuple[bool, str | None, EvidenceList | None]:
        required_previous_type = LIST_TYPE_PREVIOUS.get(ListType(list_type))
        if not required_previous_type:
            return True, None, None

        previous_list = EvidenceList.objects.filter(case_id=case_id, list_type=required_previous_type).first()
        if not previous_list:
            previous_label = dict(ListType.choices).get(required_previous_type, required_previous_type)
            current_label = dict(ListType.choices).get(list_type, list_type)
            return False, f"无法创建「{current_label}」:请先创建「{previous_label}」", None

        return True, None, previous_list

    def auto_link_previous_list(self, *, evidence_list: EvidenceList) -> EvidenceList | None:
        required_previous_type = LIST_TYPE_PREVIOUS.get(ListType(evidence_list.list_type))
        if not required_previous_type:
            return None

        previous_list = EvidenceList.objects.filter(
            case_id=evidence_list.case_id, list_type=required_previous_type
        ).first()
        if previous_list and evidence_list.previous_list != previous_list:
            evidence_list.previous_list = previous_list
            evidence_list.save(update_fields=["previous_list", "updated_at"])
        return previous_list

    @transaction.atomic
    def update_evidence_list(self, *, evidence_list: EvidenceList, title: str | None = None) -> EvidenceList:
        if title is not None:
            if not title or not title.strip():
                raise ValidationException(
                    message=_("证据清单标题不能为空"),
                    code="EVIDENCE_LIST_TITLE_EMPTY",
                    errors={"title": "标题不能为空"},
                )
            evidence_list.title = title.strip()
        evidence_list.save()
        return evidence_list

    @transaction.atomic
    def delete_evidence_list(self, *, evidence_list: EvidenceList) -> bool:
        previous_list = evidence_list.previous_list

        next_lists = list(EvidenceList.objects.filter(previous_list=evidence_list))
        if next_lists:
            from django.utils import timezone as _tz

            now = _tz.now()
            for nl in next_lists:
                nl.previous_list = previous_list
                nl.updated_at = now  # type: ignore[attr-defined]
            EvidenceList.objects.bulk_update(next_lists, ["previous_list", "updated_at"])

        if evidence_list.merged_pdf:
            with contextlib.suppress(Exception):
                evidence_list.merged_pdf.delete(save=False)

        for item in evidence_list.items.all():
            if item.file:
                with contextlib.suppress(Exception):
                    item.file.delete(save=False)

        evidence_list.delete()
        return True

    @transaction.atomic
    def create_evidence_item(self, *, evidence_list: EvidenceList, name: str, purpose: str) -> EvidenceItem:
        if not name or not name.strip():
            raise ValidationException(
                message=_("证据名称不能为空"),
                code="EVIDENCE_ITEM_NAME_EMPTY",
                errors={"name": "证据名称不能为空"},
            )

        if not purpose or not purpose.strip():
            raise ValidationException(
                message=_("证明内容不能为空"),
                code="EVIDENCE_ITEM_PURPOSE_EMPTY",
                errors={"purpose": "证明内容不能为空"},
            )

        max_order = evidence_list.items.aggregate(max_order=Max("order"))["max_order"]
        order = (max_order or 0) + 1

        return EvidenceItem.objects.create(
            evidence_list=evidence_list,
            order=order,
            name=name.strip(),
            purpose=purpose.strip(),
        )

    @transaction.atomic
    def update_evidence_item(
        self, *, item: EvidenceItem, name: str | None = None, purpose: str | None = None
    ) -> EvidenceItem:
        if name is not None:
            if not name or not name.strip():
                raise ValidationException(
                    message=_("证据名称不能为空"),
                    code="EVIDENCE_ITEM_NAME_EMPTY",
                    errors={"name": "证据名称不能为空"},
                )
            item.name = name.strip()

        if purpose is not None:
            if not purpose or not purpose.strip():
                raise ValidationException(
                    message=_("证明内容不能为空"),
                    code="EVIDENCE_ITEM_PURPOSE_EMPTY",
                    errors={"purpose": "证明内容不能为空"},
                )
            item.purpose = purpose.strip()

        item.save()
        return item

    @transaction.atomic
    def delete_evidence_item(self, *, item: EvidenceItem) -> bool:
        list_id = item.evidence_list_id

        if item.file:
            with contextlib.suppress(Exception):
                item.file.delete(save=False)

        item.delete()

        self._reorder_items_after_delete(list_id)
        return True

    def _reorder_items_after_delete(self, list_id: int) -> None:
        items = list(EvidenceItem.objects.filter(evidence_list_id=list_id).order_by("order"))
        to_update = []
        for index, item in enumerate(items, start=1):
            if item.order != index:
                item.order = index
                to_update.append(item)
        if to_update:
            EvidenceItem.objects.bulk_update(to_update, ["order"])

    @transaction.atomic
    def reorder_items(self, *, evidence_list: EvidenceList, item_ids: list[int]) -> bool:
        existing_ids = set(evidence_list.items.values_list("id", flat=True))
        provided_ids = set(item_ids)

        if existing_ids != provided_ids:
            raise ValidationException(
                message=_("提供的明细 ID 列表与实际不符"),
                code="INVALID_ITEM_IDS",
                errors={
                    "missing": list(existing_ids - provided_ids),
                    "extra": list(provided_ids - existing_ids),
                },
            )

        items_by_id = {item.id: item for item in EvidenceItem.objects.filter(id__in=item_ids)}
        to_update = []
        for index, item_id in enumerate(item_ids, start=1):
            item = items_by_id.get(item_id)
            if item and item.order != index:
                item.order = index
                to_update.append(item)
        if to_update:
            EvidenceItem.objects.bulk_update(to_update, ["order"])
        return True

    def require_case_model(self, *, case_service: Any, case_id: int) -> Any:
        case = case_service.get_case_model_internal(case_id)
        if not case:
            raise case_not_found(case_id=case_id)
        return case
