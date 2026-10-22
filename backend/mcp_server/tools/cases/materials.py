"""案件材料 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def list_bind_candidates(case_id: int) -> list[dict[str, Any]]:
    """获取案件材料的绑定候选列表（可关联的文件夹扫描结果）。"""
    return client.get(f"/cases/{case_id}/materials/bind-candidates")  # type: ignore[return-value]


def bind_materials(
    case_id: int,
    items: list[dict[str, Any]],
) -> dict[str, int]:
    """把案件日志附件绑定为正式案件材料。

    后端 ``CaseMaterialBindIn`` 只接受一个 ``items`` 数组，每一项描述
    **一个附件**要落成的材料：

    ```
    items: [
      {
        "attachment_id": 123,          # 必填：来源附件 ID
        "category": "plaintiff",        # 必填：材料大类
        "type_id": 45,                  # 可选：材料类型 ID
        "type_name": "起诉状",          # 必填：类型名称
        "side": "ours",                 # 可选：当事人方向
        "party_ids": [1, 2],            # 可选：关联当事人
        "supervising_authority_id": 3   # 可选：主管机关
      }
    ]
    ```

    早前签名是 ``(material_ids, group_name)``，与后端结构完全不同，
    每次调用都被 422 拒绝——材料绑定功能对 agent 完全不可用。
    """
    return client.post(f"/cases/{case_id}/materials/bind", json={"items": items})  # type: ignore[no-any-return]


def save_group_order(
    case_id: int,
    category: str,
    ordered_type_ids: list[int],
    side: str | None = None,
    supervising_authority_id: int | None = None,
) -> dict[str, bool]:
    """保存某个材料大类下的类型排序。

    后端 ``CaseMaterialGroupOrderIn`` 的必填字段是 ``category`` 与
    ``ordered_type_ids``。早前签名传 ``group_order``，字段名与结构都不符，
    调用必然 422。

    Args:
        case_id: 案件 ID。
        category: 材料大类。
        ordered_type_ids: 按新顺序排列的材料类型 ID 列表。
        side: 可选，限定某一当事人方向。
        supervising_authority_id: 可选，限定某一主管机关。
    """
    payload: dict[str, Any] = {"category": category, "ordered_type_ids": ordered_type_ids}
    if side is not None:
        payload["side"] = side
    if supervising_authority_id is not None:
        payload["supervising_authority_id"] = supervising_authority_id
    return client.post(f"/cases/{case_id}/materials/group-order", json=payload)  # type: ignore[no-any-return]


def rename_material_group(case_id: int, type_id: int, new_type_name: str) -> dict[str, Any]:
    """重命名材料分组的类型名称。

    后端要的是 ``{type_id, new_type_name}``。早前签名传
    ``{old_name, new_name}``，调用必然 422。
    """
    return client.post(  # type: ignore[return-value]
        f"/cases/{case_id}/materials/group-rename",
        json={"type_id": type_id, "new_type_name": new_type_name},
    )


def delete_material(case_id: int, material_id: int) -> dict[str, Any]:
    """删除案件中的单个材料。返回后端删除结果（含被删材料摘要）。"""
    return client.delete(f"/cases/{case_id}/materials/{material_id}")  # type: ignore[no-any-return]


def delete_all_materials(case_id: int, category: str) -> dict[str, Any]:
    """按分类删除案件下的所有材料。此操作不可逆。

    Args:
        case_id: 案件 ID。
        category: 材料大类（如 plaintiff/defendant/court/other）。**必填**——
            后端 ``CaseMaterialDeleteAllIn`` 以 category 限定删除范围，
            早前签名漏传该字段导致每次调用都被 422 拒绝。
    """
    return client.delete(f"/cases/{case_id}/materials", json={"category": category})  # type: ignore[no-any-return]
