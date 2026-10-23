"""文件夹浏览 MCP tools（案件 / 合同）。

系统里案件和合同都绑定了服务器上的归档文件夹。此前 agent 只能看到数据库
里的材料记录，看不到磁盘上的真实目录结构，于是「这个案子的材料文件夹里
有什么」「证据目录在哪」都无法回答。

两个端点的返回结构一致（``browsable / path_display / folders / files``），
这里不做归一化，原样透出，避免又造出「声明与实现不符」的假结构。
"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_case_folder_entries(case_id: int, subpath: str = "") -> dict[str, Any]:
    """列出案件绑定文件夹下某个子目录的条目。

    Args:
        case_id: 案件 ID。
        subpath: 相对绑定根的子路径，空串表示根目录。

    Returns:
        ``{browsable, message, path_display, subpath, parent_subpath, folders, files}``；
        ``browsable=False`` 时 ``message`` 说明原因（未绑定/路径不存在/无权限）。
    """
    params: dict[str, Any] = {}
    if subpath:
        params["subpath"] = subpath
    return client.get(f"/cases/{case_id}/folder-entries", params=params)  # type: ignore[return-value]


def list_contract_folder_entries(contract_id: int, subpath: str = "") -> dict[str, Any]:
    """列出合同绑定文件夹下某个子目录的条目。

    Args:
        contract_id: 合同 ID。
        subpath: 相对绑定根的子路径，空串表示根目录。

    Returns:
        ``{browsable, message, path_display, subpath, parent_subpath, folders, files}``
    """
    params: dict[str, Any] = {}
    if subpath:
        params["subpath"] = subpath
    return client.get(f"/contracts/{contract_id}/folder-entries", params=params)  # type: ignore[return-value]
