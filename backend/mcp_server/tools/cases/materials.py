"""案件材料 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_bind_candidates(case_id: int) -> list[dict[str, Any]]:
    """获取案件材料的绑定候选列表（可关联的文件夹扫描结果）。"""
    return client.get(f"/cases/{case_id}/materials/bind-candidates")  # type: ignore[return-value]


def bind_materials(case_id: int, material_ids: list[int], group_name: str) -> dict[str, Any]:
    """将材料绑定到案件。material_ids 为要绑定的材料ID列表；group_name 为分组名称。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/materials/bind",
        json={"material_ids": material_ids, "group_name": group_name},
    )


def save_group_order(case_id: int, group_order: list[dict[str, Any]]) -> dict[str, Any]:
    """保存材料分组排序。group_order 为分组排序列表，每项包含 group_name 和 order 字段。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/materials/group-order",
        json={"group_order": group_order},
    )


def rename_material_group(case_id: int, old_name: str, new_name: str) -> dict[str, Any]:
    """重命名材料分组。"""
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/materials/group-rename",
        json={"old_name": old_name, "new_name": new_name},
    )


def delete_material(case_id: int, material_id: int) -> None:
    """删除案件中的单个材料。"""
    client.delete(f"/cases/{case_id}/materials/{material_id}")


def delete_all_materials(case_id: int) -> None:
    """删除案件的所有材料。此操作不可逆。"""
    client.delete(f"/cases/{case_id}/materials")
