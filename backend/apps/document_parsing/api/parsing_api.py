"""文档解析 Ninja API 接口"""

import logging
from pathlib import Path
from typing import Optional

from ninja import File, Router, UploadedFile

from apps.core.security.auth import JWTOrSessionAuth
from apps.document_parsing.schemas.parsing_schemas import (
    ParseDocumentRequest,
    ParseDocumentResponse,
    ExtractTextRequest,
    ExtractTextResponse,
)
from apps.document_parsing.services import get_document_parser

logger = logging.getLogger(__name__)

router = Router()


@router.post(
    "/parse",
    response=ParseDocumentResponse,
    summary="解析文档",
    auth=JWTOrSessionAuth(),
)
def parse_document(request, file: UploadedFile = File(...), body: ParseDocumentRequest = None):
    """解析上传的文档，返回结构化的解析结果

    支持的文件格式：PDF、DOC、DOCX、PPT、PPTX、XLS、XLSX、JPG、PNG 等
    """
    try:
        # 保存上传的文件
        upload_dir = Path("media/document_parsing/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / file.name
        with open(file_path, "wb") as f:
            for chunk in file.chunks():
                f.write(chunk)

        # 获取解析参数
        backend = body.backend if body else "auto"
        extract_tables = body.extract_tables if body is not None else True
        extract_images = body.extract_images if body is not None else False
        return_markdown = body.return_markdown if body is not None else True

        # 解析文档
        parser = get_document_parser(backend=backend)
        result = parser.parse_document(
            file_path=str(file_path),
            file_type=Path(file.name).suffix.lstrip("."),
            extract_tables=extract_tables,
            extract_images=extract_images,
            return_markdown=return_markdown,
        )

        return ParseDocumentResponse(
            success=True,
            text=result.text,
            markdown=result.markdown,
            metadata=result.metadata or {},
            parse_method=result.parse_method,
        )

    except Exception as e:
        logger.error("文档解析失败: %s", str(e))
        return ParseDocumentResponse(
            success=False,
            error=str(e),
        )


@router.post(
    "/extract-text",
    response=ExtractTextResponse,
    summary="提取文档文本",
    auth=JWTOrSessionAuth(),
)
def extract_text(request, file: UploadedFile = File(...), body: ExtractTextRequest = None):
    """提取文档的纯文本内容"""
    try:
        # 保存上传的文件
        upload_dir = Path("media/document_parsing/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / file.name
        with open(file_path, "wb") as f:
            for chunk in file.chunks():
                f.write(chunk)

        # 获取参数
        backend = body.backend if body else "auto"
        max_length = body.max_length if body is not None else None

        # 提取文本
        parser = get_document_parser(backend=backend)
        result = parser.extract_text(
            file_path=str(file_path),
            max_length=max_length,
        )

        return ExtractTextResponse(
            success=result.success,
            text=result.text,
            method=result.method,
            metadata=result.metadata or {},
        )

    except Exception as e:
        logger.error("文本提取失败: %s", str(e))
        return ExtractTextResponse(
            success=False,
            text="",
            error=str(e),
        )
