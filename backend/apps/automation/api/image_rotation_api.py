"""API endpoints."""

from __future__ import annotations

"""
图片自动旋转 API

提供图片旋转和 ZIP 导出的 HTTP 接口.

Requirements: 6.1, 6.3
"""

import logging
from typing import Any

from ninja import Router

from apps.automation.schemas import (
    DetectOrientationRequestSchema,
    DetectOrientationResponseSchema,
    DetectPageOrientationRequestSchema,
    DetectPageOrientationResponseSchema,
    ExportPDFRequestSchema,
    ExportPDFResponseSchema,
    ExportRequestSchema,
    ExportResponseSchema,
    PDFExtractFastResponseSchema,
    PDFExtractRequestSchema,
    PDFExtractResponseSchema,
    SuggestRenameRequestSchema,
    SuggestRenameResponseSchema,
)
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.automation.image_rotation")

router = Router(tags=["图片自动旋转"])


def _get_image_rotation_service() -> Any:
    """
    工厂函数:创建图片旋转服务实例

    Returns:
        ImageRotationService 实例
    """
    from apps.automation.services.image_rotation import ImageRotationService

    return ImageRotationService()


def _get_orientation_detection_service() -> Any:
    """
    工厂函数:创建方向检测服务实例

    Returns:
        OrientationDetectionService 实例
    """
    from apps.automation.services.image_rotation import OrientationDetectionService

    return OrientationDetectionService()


def _get_pdf_extraction_service() -> Any:
    """
    工厂函数:创建 PDF 提取服务实例

    Returns:
        PDFExtractionService 实例
    """
    from apps.automation.services.image_rotation.pdf_extraction_service import PDFExtractionService

    return PDFExtractionService()


def _get_auto_rename_service() -> Any:
    """
    工厂函数:创建自动重命名服务实例

    Returns:
        AutoRenameService 实例
    """
    from apps.automation.services.image_rotation.auto_rename_service import AutoRenameService

    return AutoRenameService()


@router.post("/export", response=ExportResponseSchema)
@rate_limit_from_settings("EXPORT", by_user=True)
def export_rotated_images(request: Any, payload: ExportRequestSchema) -> Any:
    """
    导出旋转后的图片为 ZIP

    接收图片列表(Base64 编码),应用旋转后打包为 ZIP 文件.

    **请求示例**:
    ```json
    {
        "images": [
            {
                "filename": "photo1.jpg",
                "data": "iVBORw0KGgoAAAANSUhEUgAAAAUA...",
                "rotation": 90,
                "format": "jpeg"
            }
        ],
        "rename_map": {
            "photo1.jpg": "20250630_65500元.jpg"
        }
    }
    ```

    **成功响应示例**:
    ```json
    {
        "success": true,
        "zip_url": "/media/image_rotation/rotated_images_20250101_120000.zip",
        "message": null
    }
    ```

    Args:
        request: HTTP 请求对象
        payload: 导出请求数据

    Returns:
        ExportResponseSchema: 导出结果,包含成功状态和 ZIP 下载 URL

    Requirements: 5.1, 5.3, 6.1, 6.3
    """
    logger.info(f"收到图片导出请求,图片数量: {len(payload.images)}, 纸张尺寸: {payload.paper_size}")

    # 创建服务实例并执行导出
    service = _get_image_rotation_service()

    # 转换 Pydantic 模型为字典列表
    images_data: list[Any] = []
    result = service.export_images(images_data, paper_size=payload.paper_size, rename_map=payload.rename_map)

    # 记录请求结果
    if result.get("success"):
        logger.info(f"图片导出成功: zip_url={result.get('zip_url')}")
    else:
        logger.warning(f"图片导出失败: message={result.get('message')}")

    return ExportResponseSchema(
        success=result.get("success", False),
        zip_url=result.get("zip_url"),
        message=result.get("message"),
        warnings=result.get("warnings"),
    )


