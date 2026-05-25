"""提醒关联目标查询服务。"""

from __future__ import annotations

from typing import Any

from django.db.models import Q


def get_target_options(keyword: str = "", limit_per_group: int = 12) -> dict[str, Any]:
    """获取合同/案件/案件日志的关联选项。"""
    from apps.cases.models import Case
    from apps.cases.models.log import CaseLog
    from apps.contracts.models.contract import Contract

    keyword = keyword.strip()

    contract_qs = Contract.objects.all()
    case_qs = Case.objects.all()
    case_log_qs = CaseLog.objects.select_related("case").all()

    if keyword:
        contract_qs = contract_qs.filter(name__icontains=keyword)
        case_qs = case_qs.filter(name__icontains=keyword)
        case_log_qs = case_log_qs.filter(Q(case__name__icontains=keyword) | Q(content__icontains=keyword))

    groups: list[dict[str, object]] = []

    contract_items = [
        {"id": row["id"], "name": row["name"], "target_type": "contract", "target_type_label": "合同"}
        for row in contract_qs.order_by("-id").values("id", "name")[:limit_per_group]
    ]
    if contract_items:
        groups.append({"key": "contract", "label": "合同", "items": contract_items})

    case_items = [
        {"id": row["id"], "name": row["name"], "target_type": "case", "target_type_label": "案件"}
        for row in case_qs.order_by("-id").values("id", "name")[:limit_per_group]
    ]
    if case_items:
        groups.append({"key": "case", "label": "案件", "items": case_items})

    case_log_items: list[dict[str, object]] = []
    for item in case_log_qs.order_by("-id")[:limit_per_group]:
        preview = item.content.strip().replace("\n", " ")
        if len(preview) > 24:
            preview = f"{preview[:24]}..."
        label = f"#{item.id} {item.case.name}｜{preview or '无内容'}"
        case_log_items.append(
            {"id": item.id, "name": label, "target_type": "case_log", "target_type_label": "案件日志"}
        )
    if case_log_items:
        groups.append({"key": "case_log", "label": "案件日志", "items": case_log_items})

    merged_items: list[dict[str, object]] = []
    for group in groups:
        group_items = group.get("items", [])
        if isinstance(group_items, list):
            merged_items.extend(group_items)

    return {"items": merged_items, "groups": groups}
