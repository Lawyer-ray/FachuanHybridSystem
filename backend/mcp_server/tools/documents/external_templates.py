"""外部模板 MCP tools"""

from __future__ import annotations

import base64
from typing import Any

from mcp_server.client import client


def analyze_template(template_id: int) -> dict[str, Any]:
    """触发或重新触发 LLM 分析外部模板。"""
    return client.post(f"/documents/external-templates/{template_id}/analyze", json={})  # type: ignore[return-value]


def confirm_mappings(template_id: int) -> dict[str, Any]:
    """确认模板字段映射。"""
    return client.post(f"/documents/external-templates/{template_id}/confirm")  # type: ignore[return-value]


def preview_fill(template_id: int, case_id: int, party_id: int | None = None) -> dict[str, Any]:
    """预览模板填充结果。"""
    params: dict[str, Any] = {"case_id": case_id}
    if party_id is not None:
        params["party_id"] = party_id
    return client.get(f"/documents/external-templates/{template_id}/preview", params=params)  # type: ignore[return-value]


def match_templates(case_id: int | None = None, source_name: str | None = None) -> dict[str, Any]:
    """模板匹配推荐。

    返回 ``{success, results}`` 或 ``{success: false, message}``——匹配结果在
    ``results`` 里，失败时没有 ``results`` 键。
    """
    params: dict[str, Any] = {}
    if case_id is not None:
        params["case_id"] = case_id
    if source_name is not None:
        params["source_name"] = source_name
    return client.get("/documents/external-templates/match", params=params)  # type: ignore[return-value]


def get_custom_fields(template_id: int) -> dict[str, Any]:
    """获取模板需要手动输入的自定义字段。

    返回 ``{template_id, fields}``，字段清单在 ``fields`` 里。
    """
    return client.get(f"/documents/external-templates/{template_id}/custom-fields")  # type: ignore[return-value]


def get_fill_history(case_id: int | None = None, template_id: int | None = None) -> dict[str, Any]:
    """查询填充历史。

    返回 ``{success, records}`` 或 ``{success: false, message}``——
    既不传 case_id 也不传 template_id 时返回错误说明，而不是空列表。
    """
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


def create_mapping(
    template_id: int,
    position_locator: dict[str, Any],
    semantic_label: str,
    position_description: str = "",
    fill_type: str = "text",
) -> dict[str, Any]:
    """手动创建新的字段映射。"""
    return client.post(
        f"/documents/external-templates/{template_id}/mappings",
        json={
            "position_locator": position_locator,
            "semantic_label": semantic_label,
            "position_description": position_description,
            "fill_type": fill_type,
        },
    )  # type: ignore[return-value]


def update_mapping(mapping_id: int, **fields: Any) -> dict[str, Any]:
    """更新已有字段映射。"""
    return client.put(f"/documents/external-templates/mappings/{mapping_id}", json=fields)  # type: ignore[return-value]


def delete_mapping(mapping_id: int) -> None:
    """删除字段映射。"""
    client.delete(f"/documents/external-templates/mappings/{mapping_id}")


def fill_templates(
    template_ids: list[int],
    case_id: int,
    party_ids: list[int] | None = None,
    custom_values: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """按案件数据批量填充模板，生成文书文件。

    这是「一次性出整套文书」的入口：传一组模板 + 一个案件，后端会把案件
    当事人、案号、金额等占位符全部代入。此前 agent 只能逐个模板调 preview，
    无法真正产出文件。

    Args:
        template_ids: 要填充的模板 ID 列表（支持批量）。
        case_id: 案件 ID（数据来源）。
        party_ids: 可选，指定参与填充的当事人；不传则用案件全部当事人。
        custom_values: 可选，手动补充值，形如 ``{template_id: {key: value}}``
            （键为字符串形式的模板 ID）。

    Returns:
        后端返回填充结果（成功时含生成文件信息）。
    """
    payload: dict[str, Any] = {"template_ids": template_ids, "case_id": case_id}
    if party_ids:
        payload["party_ids"] = party_ids
    if custom_values:
        payload["custom_values"] = custom_values
    return client.post("/documents/external-templates/fill", json=payload)  # type: ignore[return-value]