@router.post("/detect-orientation", response=DetectOrientationResponseSchema)
@rate_limit_from_settings("UPLOAD", by_user=True)
def detect_orientation(request: Any, payload: DetectOrientationRequestSchema) -> Any:
    """
    检测图片方向(用于没有 EXIF 数据的图片)

    使用 Tesseract OSD 检测图片中文字的方向,返回需要旋转的角度.

    **请求示例**:
    ```json
    {
        "images": [
            {
                "filename": "photo1.jpg",
                "data": "iVBORw0KGgoAAAANSUhEUgAAAAUA..."
            }
        ]
    }
    ```

    **成功响应示例**:
    ```json
    {
        "success": true,
        "results": [
            {
                "filename": "photo1.jpg",
                "rotation": 90,
                "confidence": 0.95,
                "method": "tesseract"
            }
        ]
    }
    ```

    Args:
        request: HTTP 请求对象
        payload: 检测请求数据

    Returns:
        DetectOrientationResponseSchema: 检测结果
    """
    logger.info(f"收到方向检测请求,图片数量: {len(payload.images)}")

    service = _get_orientation_detection_service()

    images_data: list[Any] = []
    results = service.detect_batch(images_data)

    return DetectOrientationResponseSchema(
        success=True,
        results=results,
    )


@router.post("/extract-pdf", response=PDFExtractResponseSchema)
@rate_limit_from_settings("UPLOAD", by_user=True)
def extract_pdf_pages(request: Any, payload: PDFExtractRequestSchema) -> Any:
    """
    提取 PDF 页面为图片(包含方向检测,较慢)

    接收 Base64 编码的 PDF 文件,返回每页的图片数据和检测到的旋转角度.

    Args:
        request: HTTP 请求对象
        payload: PDF 提取请求数据

    Returns:
        PDFExtractResponseSchema: 提取结果,包含每页的图片数据和旋转角度

    Requirements: 1.2
    """
    logger.info(f"收到 PDF 提取请求: {payload.filename}")

    service = _get_pdf_extraction_service()
    result = service.extract_pages(payload.data, payload.filename)

    if result.get("success"):
        logger.info(f"PDF 提取成功: filename={payload.filename}, pages={len(result.get('pages', []))}")
    else:
        logger.warning(f"PDF 提取失败: filename={payload.filename}, message={result.get('message')}")

    return PDFExtractResponseSchema(
        success=result.get("success", False),
        filename=result.get("filename", payload.filename),
        pages=result.get("pages", []),
        message=result.get("message"),
    )


@router.post("/extract-pdf-fast", response=PDFExtractFastResponseSchema)
@rate_limit_from_settings("UPLOAD", by_user=True)
def extract_pdf_pages_fast(request: Any, payload: PDFExtractRequestSchema) -> Any:
    """
    快速提取 PDF 页面为图片(不检测方向)

    只提取页面图片,不进行方向检测,速度更快.
    前端可以先显示页面,再异步调用方向检测接口.

    Args:
        request: HTTP 请求对象
        payload: PDF 提取请求数据

    Returns:
        PDFExtractFastResponseSchema: 提取结果
    """
    logger.info(f"收到 PDF 快速提取请求: {payload.filename}")

    service = _get_pdf_extraction_service()
    result = service.extract_pages_only(payload.data, payload.filename)

    if result.get("success"):
        logger.info(f"PDF 快速提取成功: filename={payload.filename}, pages={len(result.get('pages', []))}")
    else:
        logger.warning(f"PDF 快速提取失败: filename={payload.filename}, message={result.get('message')}")

    return PDFExtractFastResponseSchema(
        success=result.get("success", False),
        filename=result.get("filename", payload.filename),
        pages=result.get("pages", []),
        message=result.get("message"),
    )


@router.post("/detect-page-orientation", response=DetectPageOrientationResponseSchema)
@rate_limit_from_settings("UPLOAD", by_user=True)
def detect_page_orientation(request: Any, payload: DetectPageOrientationRequestSchema) -> Any:
    """
    检测单个页面的方向

    用于 PDF 页面的异步方向检测.

    Args:
        request: HTTP 请求对象
        payload: 单页检测请求数据

    Returns:
        DetectPageOrientationResponseSchema: 检测结果
    """
    service = _get_pdf_extraction_service()
    result = service.detect_single_page_orientation(payload.data)

    return DetectPageOrientationResponseSchema(
        rotation=result.get("rotation", 0),
        confidence=result.get("confidence", 0),
        method=result.get("method", "none"),
        error=result.get("error"),
    )


