"""案件 CRUD MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_cases(
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
) -> list[dict[str, Any]]:
    """查询案件列表。可按案件类型（case_type）、状态（status）、案号（case_number）筛选。"""
    params: dict[str, Any] = {}
    if case_type:
        params["case_type"] = case_type
    if status:
        params["status"] = status
    if case_number:
        params["case_number"] = case_number
    return client.get("/cases/cases", params=params)  # type: ignore[return-value]


def search_cases(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """按关键词搜索案件，支持案件名称、当事人姓名等模糊搜索。"""
    return client.get("/cases/cases/search", params={"q": q, "limit": limit})  # type: ignore[return-value]


def get_case(case_id: int) -> dict[str, Any]:
    """获取单个案件的详细信息，包含当事人、指派律师、案号、进展日志等。"""
    return client.get(f"/cases/cases/{case_id}")  # type: ignore[return-value]


def create_case(
    name: str,
    case_type: str,
    target_amount: float | None = None,
    cause_of_action: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """创建新案件。case_type 常用值：litigation（诉讼）、non_litigation（非诉）、criminal（刑事）、advisory（顾问）。"""
    payload: dict[str, Any] = {"name": name, "case_type": case_type}
    if target_amount is not None:
        payload["target_amount"] = target_amount
    if cause_of_action:
        payload["cause_of_action"] = cause_of_action
    if status:
        payload["status"] = status
    return client.post("/cases/cases", json=payload)  # type: ignore[return-value]


def update_case(
    case_id: int,
    name: str | None = None,
    case_type: str | None = None,
    target_amount: float | None = None,
    cause_of_action: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """更新案件信息。只传需要修改的字段。"""
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if case_type is not None:
        payload["case_type"] = case_type
    if target_amount is not None:
        payload["target_amount"] = target_amount
    if cause_of_action is not None:
        payload["cause_of_action"] = cause_of_action
    if status is not None:
        payload["status"] = status
    return client.put(f"/cases/cases/{case_id}", json=payload)  # type: ignore[return-value]


def delete_case(case_id: int) -> None:
    """删除案件。此操作不可逆。"""
    client.delete(f"/cases/cases/{case_id}")


def create_full_case(
    name: str,
    case_type: str,
    parties: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    """创建完整案件（含当事人、案号等）。parties 为当事人列表；其余字段通过 extra 透传。"""
    payload: dict[str, Any] = {"name": name, "case_type": case_type, "parties": parties, **extra}
    return client.post("/cases/cases/full", json=payload)  # type: ignore[return-value]
