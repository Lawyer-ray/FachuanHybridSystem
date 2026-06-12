"""客户验证 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def validate_id_card(id_number: str) -> dict[str, Any]:
    """验证身份证号是否合法。返回校验结果。"""
    return client.post("/client/clients/validate-id-card", json={"id_number": id_number})  # type: ignore[return-value]


def check_oa_credential() -> dict[str, Any]:
    """检查当前用户是否有可用的 OA 系统凭证。"""
    return client.get("/client/clients/check-oa-credential")  # type: ignore[return-value]
