"""要素式转换 Service 层。"""

from __future__ import annotations

import logging
from pathlib import Path

from apps.doc_convert.constants import MbidDefinition, get_mbid_by_category, get_mbid_set
from apps.doc_convert.exceptions import (
    FileTooLargeError,
    InvalidFileTypeError,
    InvalidMbidError,
    ZnszjInvalidResponseError,
    ZnszjUnavailableError,
)
from apps.doc_convert.services.znszj_loader import ZnszjClientProtocol

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: list[str] = [".docx", ".doc", ".pdf"]
MAX_FILE_SIZE_MB: int = 20
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024


class DocConvertService:
    """要素式转换业务逻辑层。"""

    def __init__(self, znszj_client: ZnszjClientProtocol) -> None:
        self._client = znszj_client

    def get_mbid_list(self) -> dict[str, list[MbidDefinition]]:
        """获取文书类型列表，按类别分组。"""
        return get_mbid_by_category()

    def convert_document(
        self,
        *,
        file_content: bytes,
        filename: str,
        mbid: str,
    ) -> bytes:
        """
        转换文书。

        Args:
            file_content: 文件二进制内容
            filename: 原始文件名
            mbid: 文书类型标识符

        Returns:
            转换后的 .docx 文件字节

        Raises:
            InvalidFileTypeError: 文件扩展名不支持
            InvalidMbidError: mbid 不在支持列表中
            FileTooLargeError: 文件超过 20MB
            ZnszjUnavailableError: znszj 系统不可达
            ZnszjInvalidResponseError: znszj 返回格式异常
        """
        # 验证文件扩展名
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise InvalidFileTypeError(filename=filename, allowed_extensions=ALLOWED_EXTENSIONS)

        # 验证 mbid
        if mbid not in get_mbid_set():
            raise InvalidMbidError(mbid=mbid)

        # 验证文件大小
        size_bytes = len(file_content)
        if size_bytes > MAX_FILE_SIZE_BYTES:
            size_mb = size_bytes / (1024 * 1024)
            raise FileTooLargeError(size_mb=size_mb, max_size_mb=MAX_FILE_SIZE_MB)

        # 调用 znszj 客户端
        try:
            result = self._client.convert_document(
                file_content=file_content,
                filename=filename,
                mbid=mbid,
            )
        except (ZnszjUnavailableError, ZnszjInvalidResponseError):
            raise
        except Exception as exc:
            logger.exception(
                "znszj 转换失败",
                extra={"mbid": mbid, "doc_filename": filename, "error": str(exc)},
            )
            raise ZnszjUnavailableError(detail=str(exc)) from exc

        return result
