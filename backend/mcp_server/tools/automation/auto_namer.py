"""自动命名 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def auto_namer_process_by_path(
    file_path: str,
    prompt: str | None = None,
    model: str | None = None,
    limit: int | None = None,
    preview_page: int | None = None,
) -> dict[str, Any]:
    """按目录路径批量执行自动命名。

    后端 ``AutoToolProcessIn`` 的必填字段是 ``file_path``。早前工具传
    ``folder_path``——字段名不符，调用必然 422。

    Args:
        file_path: 要处理的目录（或单个文件）路径。
        prompt: 可选，自定义命名提示词。
        model: 可选，指定模型。
        limit: 可选，最多处理多少个文件。
        preview_page: 可选，预览页序号。
    """
    payload: dict[str, Any] = {"file_path": file_path}
    if prompt:
        payload["prompt"] = prompt
    if model:
        payload["model"] = model
    if limit is not None:
        payload["limit"] = limit
    if preview_page is not None:
        payload["preview_page"] = preview_page
    return client.post("/automation/auto-namer/process-by-path", json=payload)  # type: ignore[no-any-return]
