"""图片自动旋转 & PDF 旋转支持 Schemas"""

import base64
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


class ImageRotationItem(BaseModel):
    """图片旋转项 Schema

    Requirements: 6.1
    """

    filename: str = Field(..., description="原始文件名", min_length=1)
    data: str = Field(..., description="Base64 编码的图片数据", min_length=1)
    rotation: int = Field(..., description="旋转角度 (0, 90, 180, 270)")
    format: str = Field(..., description="图片格式 (jpeg, png)")

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: int) -> int:
        """验证旋转角度必须是 0, 90, 180, 270 之一"""
        valid_rotations = {0, 90, 180, 270}
        if v not in valid_rotations:
            raise ValueError(f"旋转角度必须是 {valid_rotations} 之一")
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """验证图片格式"""
        valid_formats = {"jpeg", "png"}
        v_lower = v.lower()
        if v_lower not in valid_formats:
            raise ValueError(f"图片格式必须是 {valid_formats} 之一")
        return v_lower


class ExportRequestSchema(BaseModel):
    """图片导出请求 Schema

    Requirements: 5.1, 5.3, 6.1
    """

    images: list[ImageRotationItem] = Field(..., description="图片列表", min_length=1)
    paper_size: str = Field(
        "original",
        description="输出纸张尺寸: original(原始), a4, a3, letter",
    )
    rename_map: dict[str, str] | None = Field(
        None,
        description="文件名映射表,key 为原始文件名,value 为新文件名.未映射的文件保持原名.",
    )

    @field_validator("images")
    @classmethod
    def validate_images(cls, v: list[ImageRotationItem]) -> list[ImageRotationItem]:
        """验证图片列表"""
        if not v:
            raise ValueError("图片列表不能为空")
        return v

    @field_validator("paper_size")
    @classmethod
    def validate_paper_size(cls, v: str) -> str:
        """验证纸张尺寸"""
        valid_sizes: tuple[str, ...] = (("A4", "A3", "B4", "B5"),)  # type: ignore[assignment]
        if v.lower() not in valid_sizes:
            raise ValueError(f"不支持的纸张尺寸: {v},可选: {', '.join(valid_sizes)}")
        return v.lower()


class ExportResponseSchema(BaseModel):
    """图片导出响应 Schema

    Requirements: 6.1
    """

    success: bool = Field(..., description="是否成功")
    zip_url: str | None = Field(None, description="ZIP 文件下载 URL")
    message: str | None = Field(None, description="响应消息")
    warnings: list[str] | None = Field(None, description="警告信息列表")

    class Config:
        json_schema_extra: ClassVar = {
            "examples": [
                {
                    "success": True,
                    "zip_url": "/media/image_rotation/rotated_images_20250101_120000_abc12345.zip",
                    "message": None,
                    "warnings": None,
                },
                {
                    "success": False,
                    "zip_url": None,
                    "message": "所有图片处理失败",
                    "warnings": ["image1.jpg: 格式不支持"],
                },
            ]
        }


class DetectOrientationItem(BaseModel):
    """方向检测图片项 Schema"""

    filename: str = Field(..., description="文件名")
    data: str = Field(..., description="Base64 编码的图片数据", min_length=1)


class DetectOrientationRequestSchema(BaseModel):
    """方向检测请求 Schema"""

    images: list[DetectOrientationItem] = Field(..., description="图片列表", min_length=1)

    @field_validator("images")
    @classmethod
    def validate_images(cls, v: list[DetectOrientationItem]) -> list[DetectOrientationItem]:
        """验证图片列表"""
        if not v:
            raise ValueError("图片列表不能为空")
        return v


class OrientationResult(BaseModel):
    """单个图片方向检测结果"""

    filename: str = Field(..., description="文件名")
    rotation: int = Field(..., description="需要旋转的角度 (0, 90, 180, 270)")
    confidence: float = Field(0, description="置信度")
    method: str = Field("none", description="检测方法")
    script: str | None = Field(None, description="检测到的文字类型")
    error: str | None = Field(None, description="错误信息")
    ocr_text: str | None = Field(None, description="OCR 识别的文本内容")


class DetectOrientationResponseSchema(BaseModel):
    """方向检测响应 Schema"""

    success: bool = Field(..., description="是否成功")
    results: list[OrientationResult] = Field(..., description="检测结果列表")


