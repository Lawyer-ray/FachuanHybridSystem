"""图片旋转/PDF 提取 MCP tools"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client


def extract_pdf_pages(
    filename: str,
    data_base64: str,
) -> dict[str, Any]:
    """从 PDF 快速提取页面图片。data_base64: PDF 文件的 base64 编码。返回提取的页面列表。"""
    return client.post(  # type: ignore[no-any-return]
        "/image-rotation/extract-pdf-fast",
        json={"filename": filename, "data": data_base64},
    )


def detect_orientation(
    images: list[dict[str, str]],
) -> dict[str, Any]:
    """批量检测图片方向。images: [{data: base64}]。返回每张图片的旋转角度和置信度。"""
    return client.post(  # type: ignore[no-any-return]
        "/image-rotation/detect-orientation",
        json={"images": images},
    )


def suggest_rename(
    items: list[dict[str, str]],
) -> dict[str, Any]:
    """AI 建议文件重命名。items: [{filename, ocr_text}]。返回重命名建议列表。"""
    return client.post(  # type: ignore[no-any-return]
        "/image-rotation/suggest-rename",
        json={"items": items},
    )


def detect_single_page_orientation(data_base64: str) -> dict[str, Any]:
    """检测单张图片的旋转方向。data_base64 为图片的 base64 编码。"""
    return client.post(  # type: ignore[no-any-return]
        "/image-rotation/detect-page-orientation",
        json={"data": data_base64},
    )


def export_rotated_pdf(
    pages: list[dict[str, str]],
    paper_size: str = "A4",
) -> dict[str, Any]:
    """将旋转后的图片导出为 PDF。pages: [{filename, data, rotation}]。paper_size: A4/A3/B5。"""
    return client.post(  # type: ignore[no-any-return]
        "/image-rotation/export-pdf",
        json={"pages": pages, "paper_size": paper_size},
    )


def export_rotated_images(
    images: list[dict[str, str]],
    format: str = "png",
    paper_size: str = "A4",
) -> dict[str, Any]:
    """将旋转后的图片导出为图片文件。images: [{filename, data, rotation}]。format: png/jpg。"""
    return client.post(  # type: ignore[no-any-return]
        "/image-rotation/export",
        json={"images": images, "format": format, "paper_size": paper_size},
    )
