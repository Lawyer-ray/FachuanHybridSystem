"""自动命名 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def auto_namer_process(file_path: str) -> dict[str, Any]:
    """对文件执行自动命名。file_path 为文件路径。"""
    return client.post("/automation/auto-namer/process", json={"file_path": file_path})  # type: ignore[return-value]


def auto_namer_process_by_path(folder_path: str) -> dict[str, Any]:
    """批量对文件夹中的文件执行自动命名。folder_path 为文件夹路径。"""
    return client.post("/automation/auto-namer/process-by-path", json={"folder_path": folder_path})  # type: ignore[return-value]
