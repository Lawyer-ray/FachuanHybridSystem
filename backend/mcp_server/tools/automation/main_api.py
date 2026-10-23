"""自动化主 API MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_automation_config() -> dict[str, Any]:
    """获取当前自动化配置（管理员）。"""
    return client.get("/automation/config")  # type: ignore[return-value]


def get_automation_status() -> dict[str, Any]:
    """获取系统状态。"""
    return client.get("/automation/status")  # type: ignore[return-value]
