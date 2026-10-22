"""列表输出精简 —— 解决「列表接口返回整包详情」导致的上下文溢出。

## 问题

``ContractOut`` 每条内嵌 6 组关系（当事人、提醒、收款、补充协议、律师指派、
客户回款），``CaseOut`` 每条内嵌 7 组（当事人、指派、日志、案号、主管机关、
群聊、联系人）。实测：

- ``list_contracts(page_size=50)`` 单条 6.5KB / 34 字段，165 条合同 ≈ 22 万 token
- 模型根本读不完，只能从被截断的头部人工统计

根因不是「分页坏了」，而是**列表端点返回的就是详情结构**。后端已提供
``slim=true``，但只剔除了 2 个字段，剩余嵌套仍然巨大，且 MCP 从未传过。

## 方案

在 MCP 工具层做投影，而不是改后端 schema：

1. ``fields`` 参数：显式列出要的字段，返回极简结构
2. 不传 ``fields`` 时用**默认投影**（列表场景真正需要的十几个字段）
3. ``full=True`` 才返回后端原始完整结构（模型明确要详情时）

投影只删字段、不改结构，模型看得到的信息是后端返回的子集，不存在
「编造字段」的风险。
"""

from __future__ import annotations

from typing import Any

#: 合同列表默认投影：够模型做判断与汇总，不含嵌套关系数组。
CONTRACT_LIST_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "case_type",
    "case_type_label",
    "status",
    "status_label",
    "fee_mode",
    "fixed_amount",
    "risk_rate",
    "start_date",
    "end_date",
    "is_filed",
    "filing_number",
    "case_count",
    "total_received",
    "unpaid_amount",
    "primary_lawyer",
)

#: 案件列表默认投影。
CASE_LIST_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "status",
    "is_filed",
    "filing_number",
    "case_type",
    "start_date",
    "effective_date",
    "specified_date",
    "target_amount",
    "preservation_amount",
    "cause_of_action",
    "current_stage",
    "contract_id",
)


def project(
    item: dict[str, Any],
    fields: list[str] | None,
    default_fields: tuple[str, ...],
    *,
    full: bool = False,
) -> dict[str, Any]:
    """按 ``fields``（或默认字段集）裁剪一条记录。

    Args:
        item: 后端返回的单条记录。
        fields: 调用方显式指定的字段名；``None`` 表示用默认投影。
        default_fields: 默认字段集。
        full: True 时原样返回（模型明确要看全部字段）。

    Returns:
        裁剪后的 dict；请求的字段若后端不存在，值为 ``None`` 且附带
        ``_missing_fields`` 提示，避免模型误以为「字段为空」。
    """
    if full:
        return item

    wanted = list(fields) if fields else list(default_fields)
    projected = {key: item.get(key) for key in wanted}
    missing = [key for key in wanted if key not in item]
    if missing:
        projected["_missing_fields"] = missing
    return projected


def project_page(
    payload: dict[str, Any],
    fields: list[str] | None,
    default_fields: tuple[str, ...],
    *,
    full: bool = False,
) -> dict[str, Any]:
    """对分页结构 ``{items, total, ...}`` 的每一项做投影，保留分页元信息。"""
    if full or not isinstance(payload.get("items"), list):
        return payload
    projected = dict(payload)
    projected["items"] = [project(item, fields, default_fields) for item in payload["items"] if isinstance(item, dict)]
    projected["projected"] = True
    if fields:
        projected["fields"] = list(fields)
    else:
        projected["default_fields"] = list(default_fields)
    return projected


def project_list(
    items: list[Any],
    fields: list[str] | None,
    default_fields: tuple[str, ...],
    *,
    full: bool = False,
) -> list[Any]:
    """对裸数组的每一项做投影。"""
    if full:
        return items
    return [project(item, fields, default_fields) if isinstance(item, dict) else item for item in items]
