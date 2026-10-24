"""案件 CRUD MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result
from mcp_server.tools.core.projection import CASE_LIST_FIELDS, project_list


def list_cases(
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
    contract_id: int | None = None,
    limit: int = 100,
    fields: list[str] | None = None,
    full: bool = False,
) -> dict[str, Any]:
    """查询案件列表。

    默认返回**精简投影**（id/名称/状态/案号/类型/日期/金额/案由等 14 个字段），
    不含当事人、指派、日志、案号列表等嵌套数组——``CaseOut`` 每条内嵌 7 组
    关系，案件多时一次序列化会撑爆上下文。

    Args:
        case_type: 按案件类型筛选（civil 民事 / administrative 行政 /
            criminal 刑事 / execution 申请执行 / bankruptcy 破产）。
        status: 按状态筛选（如 active / closed）。
        case_number: 按案号精确/模糊查询。
        contract_id: 按所属合同筛选。
        limit: 最多返回条数，默认 100，上限 2000。
        fields: 只返回这些字段；不传用默认投影。
        full: True 时返回后端完整结构（含当事人、日志等全部嵌套）。

    Returns:
        案件数组（已投影）。注意本端点**不返回总数**，需要计数请看
        ``get_dashboard_stats`` 或对结果取长度。
    """
    params: dict[str, Any] = {}
    if case_type:
        params["case_type"] = case_type
    if status:
        params["status"] = status
    if case_number:
        params["case_number"] = case_number
    if contract_id is not None:
        params["contract_id"] = contract_id
    if limit:
        params["limit"] = max(1, min(limit, 2000))
    rows: list[Any] = client.get("/cases/cases", params=params)
    return list_result(project_list(rows, fields, CASE_LIST_FIELDS, full=full))


def search_cases(q: str, limit: int = 10) -> dict[str, Any]:
    """按关键词搜索案件，支持案件名称、当事人姓名等模糊搜索。"""
    return list_result(client.get("/cases/cases/search", params={"q": q, "limit": limit}))


def get_case(case_id: int) -> dict[str, Any]:
    """获取单个案件的详细信息，包含当事人、指派律师、案号、进展日志等。"""
    return client.get(f"/cases/cases/{case_id}")  # type: ignore[no-any-return]


def create_case(
    name: str,
    case_type: str,
    target_amount: float | None = None,
    cause_of_action: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """创建新案件。case_type 取值：civil（民事）/ administrative（行政）/
    criminal（刑事）/ execution（申请执行）/ bankruptcy（破产）。"""
    payload: dict[str, Any] = {"name": name, "case_type": case_type}
    if target_amount is not None:
        payload["target_amount"] = target_amount
    if cause_of_action:
        payload["cause_of_action"] = cause_of_action
    if status:
        payload["status"] = status
    return client.post("/cases/cases", json=payload)  # type: ignore[no-any-return]


def update_case(
    case_id: int,
    name: str | None = None,
    case_type: str | None = None,
    target_amount: float | None = None,
    cause_of_action: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """更新案件档案的可编辑字段（名称/状态/类型/日期/金额/案由等）。

    只传需要修改的字段;改动立即生效并进入审计日志。金额类字段
    （amount 等）触发审批。案件归属不变。"""
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
    return client.put(f"/cases/cases/{case_id}", json=payload)  # type: ignore[no-any-return]


def delete_case(case_id: int) -> None:
    """删除整个案件档案——硬删除,不可恢复。

    级联删除案件下的当事人、案号、指派、进展日志、访问授权等全部
    关联记录。删除前确认没有关联合同/文书仍在引用。高危操作,需人工审批。"""
    client.delete(f"/cases/cases/{case_id}")


def create_full_case(
    case: dict[str, Any],
    parties: list[dict[str, Any]] | None = None,
    assignments: list[dict[str, Any]] | None = None,
    case_numbers: list[dict[str, Any]] | None = None,
    supervising_authorities: list[dict[str, Any]] | None = None,
    logs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """创建完整案件（一案落库 + 当事人/案号/指派等一次到位）。

    Args:
        case: 案件主体字段。必填 ``name``；常用 ``case_type``
            （civil / administrative / criminal / execution / bankruptcy）、
            ``target_amount``、``cause_of_action``、``status``
            （active / closed）等。
        parties: 当事人列表（每项含 name / party_type 等字段）。
        assignments: 指派律师列表。
        case_numbers: 案号列表。
        supervising_authorities: 主管机关列表。
        logs: 进展日志列表。
    """
    payload: dict[str, Any] = {"case": case}
    if parties:
        payload["parties"] = parties
    if assignments:
        payload["assignments"] = assignments
    if case_numbers:
        payload["case_numbers"] = case_numbers
    if supervising_authorities:
        payload["supervising_authorities"] = supervising_authorities
    if logs:
        payload["logs"] = logs
    return client.post("/cases/cases/full", json=payload)  # type: ignore[no-any-return]
