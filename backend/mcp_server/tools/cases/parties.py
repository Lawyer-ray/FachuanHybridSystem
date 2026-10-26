"""案件当事人 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_case_parties(case_id: int) -> dict[str, Any]:
    """查询指定案件的所有当事人，包含客户详情和诉讼地位。

    后端 ``/cases/parties`` 返回裸数组,工具侧包成 ``{total, items}`` 信封
    (SDK 会把裸 list 逐项拆成独立文本块,空列表变成零内容块;早期「分页壳
    是模型看不到的假结构」的判断经线上实测推翻——dict 信封单块全量可见)。
    """
    return list_result(client.get("/cases/parties", params={"case_id": case_id}))


def add_case_party(case_id: int, client_id: int, legal_status: str | None = None) -> dict[str, Any]:
    """为案件添加当事人。

    legal_status 为诉讼地位,取**英文键**（中文标签不是合法值）:
    plaintiff 原告 / defendant 被告 / third 第三人 / applicant 申请人 /
    respondent 被申请人 / criminal_defendant 被告人 / victim 被害人 /
    appellant 上诉人 / appellee 被上诉人 / orig_plaintiff 原审原告 /
    orig_defendant 原审被告 / orig_third 原审第三人。
    """
    payload: dict[str, Any] = {"case_id": case_id, "client_id": client_id}
    if legal_status:
        payload["legal_status"] = legal_status
    return client.post("/cases/parties", json=payload)  # type: ignore[no-any-return]


def get_case_party(party_id: int) -> dict[str, Any]:
    """获取单个当事人的详情（身份、诉讼地位、联系方式）。"""
    return client.get(f"/cases/parties/{party_id}")  # type: ignore[no-any-return]


def update_case_party(
    party_id: int, legal_status: str | None = None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """更新当事人信息（姓名/诉讼地位/证件等）。只传需要修改的字段。

    legal_status 取值同 ``add_case_party``（英文键,见其文档）;
    ``extra`` 里的其他字段名需与端点 ``PartyUpdate`` 声明一致。
    """
    payload: dict[str, Any] = {}
    if legal_status is not None:
        payload["legal_status"] = legal_status
    payload.update(extra or {})  # extra 可为 None:mypy 分诊发现的真 bug,裸 .update(None) 必 TypeError
    return client.put(f"/cases/parties/{party_id}", json=payload)  # type: ignore[no-any-return]


def delete_case_party(party_id: int) -> None:
    """把当事人从案件中移除——硬删除该关联记录,不可恢复。"""
    client.delete(f"/cases/parties/{party_id}")
