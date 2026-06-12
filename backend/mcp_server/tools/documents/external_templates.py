"""外部模板 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def analyze_template(template_id: int) -> dict[str, Any]:
    """触发或重新触发 LLM 分析外部模板。"""
    return client.post(f"/documents/external-templates/{template_id}/analyze", json={})  # type: ignore[return-value]


def confirm_mappings(template_id: int, mappings: list[dict[str, Any]]) -> dict[str, Any]:
    """确认模板字段映射。"""
    return client.post(f"/documents/external-templates/{template_id}/confirm", json={"mappings": mappings})  # type: ignore[return-value]


def preview_fill(template_id: int, case_id: int, party_id: int | None = None) -> dict[str, Any]:
    """预览模板填充结果。"""
    params: dict[str, Any] = {"case_id": case_id}
    if party_id is not None:
        params["party_id"] = party_id
    return client.get(f"/documents/external-templates/{template_id}/preview", params=params)  # type: ignore[return-value]


def match_templates(case_id: int | None = None, source_name: str | None = None) -> list[dict[str, Any]]:
    """模板匹配推荐。"""
    params: dict[str, Any] = {}
    if case_id is not None:
        params["case_id"] = case_id
    if source_name is not None:
        params["source_name"] = source_name
    return client.get("/documents/external-templates/match", params=params)  # type: ignore[return-value]


def get_custom_fields(template_id: int) -> list[dict[str, Any]]:
    """获取模板需要手动输入的自定义字段。"""
    return client.get(f"/documents/external-templates/{template_id}/custom-fields")  # type: ignore[return-value]


def get_fill_history(case_id: int | None = None, template_id: int | None = None) -> list[dict[str, Any]]:
    """查询填充历史。"""
    params: dict[str, Any] = {}
    if case_id is not None:
        params["case_id"] = case_id
    if template_id is not None:
        params["template_id"] = template_id
    return client.get("/documents/external-templates/history", params=params)  # type: ignore[return-value]


def get_statistics() -> dict[str, Any]:
    """获取当前律所的模板使用统计。"""
    return client.get("/documents/external-templates/statistics")  # type: ignore[return-value]


def get_preview_html(template_id: int) -> dict[str, Any]:
    """将 docx 模板转换为 HTML 用于浏览器预览。"""
    return client.get(f"/documents/external-templates/{template_id}/preview-html")  # type: ignore[return-value]


def list_mappings(template_id: int) -> list[dict[str, Any]]:
    """列出模板的所有字段映射。"""
    return client.get(f"/documents/external-templates/{template_id}/mappings")  # type: ignore[return-value]


def create_mapping(template_id: int, field_name: str, placeholder: str, **extra: Any) -> dict[str, Any]:
    """手动创建新的字段映射。"""
    return client.post(
        f"/documents/external-templates/{template_id}/mappings",
        json={"field_name": field_name, "placeholder": placeholder, **extra},
    )  # type: ignore[return-value]


def update_mapping(mapping_id: int, **fields: Any) -> dict[str, Any]:
    """更新已有字段映射。"""
    return client.put(f"/documents/external-templates/mappings/{mapping_id}", json=fields)  # type: ignore[return-value]


def delete_mapping(mapping_id: int) -> None:
    """删除字段映射。"""
    client.delete(f"/documents/external-templates/mappings/{mapping_id}")
