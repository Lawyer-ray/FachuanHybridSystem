"""诉讼保全 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_guarantee_case_info(case_id: int) -> dict[str, Any]:
    """获取案件的保全担保前置信息（保全金额等）——execute_guarantee 前先查。"""
    return client.get(f"/court-guarantee/case-info/{case_id}")  # type: ignore[no-any-return]


def get_guarantee_session(session_id: int) -> dict[str, Any]:
    """查询保全任务会话状态（进行到哪一步、是否需要人工介入）。"""
    return client.get(f"/court-guarantee/session/{session_id}")  # type: ignore[no-any-return]


def execute_guarantee(case_id: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行诉讼保全申请。case_id 为案件ID；其余参数通过 extra 透传。"""
    return client.post("/court-guarantee/execute", json={"case_id": case_id, **(extra or {})})  # type: ignore[no-any-return]


def ensure_guarantee_quote(case_id: int) -> dict[str, Any]:
    """确保保全询价已创建（无则自动创建）。

    询价金额**不由本工具控制**——后端固定取案件档案的保全金额
    （preservation_amount）。历史版本的 amount 参数从未生效（REST
    ``CaseQuoteOperationIn`` 只收 case_id）,2026-10-25 参数级契约审计后移除;
    要按特定金额询价,先更新案件的保全金额。
    """
    return client.post("/court-guarantee/quote/ensure", json={"case_id": case_id})  # type: ignore[no-any-return]


def bind_guarantee_quote(quote_id: int, case_id: int) -> dict[str, Any]:
    """把已完成的询价绑定到案件（后续执行保全时使用该报价）。"""
    return client.post(f"/court-guarantee/quote/{quote_id}/bind", json={"case_id": case_id})  # type: ignore[no-any-return]


def delete_guarantee_quote(quote_id: int, case_id: int) -> dict[str, Any]:
    """删除保全询价记录。后端以 POST /delete 表达删除（非 HTTP DELETE）。

    ``case_id`` 是后端 ``CaseQuoteOperationIn`` 的必填字段，用于归属校验。
    """
    return client.post(f"/court-guarantee/quote/{quote_id}/delete", json={"case_id": case_id})  # type: ignore[no-any-return]


def retry_guarantee_quote(quote_id: int, case_id: int) -> dict[str, Any]:
    """重试失败的保全询价。``case_id`` 为后端必填的归属校验字段。"""
    return client.post(f"/court-guarantee/quote/{quote_id}/retry", json={"case_id": case_id})  # type: ignore[no-any-return]


def delete_guarantee_binding(binding_id: int, case_id: int) -> dict[str, Any]:
    """删除保全询价绑定关系。后端以 POST /delete 表达删除（非 HTTP DELETE）。

    ``case_id`` 是后端 ``CaseQuoteOperationIn`` 的必填字段，用于归属校验。
    """
    return client.post(f"/court-guarantee/quote-binding/{binding_id}/delete", json={"case_id": case_id})  # type: ignore[no-any-return]
