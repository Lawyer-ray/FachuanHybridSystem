"""要素式转换 Service 层。"""

from __future__ import annotations

import logging
from pathlib import Path

from apps.doc_convert.constants import MbidDefinition, get_mbid_by_category, get_mbid_set
from apps.doc_convert.exceptions import (
    FileCorruptedError,
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

        # 验证文件内容可解析（扩展名对但内容是坏的，最常见的是改了后缀的文本、
        # 传输中断的半截文件、加密过的 docx）。
        #
        # ⚠️ 必须在调 znszj 之前做：那种文件会让 znszj 侧抛异常，被下面的
        # `except Exception` 收成 ZnszjUnavailableError（502），
        # 明明是「你这个文件坏了」却报成「服务挂了」。
        assert_parsable(file_content, filename, suffix)

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


def assert_parsable(content: bytes, filename: str, suffix: str) -> None:
    """文件内容能否被正常打开。打不开抛 FileCorruptedError（400）。

    只做「最轻的一个动作」：docx 走 zipfile 目录、pdf 读 header。
    不真去解析文档结构——那交给 znszj，这里只负责把明显坏掉的文件挡在外面。

    ═══ 为什么这道校验必须在调 znszj 之前 ═══
    扩展名对、内容坏（改了后缀的文本、传输中断的半截文件、加密过的 docx）
    能通过扩展名校验，到 znszj 侧才炸，然后被 `except Exception` 收成
    ZnszjUnavailableError（502）。502 的语义是「上游服务挂了」——
    网关会当故障、律师会去报障，而真实原因只是这一个文件打不开。
    """
    if not content:
        raise FileCorruptedError(filename=filename, detail="empty file")

    try:
        if suffix in (".docx", ".doc"):
            # .doc 老格式是 OLE2 复合文档，不是 zip；交给 znszj 处理
            if content[:8].startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
                return
            import io
            import zipfile

            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
            # 合法 docx 必须有 word/document.xml
            if not any(n.endswith("document.xml") for n in names):
                raise FileCorruptedError(filename=filename, detail="no word/document.xml")
        elif suffix == ".pdf":
            if not content[:5].startswith(b"%PDF"):
                raise FileCorruptedError(filename=filename, detail="bad pdf header")
    except FileCorruptedError:
        raise
    except Exception as exc:
        # zipfile.BadZipFile / 读取越界等
        raise FileCorruptedError(filename=filename, detail=str(exc)[:200]) from exc
