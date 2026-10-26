"""合同归档 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def learn_archive_rules() -> dict[str, Any]:
    """从已归档材料学习分类规则（写入全局规则库,影响后续自动分类）。"""
    return client.post("/contracts/archive/learn-rules", json={})  # type: ignore[no-any-return]


def get_archive_checklist(contract_id: int) -> dict[str, Any]:
    """获取合同归档清单及各清单项的完成状态——归档前查缺漏用。"""
    return client.get(f"/contracts/{contract_id}/archive/checklist")  # type: ignore[no-any-return]


def download_archive_item(contract_id: int, archive_item_code: str) -> dict[str, Any]:
    """下载归档清单某项的材料（多份合并为 PDF）——1MB 闸门内返回 base64。"""
    content, filename, content_type = client.download(
        f"/contracts/{contract_id}/archive/download-item/{archive_item_code}"
    )
    return {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(content).decode()}


def generate_archive_folder(contract_id: int) -> dict[str, Any]:
    """生成归档文件夹：模板文档 + 合并 PDF 到绑定文件夹。"""
    return client.post(f"/contracts/{contract_id}/archive/generate-folder", json={})  # type: ignore[no-any-return]


def toggle_compact_archive(contract_id: int) -> dict[str, Any]:
    """切换合同的简洁归档视图开关（只影响展示,不动数据）。"""
    return client.post(f"/contracts/{contract_id}/archive/toggle-compact", json={})  # type: ignore[no-any-return]


def sync_case_materials(contract_id: int) -> dict[str, Any]:
    """把关联案件的材料同步进合同归档（增量,不覆盖已有）。"""
    return client.post(f"/contracts/{contract_id}/archive/sync-case-materials", json={})  # type: ignore[no-any-return]


def reset_and_resync_case_materials(contract_id: int) -> dict[str, Any]:
    """清空合同归档材料后从案件全量重同步——**紧急级,需二次确认**;会丢弃归档侧的手工调整。"""
    return client.post(f"/contracts/{contract_id}/archive/reset-and-resync", json={})  # type: ignore[no-any-return]


def scale_to_a4(contract_id: int) -> dict[str, Any]:
    """将所有非 A4 尺寸的 PDF 页面缩放为 A4。"""
    return client.post(f"/contracts/{contract_id}/archive/scale-to-a4", json={})  # type: ignore[no-any-return]


def confirm_archive(contract_id: int) -> dict[str, Any]:
    """确认归档：设置合同状态为"已归档"并自动关闭关联案件。"""
    return client.post(f"/contracts/{contract_id}/archive/confirm", json={})  # type: ignore[no-any-return]


def delete_archive_material(contract_id: int, material_id: int) -> dict[str, Any]:
    """删除单个归档材料记录——硬删除,不可恢复。"""
    return client.delete(f"/contracts/{contract_id}/archive/materials/{material_id}")  # type: ignore[no-any-return]


def reorder_archive_materials(contract_id: int, orders: dict[str, list[int]]) -> dict[str, Any]:
    """调整归档材料在清单项分组内的显示顺序。"""
    return client.post(f"/contracts/{contract_id}/archive/reorder", json={"orders": orders})  # type: ignore[no-any-return]


def move_archive_material(contract_id: int, material_id: int, target_item_code: str) -> dict[str, Any]:
    """把归档材料移到其他清单项分类。

    Args:
        contract_id: 合同 ID。
        material_id: 归档材料 ID。
        target_item_code: 目标清单项编码(归档清单的 item code,见归档清单工具)。
    """
    return client.post(  # type: ignore[no-any-return]
        f"/contracts/{contract_id}/archive/materials/{material_id}/move", json={"target_code": target_item_code}
    )


def clear_all_archive_materials(contract_id: int) -> dict[str, Any]:
    """清空合同的**全部**归档材料——紧急级,需二次确认,不可恢复。"""
    return client.post(f"/contracts/{contract_id}/archive/clear-all", json={})  # type: ignore[no-any-return]
