"""OA 立案 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_oa_configs() -> dict[str, Any]:
    """获取当前用户可用的 OA 系统列表。

    每项含 ``oa_system_name``（发起立案时的 site_name 取值）与
    ``has_credential``（当前律师是否已配置该站点的登录凭证）——
    ``has_credential=false`` 的站点发起立案必失败。
    """
    return list_result(client.get("/oa-filing/configs"))


def trigger_oa_filing(
    contract_id: int,
    site_name: str,
    case_id: int | None = None,
) -> dict[str, Any]:
    """发起 OA 立案（全自动浏览器流程，外部副作用，高危需审批）。

    site_name 必须与 ``list_oa_configs`` 返回的 ``oa_system_name`` **完全一致**
    （以该接口返回为准，不要凭记忆猜测）——后端按它精确匹配当前律师的
    账号凭证，名字对不上直接报「未找到匹配凭证」。发起前先调
    ``list_oa_configs`` 确认目标站点 ``has_credential=true``。

    执行是异步的：立即返回立案会话（含 session id），Playwright 流程在
    后台跑（数十秒到分钟级），之后用 ``get_filing_status`` 轮询。
    """
    payload: dict[str, Any] = {"contract_id": contract_id, "site_name": site_name}
    if case_id is not None:
        payload["case_id"] = case_id
    return client.post("/oa-filing/execute", json=payload)  # type: ignore[no-any-return]


def get_filing_status(session_id: int) -> dict[str, Any]:
    """查询 OA 立案进度。

    状态取值：``pending``（待开始）/ ``in_progress``（进行中）/
    ``completed``（已完成）/ ``failed``（失败，含错误信息）/
    ``cancelled``（已取消）。
    """
    return client.get(f"/oa-filing/session/{session_id}")  # type: ignore[no-any-return]