# ============================================================================
# PDF 旋转支持 Schemas
# ============================================================================


class PDFExtractRequestSchema(BaseModel):
    """PDF 提取请求

    Requirements: 1.2
    """

    filename: str = Field(..., description="PDF 文件名", min_length=1)
    data: str = Field(..., description="Base64 编码的 PDF 数据", min_length=1)

    @field_validator("data")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """验证 Base64 格式"""
        if not v or not v.strip():
            raise ValueError("PDF 数据不能为空")

        # 移除可能的 data URL 前缀
        if "," in v:
            v = v.split(",", 1)[1]

        v = v.strip()

        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("无效的 Base64 编码") from None

        return v


class PDFPageItem(BaseModel):
    """PDF 页面项

    Requirements: 1.2, 2.1
    """

    page_number: int = Field(..., description="页码(从 1 开始)", ge=1)
    data: str = Field(..., description="Base64 编码的页面图片")
    rotation: int = Field(..., description="检测到的旋转角度")
    confidence: float = Field(..., description="检测置信度", ge=0, le=1)
    width: int = Field(..., description="页面宽度", gt=0)
    height: int = Field(..., description="页面高度", gt=0)

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: int) -> int:
        """验证旋转角度必须是 0, 90, 180, 270 之一"""
        valid_rotations = {0, 90, 180, 270}
        if v not in valid_rotations:
            raise ValueError(f"旋转角度必须是 {valid_rotations} 之一")
        return v


class PDFExtractResponseSchema(BaseModel):
    """PDF 提取响应

    Requirements: 1.2
    """

    success: bool = Field(..., description="是否成功")
    filename: str = Field(..., description="原始文件名")
    pages: list[PDFPageItem] = Field(default_factory=list, description="页面列表")
    message: str | None = Field(None, description="响应消息")

    class Config:
        json_schema_extra: ClassVar = {
            "examples": [
                {
                    "success": True,
                    "filename": "document.pdf",
                    "pages": [
                        {
                            "page_number": 1,
                            "data": "iVBORw0KGgo...",
                            "rotation": 0,
                            "confidence": 0.95,
                            "width": 595,
                            "height": 842,
                        }
                    ],
                    "message": None,
                },
                {
                    "success": False,
                    "filename": "invalid.pdf",
                    "pages": [],
                    "message": "PDF 解析失败",
                },
            ]
        }


class ExportPageItem(BaseModel):
    """导出页面项

    Requirements: 5.1
    """

    filename: str = Field(..., description="文件名", min_length=1)
    data: str = Field(..., description="Base64 编码的图片数据", min_length=1)
    rotation: int = Field(..., description="旋转角度")
    source_type: str = Field(..., description="来源类型: image 或 pdf_page")

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: int) -> int:
        """验证旋转角度必须是 0, 90, 180, 270 之一"""
        valid_rotations = {0, 90, 180, 270}
        if v not in valid_rotations:
            raise ValueError(f"旋转角度必须是 {valid_rotations} 之一")
        return v

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        """验证来源类型"""
        valid_types = {"pdf", "image"}
        if v not in valid_types:
            raise ValueError(f"来源类型必须是 {valid_types} 之一")
        return v


class ExportPDFRequestSchema(BaseModel):
    """PDF 导出请求

    Requirements: 5.1
    """

    pages: list[ExportPageItem] = Field(..., description="页面列表", min_length=1)
    paper_size: str = Field(
        "original",
        description="输出纸张尺寸: original(原始), a4, a3, letter",
    )

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, v: list[ExportPageItem]) -> list[ExportPageItem]:
        """验证页面列表"""
        if not v:
            raise ValueError("页面列表不能为空")
        return v

    @field_validator("paper_size")
    @classmethod
    def validate_paper_size(cls, v: str) -> str:
        """验证纸张尺寸"""
        valid_sizes: tuple[str, ...] = (("A4", "A3", "B4", "B5"),)  # type: ignore[assignment]
        if v.lower() not in valid_sizes:
            raise ValueError(f"不支持的纸张尺寸: {v},可选: {', '.join(valid_sizes)}")
        return v.lower()


