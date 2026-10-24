"""合同 CRUD MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import FachuanApiError, client
from mcp_server.tool_shaping import list_result
from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project_page


def list_contracts(
    case_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    fee_mode: str | None = None,
    is_filed: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    fields: list[str] | None = None,
    full: bool = False,
) -> dict[str, Any]:
    """查询合同列表（服务端分页）。

    默认返回**精简投影**（id/名称/类型/状态/金额/主办律师等 17 个字段），
    不含当事人、提醒、收款等嵌套数组——完整详情曾经单条 6.5KB，165 条合同
    一次序列化约 22 万 token，模型读不完只能从截断处人工统计。

    Args:
        case_type: 按案件类型筛选（civil/criminal/administrative/labor/intl/special/advisor）。
        status: 按合同状态筛选（unsigned / active / archived）。
        search: 按合同名称模糊搜索。
        fee_mode: 按收费方式筛选（**大写**：``FIXED`` 固定 / ``SEMI_RISK``
            半风险 / ``FULL_RISK`` 全风险 / ``CUSTOM`` 自定义）。
        is_filed: 按是否已建档筛选。
        page: 页码，从 1 开始。
        page_size: 每页条数，默认 20，上限 200。
        fields: 只返回这些字段（如 ``["id","name","status","fixed_amount"]``）。
            不传则用默认投影；传 ``[]`` 会得到 ``_missing_fields`` 提示。
        full: True 时返回后端完整结构（含全部嵌套关系），仅在确实需要
            某个合同的当事人/收款明细时使用。

    Returns:
        ``{items, total, page, page_size, projected, ...facets}``；``items``
        按 ``fields`` 投影，``total`` 是符合条件的总数（可据此判断翻页）。
    """
    params: dict[str, Any] = {"page": max(1, page), "page_size": max(1, min(page_size, 200))}
    if case_type:
        params["case_type"] = case_type
    if status:
        params["status"] = status
    if search:
        params["search"] = search
    if fee_mode:
        params["fee_mode"] = fee_mode
    if is_filed is not None:
        params["is_filed"] = is_filed
    payload: dict[str, Any] = client.get("/contracts/contracts", params=params)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise FachuanApiError(
            f"/contracts/contracts 返回了非分页结构: {type(payload).__name__}；后端契约可能已变更，请检查"
        )
    return project_page(payload, fields, CONTRACT_LIST_FIELDS, full=full)


def get_contract(contract_id: int) -> dict[str, Any]:
    """获取单个合同的详细信息，包含关联案件、当事人、律师指派、付款记录等。"""
    return client.get(f"/contracts/contracts/{contract_id}")  # type: ignore[no-any-return]


def create_contract(
    name: str,
    case_type: str,
    lawyer_ids: list[int],
    status: str | None = None,
    fixed_amount: float | None = None,
    fee_mode: str | None = None,
    risk_rate: float | None = None,
    custom_terms: str | None = None,
    representation_stages: list[str] | None = None,
    specified_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    parties: list[dict[str, Any]] | None = None,
    payments: list[dict[str, Any]] | None = None,
    confirm_finance: bool = False,
) -> dict[str, Any]:
    """创建新合同。

    Args:
        name: 合同名称。
        case_type: 案件类型（英文键）：``civil`` 民商事 / ``criminal`` 刑事 /
            ``administrative`` 行政 / ``labor`` 劳动仲裁 / ``intl`` 商事仲裁 /
            ``special`` 专项服务 / ``advisor`` 常法顾问。
        lawyer_ids: 律师 ID 列表，**第一个为主办律师**。
        status: 合同状态（unsigned 未签约 / active 在办 / archived 已归档，
            新建一般留空默认未签约）。
        fixed_amount: 固定代理费金额。
        fee_mode: 收费方式（**大写枚举，写错值会绕过金额校验静默落库**）：
            ``FIXED`` 固定（需 fixed_amount>0）/ ``SEMI_RISK`` 半风险
            （需 fixed_amount>0 且 risk_rate>0）/ ``FULL_RISK`` 全风险
            （需 risk_rate>0）/ ``CUSTOM`` 自定义（需 custom_terms）。
        risk_rate: 风险代理比例（SEMI_RISK/FULL_RISK 时必填）。
        custom_terms: 自定义条款文本。
        representation_stages: 代理阶段列表，取**英文键**（中文会被
            ValidationException 拒绝）：``first_trial`` 一审 /
            ``second_trial`` 二审 / ``enforcement`` 执行 /
            ``labor_arbitration`` 劳动仲裁 / ``administrative_review``
            行政复议 / ``private_prosecution`` 自诉 / ``investigation``
            侦查 / ``prosecution_review`` 审查起诉 / ``retrial_first`` /
            ``retrial_second`` 重审。仅民商事/刑事/行政/劳动/商事仲裁
            类合同适用。
        specified_date / start_date / end_date: 关键日期（YYYY-MM-DD）。
        parties: 当事人列表，每项含身份与客户信息；合同当事人是后续
            立案、文书生成的数据源，缺省则合同下无当事人。
        payments: 收款记录列表，创建合同时一并写入。
        confirm_finance: 是否确认财务变动（与 payments 一起决定是否落财务）。

    Notes:
        早前签名只覆盖 6 个字段，``parties`` / ``representation_stages`` /
        ``risk_rate`` 等后端 ``ContractIn`` 支持的字段全部无法传入，
        agent 建出来的合同总是缺当事人，后续流程拿不到数据。

        **请求体形状**：该端点同时声明了 ``payload: ContractIn`` 与
        ``payments: list[ContractPaymentIn] | None``，Django Ninja 会把 body
        包成 ``{"payload": {...}, "payments": [...]}``；直接发扁平 JSON 会被
        ``Field required: body.payload`` 拒绝（422）。这里按嵌套形状发送。
        单 payload 的端点是 ``/contracts/contracts/full``。
    """
    payload: dict[str, Any] = {"name": name, "case_type": case_type, "lawyer_ids": lawyer_ids}
    if status:
        payload["status"] = status
    if fixed_amount is not None:
        payload["fixed_amount"] = fixed_amount
    if fee_mode:
        payload["fee_mode"] = fee_mode
    if risk_rate is not None:
        payload["risk_rate"] = risk_rate
    if custom_terms:
        payload["custom_terms"] = custom_terms
    if representation_stages:
        payload["representation_stages"] = representation_stages
    if specified_date:
        payload["specified_date"] = specified_date
    if start_date:
        payload["start_date"] = start_date
    if end_date:
        payload["end_date"] = end_date
    if parties:
        payload["parties"] = parties
    body: dict[str, Any] = {"payload": payload}
    if payments:
        body["payments"] = payments
    params: dict[str, Any] = {}
    if confirm_finance:
        params["confirm_finance"] = confirm_finance
    return client.post("/contracts/contracts", json=body, params=params)  # type: ignore[no-any-return]


def create_contract_with_cases(
    contract_data: dict[str, Any],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """创建合同并同时关联案件。contract_data 为合同字段（name、case_type、lawyer_ids 等）；cases 为案件列表（每项含 case_type、client_name 等）。"""
    payload: dict[str, Any] = {**contract_data, "cases": cases}
    return client.post("/contracts/contracts/full", json=payload)  # type: ignore[no-any-return]


def update_contract(
    contract_id: int,
    contract_data: dict[str, Any],
    sync_cases: bool = False,
    confirm_finance: bool = False,
) -> dict[str, Any]:
    """更新合同信息。contract_data 为需要修改的字段；sync_cases 为 True 时同步更新关联案件；confirm_finance 为 True 时确认财务变动。"""
    params: dict[str, Any] = {}
    if sync_cases:
        params["sync_cases"] = sync_cases
    if confirm_finance:
        params["confirm_finance"] = confirm_finance
    return client.put(  # type: ignore[no-any-return]
        f"/contracts/contracts/{contract_id}",
        json=contract_data,
        params=params,
    )


def delete_contract(contract_id: int) -> None:
    """删除合同——硬删除,不可恢复。

    合同下存在案件时后端会**拒绝删除**（Case 外键 PROTECT,防静默抹掉
    案件数据）,需先处理案件。删除前确认收款/归档记录已不需要。高危操作,需人工审批。"""
    client.delete(f"/contracts/contracts/{contract_id}")


def update_contract_lawyers(
    contract_id: int,
    lawyer_ids: list[int],
) -> dict[str, Any]:
    """更新合同的律师指派。lawyer_ids 第一个为主办律师。

    后端 ``response=list[ContractAssignmentOut]``，返回更新后的指派列表。
    """
    payload: dict[str, Any] = {"lawyer_ids": lawyer_ids}
    return list_result(client.put(f"/contracts/contracts/{contract_id}/lawyers", json=payload))


def get_contract_all_parties(contract_id: int) -> dict[str, Any]:
    """获取合同全部当事人信息，包含原告、被告、第三人等分组。

    后端 ``response=list[ContractPartySourceOut]``，返回扁平数组（每条带
    当事人方向字段），不是按原告/被告分组的对象。
    """
    return list_result(client.get(f"/contracts/contracts/{contract_id}/all-parties"))
