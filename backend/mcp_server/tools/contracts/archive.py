"""合同归档 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def learn_archive_rules() -> dict[str, Any]:
    """从已归档材料中学习分类规则（全局操作）。"""
    return client.post("/contracts/archive/learn-rules", json={})  # type: ignore[return-value]


def get_archive_checklist(contract_id: int) -> dict[str, Any]:
    """获取合同归档清单及各项目完成状态。"""
    return client.get(f"/contracts/{contract_id}/archive/checklist")  # type: ignore[return-value]


def download_archive_item(contract_id: int, archive_item_code: str) -> dict[str, Any]:
    """下载归档清单项目的材料（合并为 PDF）。"""
    content, filename, content_type = client.download(
        f"/contracts/{contract_id}/archive/download-item/{archive_item_code}"
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def generate_archive_folder(contract_id: int) -> dict[str, Any]:
    """生成归档文件夹：模板文档 + 合并 PDF 到绑定文件夹。"""
    return client.post(f"/contracts/{contract_id}/archive/generate-folder", json={})  # type: ignore[return-value]


def toggle_compact_archive(contract_id: int) -> dict[str, Any]:
    """切换合同的简洁归档视图开关。"""
    return client.post(f"/contracts/{contract_id}/archive/toggle-compact", json={})  # type: ignore[return-value]


def sync_case_materials(contract_id: int) -> dict[str, Any]:
    """将关联案件的材料同步到归档。"""
    return client.post(f"/contracts/{contract_id}/archive/sync-case-materials", json={})  # type: ignore[return-value]


def reset_and_resync_case_materials(contract_id: int) -> dict[str, Any]:
    """重置归档材料后重新从案件同步。"""
    return client.post(f"/contracts/{contract_id}/archive/reset-and-resync", json={})  # type: ignore[return-value]


def scale_to_a4(contract_id: int) -> dict[str, Any]:
    """将所有非 A4 尺寸的 PDF 页面缩放为 A4。"""
    return client.post(f"/contracts/{contract_id}/archive/scale-to-a4", json={})  # type: ignore[return-value]


def confirm_archive(contract_id: int) -> dict[str, Any]:
    """确认归档：设置合同状态为"已归档"并自动关闭关联案件。"""
    return client.post(f"/contracts/{contract_id}/archive/confirm", json={})  # type: ignore[return-value]


def delete_archive_material(contract_id: int, material_id: int) -> None:
    """删除单个归档材料。"""
    client.delete(f"/contracts/{contract_id}/archive/materials/{material_id}")


def reorder_archive_materials(contract_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    """重新排列归档材料在清单项目分组内的顺序。"""
    return client.post(f"/contracts/{contract_id}/archive/reorder", json={"items": items})  # type: ignore[return-value]


def move_archive_material(contract_id: int, material_id: int, target_item_code: str) -> dict[str, Any]:
    """将归档材料移动到不同的清单项目分类。"""
    return client.post(
        f"/contracts/{contract_id}/archive/materials/{material_id}/move", json={"target_item_code": target_item_code}
    )  # type: ignore[return-value]


def clear_all_archive_materials(contract_id: int) -> None:
    """删除合同的所有归档材料。"""
    client.post(f"/contracts/{contract_id}/archive/clear-all", json={})
