"""案件 CRUD MCP tools"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from mcp_server.client import client
from mcp_server.tool_shaping import list_result
from mcp_server.tools.core.projection import CASE_LIST_FIELDS, project_list

#: 枚举取值与 apps.core.models.enums 的 TextChoices 同源(测试逐值对账,
#: 后端加值不同步会红灯)——schema 级 enum 让模型在选值时就看到合法集,
#: 而不是 filter 静默空列表。
_SimpleCaseTypeL = Literal["civil", "administrative", "criminal", "execution", "bankruptcy"]
_CaseStatusL = Literal["active", "closed"]


def list_cases(
    case_type: Annotated[
        _SimpleCaseTypeL | None,
        Field(description="按案件类型筛选:civil 民事 / administrative 行政 / criminal 刑事 / execution 申请执行 / bankruptcy 破产"),
    ] = None,
    status: Annotated[_CaseStatusL | None, Field(description="按状态筛选(active 在办 / closed 已结案)")] = None,
    case_number: Annotated[str | None, Field(description="按案号精确/模糊查询")] = None,
    contract_id: Annotated[int | None, Field(description="按所属合同筛选")] = None,
    limit: Annotated[int, Field(description="最多返回条数(默认 40,上限 2000;投影后约 0.4KB/条,默认调用应留在 20KB 截断线内)", ge=1, le=2000)] = 40,
    offset: Annotated[int, Field(description="跳过前 offset 条再取——truncated=true 时续取翻页用(第 N 页传 offset=N×limit)", ge=0)] = 0,
    fields: Annotated[list[str] | None, Field(description="只返回这些字段;不传用默认 14 字段精简投影")] = None,
    full: Annotated[bool, Field(description="True 时返回后端完整结构(含当事人、日志等全部嵌套,体量大)")] = False,
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
        limit: 最多返回条数，默认 40（投影后约 0.4KB/条,40 条 ≈ 17KB——
            pi 对工具输出 20KB 起腰斩,默认调用应留在截断线内）,上限 2000。
        offset: 跳过前 offset 条再取——truncated=true 时续取翻页用
            (第 N 页传 offset=N×limit)。
        fields: 只返回这些字段；不传用默认投影。
        full: True 时返回后端完整结构（含当事人、日志等全部嵌套）。

    Returns:
        ``{total, items}`` 信封（items 已投影;total=本次返回条数,后端端点
        本身不返回总数,需要全量计数请看 ``get_dashboard_stats``）。
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
        # limit+1 探测:多取一条判断「还有更多」;truncated=True 时 total 是下界
        params["limit"] = max(1, min(limit + 1, 2000))
    params["offset"] = max(0, offset)
    rows: list[Any] = client.get("/cases/cases", params=params)
    return list_result(project_list(rows, fields, CASE_LIST_FIELDS, full=full), limit=limit)


def search_cases(
    q: Annotated[str, Field(description="搜索关键词(案件名/当事人姓名/案号)")],
    limit: Annotated[int, Field(description="最多返回条数(默认 10)", ge=1)] = 10,
    offset: Annotated[int, Field(description="跳过前 offset 条再取——续取翻页用", ge=0)] = 0,
    fields: Annotated[list[str] | None, Field(description="只返回这些字段;不传用默认投影")] = None,
) -> dict[str, Any]:
    """按关键词搜索案件，支持案件名称、当事人姓名等模糊搜索。

    搜索端点返回**未投影的全量嵌套 DTO**（实测 ~12.5KB/条——含当事人/日志
    等 7 组关系,10 条就能 137KB）,这里与 ``list_cases`` 同款套精简投影
    （14 字段）;要完整结构请拿 id 调 ``get_case``。
    limit+1 探测:truncated=True 时 total 是下界,用 offset 续取。

    Args:
        q: 搜索关键词(案件名/当事人姓名/案号)。
        limit: 最多返回条数(默认 10)。
        offset: 跳过前 offset 条再取——续取翻页用。
        fields: 只返回这些字段;不传用默认投影。
    """
    rows = client.get("/cases/cases/search", params={"q": q, "limit": limit + 1, "offset": offset})
    return list_result(project_list(rows, fields, CASE_LIST_FIELDS, full=False), limit=limit)


def get_case(case_id: int, include_logs: bool = False) -> dict[str, Any]:
    """获取单个案件的详细信息，包含当事人、指派律师、案号、监督机关等。

    进展日志数组默认**不包含**——它是响应的大头（实测 23 条日志占 45.8KB
    响应中的 36.3KB,中文转义后 ~1.8KB/条,默认全带会超 pi 20KB 截断线）;
    看日志请用 ``list_case_logs``（可控条数）。确要一次全带传
    ``include_logs=True``。
    """
    data: dict[str, Any] = client.get(f"/cases/cases/{case_id}")
    if not include_logs:
        data.pop("logs", None)
    return data


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
    case_id: Annotated[int, Field(description="案件 ID", ge=1)],
    name: Annotated[str | None, Field(description="案件名称(不改不传)")] = None,
    case_type: Annotated[str | None, Field(description="案件类型(自由文本,如 民事诉讼/刑事诉讼;不改不传)")] = None,
    target_amount: Annotated[float | None, Field(description="标的额(元)", ge=0)] = None,
    cause_of_action: Annotated[str | None, Field(description="案由(如 买卖合同纠纷)")] = None,
    status: Annotated[_CaseStatusL | None, Field(description="active 在办/closed 已结(不改不传)")] = None,
) -> dict[str, Any]:
    """更新案件档案的可编辑字段（名称/状态/类型/日期/金额/案由等）。

    只传需要修改的字段;改动立即生效并进入审计日志。金额类字段
    （amount 等）触发审批。案件归属不变。

    Args:
        case_id: 案件 ID。
        name: 案件名称。
        case_type: 案件类型——civil/administrative/criminal/execution/bankruptcy。
        target_amount: 标的额(元,数字)。
        cause_of_action: 案由。
        status: 案件状态。
    """
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
