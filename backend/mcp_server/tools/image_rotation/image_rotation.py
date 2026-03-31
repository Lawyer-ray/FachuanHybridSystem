"""图片旋转/PDF 提取 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def extract_pdf_pages(
    filename: str,
    data_base64: str,
) -> dict[str, Any]:
    """从 PDF 快速提取页面图片。data_base64: PDF 文件的 base64 编码。返回提取的页面列表。"""
    return client.post(  # type: ignore[return-value]
        "/image-rotation/extract-pdf-fast",
        json={"filename": filename, "data": data_base64},
    )


def detect_orientation(
    images: list[dict[str, str]],
) -> dict[str, Any]:
    """批量检测图片方向。images: [{data: base64}]。返回每张图片的旋转角度和置信度。"""
    return client.post(  # type: ignore[return-value]
        "/image-rotation/detect-orientation",
        json={"images": images},
    )


def suggest_rename(
    items: list[dict[str, str]],
) -> dict[str, Any]:
    """AI 建议文件重命名。items: [{filename, ocr_text}]。返回重命名建议列表。"""
    return client.post(  # type: ignore[return-value]
        "/image-rotation/suggest-rename",
        json={"items": items},
    )
