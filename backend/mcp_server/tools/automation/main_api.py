"""自动化主 API MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def get_automation_config() -> dict[str, Any]:
    """获取当前自动化配置（管理员）——各自动化模块的开关与参数。"""
    return client.get("/automation/config")  # type: ignore[return-value]


def get_automation_status() -> dict[str, Any]:
    """获取自动化系统整体状态概览。"""
    return client.get("/automation/status")  # type: ignore[return-value]
