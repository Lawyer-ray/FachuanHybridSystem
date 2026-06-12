"""诉讼保全 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_guarantee_case_info(case_id: int) -> dict[str, Any]:
    """获取保全案件信息。"""
    return client.get(f"/automation/court-guarantee/case-info/{case_id}")  # type: ignore[return-value]


def get_guarantee_session(session_id: int) -> dict[str, Any]:
    """查询保全任务会话状态。"""
    return client.get(f"/automation/court-guarantee/session/{session_id}")  # type: ignore[return-value]


def execute_guarantee(case_id: int, **extra: Any) -> dict[str, Any]:
    """执行诉讼保全申请。case_id 为案件ID；其余参数通过 extra 透传。"""
    return client.post("/automation/court-guarantee/execute", json={"case_id": case_id, **extra})  # type: ignore[return-value]


def ensure_guarantee_quote(case_id: int, amount: float, **extra: Any) -> dict[str, Any]:
    """确保保全询价已创建。若无则自动创建。"""
    return client.post("/automation/court-guarantee/quote/ensure", json={"case_id": case_id, "amount": amount, **extra})  # type: ignore[return-value]


def bind_guarantee_quote(quote_id: int, case_id: int) -> dict[str, Any]:
    """将保全询价绑定到案件。"""
    return client.post(f"/automation/court-guarantee/quote/{quote_id}/bind", json={"case_id": case_id})  # type: ignore[return-value]


def delete_guarantee_quote(quote_id: int) -> None:
    """删除保全询价记录。"""
    client.delete(f"/automation/court-guarantee/quote/{quote_id}/delete")


def retry_guarantee_quote(quote_id: int) -> dict[str, Any]:
    """重试失败的保全询价。"""
    return client.post(f"/automation/court-guarantee/quote/{quote_id}/retry", json={})  # type: ignore[return-value]


def delete_guarantee_binding(binding_id: int) -> None:
    """删除保全询价绑定关系。"""
    client.delete(f"/automation/court-guarantee/quote-binding/{binding_id}/delete")