@router.post("/export-pdf", response=ExportPDFResponseSchema)
@rate_limit_from_settings("EXPORT", by_user=True)
def export_as_pdf(request: Any, payload: ExportPDFRequestSchema) -> Any:
    """
    导出所有页面为单个 PDF 文件

    接收图片/页面列表,生成 PDF 文件.

    **请求示例**:
    ```json
    {
        "pages": [
            {
                "filename": "photo1.jpg",
                "data": "iVBORw0KGgoAAAANSUhEUgAAAAUA...",
                "rotation": 90,
                "source_type": "image"
            },
            {
                "filename": "document.pdf_page_1",
                "data": "iVBORw0KGgoAAAANSUhEUgAAAAUA...",
                "rotation": 0,
                "source_type": "pdf_page"
            }
        ]
    }
    ```

    **成功响应示例**:
    ```json
    {
        "success": true,
        "pdf_url": "/media/image_rotation/rotated_pages_20250101_120000.pdf",
        "message": null
    }
    ```

    Args:
        request: HTTP 请求对象
        payload: PDF 导出请求数据

    Returns:
        ExportPDFResponseSchema: 导出结果,包含成功状态和 PDF 下载 URL

    Requirements: 5.1
    """
    logger.info(f"收到 PDF 导出请求,页面数量: {len(payload.pages)}, 纸张尺寸: {payload.paper_size}")

    service = _get_image_rotation_service()

    # 转换 Pydantic 模型为字典列表
    pages_data: list[Any] = []
    result = service.export_as_pdf(pages_data, paper_size=payload.paper_size)

    if result.get("success"):
        logger.info(f"PDF 导出成功: pdf_url={result.get('pdf_url')}")
    else:
        logger.warning(f"PDF 导出失败: message={result.get('message')}")

    return ExportPDFResponseSchema(
        success=result.get("success", False),
        pdf_url=result.get("pdf_url"),
        message=result.get("message"),
    )


@router.post("/suggest-rename", response=SuggestRenameResponseSchema)
@rate_limit_from_settings("LLM", by_user=True)
def suggest_rename(request: Any, payload: SuggestRenameRequestSchema) -> Any:
    """
    获取图片重命名建议

    接收图片文件名和 OCR 文本列表,使用 LLM 提取日期和金额信息,
    返回建议的新文件名.

    **请求示例**:
    ```json
    {
        "items": [
            {
                "filename": "IMG_001.jpg",
                "ocr_text": "收据\\n日期:2025年6月30日\\n金额:65,500元"
            },
            {
                "filename": "IMG_002.jpg",
                "ocr_text": "发票\\n2025-07-01\\n总计:12000元"
            }
        ]
    }
    ```

    **成功响应示例**:
    ```json
    {
        "success": true,
        "suggestions": [
            {
                "original_filename": "IMG_001.jpg",
                "suggested_filename": "20250630_65500元.jpg",
                "date": "20250630",
                "amount": "65500元",
                "success": true,
                "error": null
            },
            {
                "original_filename": "IMG_002.jpg",
                "suggested_filename": "20250701_12000元.jpg",
                "date": "20250701",
                "amount": "12000元",
                "success": true,
                "error": null
            }
        ]
    }
    ```

    Args:
        request: HTTP 请求对象
        payload: 重命名建议请求数据

    Returns:
        SuggestRenameResponseSchema: 重命名建议响应

    Requirements: 4.1, 4.3
    """
    logger.info(f"收到重命名建议请求,项目数量: {len(payload.items)}")

    service = _get_auto_rename_service()

    # 调用批量处理方法
    suggestions = service.suggest_rename_batch(payload.items)

    # 转换为响应格式
    suggestion_items: list[Any] = [
        {
            "original_filename": s.original_filename,
            "suggested_filename": s.suggested_filename,
            "date": s.date,
            "amount": s.amount,
            "success": s.success,
            "error": s.error,
        }
        for s in suggestions
    ]

    logger.info(f"重命名建议生成完成,成功: {sum(1 for s in suggestions if s.success)}/{len(suggestions)}")

    return SuggestRenameResponseSchema(
        success=True,
        suggestions=suggestion_items,
    )