class ExportPDFResponseSchema(BaseModel):
    """PDF 导出响应

    Requirements: 5.1
    """

    success: bool = Field(..., description="是否成功")
    pdf_url: str | None = Field(None, description="PDF 文件下载 URL")
    message: str | None = Field(None, description="响应消息")

    class Config:
        json_schema_extra: ClassVar = {
            "examples": [
                {
                    "success": True,
                    "pdf_url": "/media/image_rotation/rotated_pages_20250101_120000.pdf",
                    "message": None,
                },
                {
                    "success": False,
                    "pdf_url": None,
                    "message": "PDF 生成失败",
                },
            ]
        }


class PDFPageItemSimple(BaseModel):
    """PDF 页面项(简化版,不含方向检测结果)"""

    page_number: int = Field(..., description="页码(从 1 开始)", ge=1)
    data: str = Field(..., description="Base64 编码的页面图片(含 data URL 前缀)")
    rotation: int = Field(0, description="旋转角度(默认 0)")
    width: int = Field(..., description="页面宽度", gt=0)
    height: int = Field(..., description="页面高度", gt=0)


class PDFExtractFastResponseSchema(BaseModel):
    """PDF 快速提取响应(不含方向检测)"""

    success: bool = Field(..., description="是否成功")
    filename: str = Field(..., description="原始文件名")
    pages: list[PDFPageItemSimple] = Field(default_factory=list, description="页面列表")
    message: str | None = Field(None, description="响应消息")


class DetectPageOrientationRequestSchema(BaseModel):
    """单页方向检测请求"""

    data: str = Field(..., description="Base64 编码的图片数据(可含 data URL 前缀)", min_length=1)


class DetectPageOrientationResponseSchema(BaseModel):
    """单页方向检测响应"""

    rotation: int = Field(..., description="需要旋转的角度 (0, 90, 180, 270)")
    confidence: float = Field(0, description="置信度")
    method: str = Field("none", description="检测方法")
    error: str | None = Field(None, description="错误信息")


# ============================================================================
# 图片自动重命名 Schemas
# ============================================================================


class RenameRequestItem(BaseModel):
    """单个重命名请求项

    Requirements: 4.1
    """

    filename: str = Field(..., description="原始文件名", min_length=1)
    ocr_text: str = Field(..., description="OCR 识别的文本内容")


class SuggestRenameRequestSchema(BaseModel):
    """重命名建议请求

    Requirements: 4.1, 4.2
    """

    items: list[RenameRequestItem] = Field(..., description="重命名请求项列表", min_length=1)

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[RenameRequestItem]) -> list[RenameRequestItem]:
        """验证请求项列表"""
        if not v:
            raise ValueError("请求项列表不能为空")
        return v


class RenameSuggestionItem(BaseModel):
    """单个重命名建议

    Requirements: 4.3
    """

    original_filename: str = Field(..., description="原始文件名")
    suggested_filename: str = Field(..., description="建议的新文件名")
    date: str | None = Field(None, description="提取的日期 (YYYYMMDD 格式)")
    amount: str | None = Field(None, description="提取的金额 (如 65500元)")
    success: bool = Field(True, description="是否成功提取")
    error: str | None = Field(None, description="错误信息")


class SuggestRenameResponseSchema(BaseModel):
    """重命名建议响应

    Requirements: 4.1, 4.3
    """

    success: bool = Field(..., description="是否成功")
    suggestions: list[RenameSuggestionItem] = Field(default_factory=list, description="重命名建议列表")

    class Config:
        json_schema_extra: ClassVar = {
            "examples": [
                {
                    "success": True,
                    "suggestions": [
                        {
                            "original_filename": "IMG_001.jpg",
                            "suggested_filename": "20250630_65500元.jpg",
                            "date": "20250630",
                            "amount": "65500元",
                            "success": True,
                            "error": None,
                        },
                        {
                            "original_filename": "IMG_002.jpg",
                            "suggested_filename": "20250701.jpg",
                            "date": "20250701",
                            "amount": None,
                            "success": True,
                            "error": None,
                        },
                    ],
                },
                {
                    "success": True,
                    "suggestions": [
                        {
                            "original_filename": "IMG_003.jpg",
                            "suggested_filename": "IMG_003.jpg",
                            "date": None,
                            "amount": None,
                            "success": False,
                            "error": "无法提取日期和金额信息",
                        }
                    ],
                },
            ]
        }
