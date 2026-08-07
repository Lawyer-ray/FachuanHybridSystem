"""TextinParse API 后端实现

基于 xparse-client SDK，与 MinerU 后端平级，复用同一套 DocumentParsingTask / Admin / API 体系。
SDK 内部使用 httpx，与仓库风格一致。

流程（异步路径，由 Django-Q worker 调用）：
    create_job(file) → job_id
    → 轮询 get_job(job_id) 直到终态
    → 下载 result_url 的 JSON（ParseResponse 结构）
    → 转换为 ParsedDocument
"""

import logging
import time
from pathlib import Path
from typing import Any

import httpx
import xparse_client as xc

from apps.core.services.system_config_service import SystemConfigService
from apps.document_parsing.exceptions import (
    DocumentParsingError,
    FileFormatNotSupportedError,
    ParsingTimeoutError,
    TextinAPIError,
)
from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult
from apps.document_parsing.services.backends._page_artifacts import (
    clean_page_artifacts,
    collect_header_texts,
    strip_markdown_emphasis,
)

logger = logging.getLogger(__name__)
_config_service = SystemConfigService()


class TextinBackend:
    """TextinParse API 后端

    通过 TextinParse 云服务（xparse-client SDK）解析文档，支持
    PDF / DOC / DOCX / PPT / PPTX / XLS / XLSX / 图片 / OFD / RTF / HTML / CSV / TXT 等格式。
    """

    # 固定的配置（不需要用户管理）
    POLL_INTERVAL = 2  # 轮询间隔（秒）
    POLL_TIMEOUT = 300  # 轮询总超时（秒）
    HTTP_TIMEOUT = 30  # 单次 HTTP 请求超时（秒）
    RESULT_DOWNLOAD_TIMEOUT = 60  # 结果文件下载超时（秒）

    # 后端能力声明：云端后端含 HTTP 上传 + 轮询，阻塞时间长，需异步执行
    requires_async_execution: bool = True

    def __init__(
        self,
        app_id: str | None = None,
        secret_code: str | None = None,
        *,
        timeout: int = HTTP_TIMEOUT,
    ):
        """初始化 TextinParse 后端

        Args:
            app_id: TextinParse App ID。如果未提供，从 SystemConfig 读取
            secret_code: TextinParse Secret Code。如果未提供，从 SystemConfig 读取
            timeout: SDK HTTP 请求超时时间（秒）
        """
        self.app_id = app_id or _config_service.get_value_internal("TEXTIN_APP_ID")
        self.secret_code = secret_code or _config_service.get_value_internal("TEXTIN_SECRET_CODE")

        if not self.app_id or not self.secret_code:
            raise ValueError(
                "未配置 TextinParse 凭证。"
                "请在 SystemConfig 中设置 TEXTIN_APP_ID 和 TEXTIN_SECRET_CODE"
                "（http://127.0.0.1:8002/admin/core/systemconfig/）"
            )

        self.timeout = timeout

        try:
            self._client = xc.XParseClient(
                app_id=self.app_id,
                secret_code=self.secret_code,
                timeout=float(self.timeout),
            )
        except xc.XParseClientError as e:
            raise TextinAPIError(f"初始化 TextinParse SDK 失败: {e}") from e

        logger.info("初始化 TextinParse 后端: timeout=%ds", self.timeout)

    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """通过 TextinParse API 解析文档

        Args:
            file_path: 文件路径
            file_type: 文件类型（用于校验，SDK 通过文件名后缀自动识别）
            extract_tables: 是否提取表格结构
            extract_images: 是否提取图片数据
            return_markdown: 是否返回 Markdown
            **kwargs: 其他参数（保留兼容性）

        Returns:
            ParsedDocument 解析结果
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        start_time = time.time()
        logger.info("开始 TextinParse 解析: %s", file_path)

        try:
            # 1. 创建异步解析任务
            job_id = self._create_job(file_path_obj, extract_tables=extract_tables)

            # 2. 轮询任务直到终态
            job_result = self._poll_job(job_id)

            # 3. 下载并解析结果
            parsed = self._parse_result(
                job_result,
                return_markdown=return_markdown,
                extract_images=extract_images,
            )

            duration = time.time() - start_time
            logger.info(
                "TextinParse 解析完成: %s (%.2fs, %d 字符)",
                file_path,
                duration,
                len(parsed.text),
            )

            return parsed

        except (TextinAPIError, ParsingTimeoutError, FileFormatNotSupportedError):
            raise
        except xc.XParseClientError as e:
            logger.error("TextinParse 解析失败: %s - %s", file_path, str(e))
            raise self._wrap_sdk_error(e) from e
        except Exception as e:
            logger.error("TextinParse 解析失败: %s - %s", file_path, str(e))
            raise TextinAPIError(f"TextinParse 解析失败: {e}") from e

    def extract_text(
        self,
        file_path: str,
        max_length: int | None = None,
        **kwargs: Any,
    ) -> TextExtractionResult:
        """提取文档纯文本

        Args:
            file_path: 文件路径
            max_length: 最大文本长度

        Returns:
            TextExtractionResult 提取结果
        """
        try:
            parsed = self.parse_document(
                file_path=file_path,
                extract_tables=False,
                extract_images=False,
                return_markdown=False,
                **kwargs,
            )

            text = parsed.text
            if max_length and len(text) > max_length:
                text = text[:max_length]

            return TextExtractionResult(
                text=text,
                success=True,
                method="textin",
                metadata=parsed.metadata,
            )

        except Exception as e:
            logger.error("TextinParse 文本提取失败: %s - %s", file_path, str(e))
            return TextExtractionResult(
                text="",
                success=False,
                method="textin",
                metadata={"error": str(e)},
            )

    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格式

        TextinParse 支持的格式比 MinerU 更广，包含 OFD / RTF / HTML / CSV / TXT。
        """
        return [
            "pdf",
            "doc",
            "docx",
            "ppt",
            "pptx",
            "xls",
            "xlsx",
            "jpg",
            "jpeg",
            "png",
            "bmp",
            "gif",
            "tiff",
            "webp",
            "ofd",
            "rtf",
            "html",
            "csv",
            "txt",
        ]

    # ── 内部方法 ──────────────────────────────────────────────

    def _create_job(self, file_path: Path, *, extract_tables: bool = True) -> str:
        """创建异步解析任务

        Args:
            file_path: 文件路径
            extract_tables: 是否提取表格结构

        Returns:
            job_id 任务 ID

        Raises:
            TextinAPIError: 任务创建失败
            FileFormatNotSupportedError: 不支持的文件格式
        """
        try:
            # 构建 Capabilities 配置
            capabilities = xc.Capabilities(
                include_table_structure=extract_tables,
                title_tree=True,
            )
            config = xc.ParseConfig(capabilities=capabilities)

            with open(file_path, "rb") as f:
                job_response = self._client.parse.create_job(
                    file=f,
                    filename=file_path.name,
                    config=config,
                )

            job_id: str = str(job_response.job_id)
            logger.info(
                "TextinParse 任务已创建: %s (job_id=%s)",
                file_path.name,
                job_id,
            )
            return job_id

        except xc.XParseClientError as e:
            raise self._wrap_sdk_error(e) from e

    def _poll_job(self, job_id: str) -> xc.JobStatusResponse:
        """轮询任务状态直到终态

        与 SDK 内置的 wait_job 相比，这里显式处理 partial_completed / stopped / deleted
        等终态（SDK 的 wait_job 只认 completed/failed，其他终态会一直轮询到超时）。

        Args:
            job_id: 任务 ID

        Returns:
            JobStatusResponse 终态响应

        Raises:
            ParsingTimeoutError: 轮询超时
            TextinAPIError: 任务失败
        """
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.POLL_TIMEOUT:
                raise ParsingTimeoutError(f"任务超时 ({self.POLL_TIMEOUT}秒): job_id={job_id}")

            try:
                result = self._client.parse.get_job(job_id=job_id)
            except xc.XParseClientError as e:
                raise self._wrap_sdk_error(e) from e

            status = result.status

            if status == "completed":
                logger.info("TextinParse 任务完成: %s", job_id)
                return result

            if status == "partial_completed":
                # 部分完成，仍然返回可用的结果
                logger.info(
                    "TextinParse 任务部分完成: %s (error_message=%s)",
                    job_id,
                    result.error_message,
                )
                return result

            if status in ("failed", "stopped", "deleted"):
                err_msg = result.error_message or "未知错误"
                raise TextinAPIError(
                    f"任务失败 (status={status}): {err_msg}",
                )

            # pending / running / 其他非终态 — 继续轮询
            logger.debug(
                "任务进行中: job_id=%s (status=%s, elapsed=%.1fs)",
                job_id,
                status,
                elapsed,
            )
            time.sleep(self.POLL_INTERVAL)

    def _parse_result(
        self,
        job_result: xc.JobStatusResponse,
        *,
        return_markdown: bool = False,
        extract_images: bool = False,
    ) -> ParsedDocument:
        """下载并解析结果

        Args:
            job_result: 终态任务响应（含 result_url）
            return_markdown: 是否包含 Markdown
            extract_images: 是否包含图片数据

        Returns:
            ParsedDocument 解析结果
        """
        if not job_result.result_url:
            raise TextinAPIError(
                f"任务完成但未返回 result_url (job_id={job_result.job_id})",
            )

        try:
            # 下载结果 JSON（ParseResponse 结构）
            response = httpx.get(
                job_result.result_url,
                timeout=self.RESULT_DOWNLOAD_TIMEOUT,
            )
            response.raise_for_status()
            result_data = response.json()

        except httpx.HTTPError as e:
            raise TextinAPIError(f"下载结果文件失败: {e}") from e
        except ValueError as e:
            raise TextinAPIError(f"解析结果 JSON 失败: {e}") from e

        # ParseResponse 结构：{markdown, elements, metadata, success_count, ...}
        markdown = result_data.get("markdown", "") or ""
        elements = result_data.get("elements", []) or []
        metadata = result_data.get("metadata", {}) or {}
        success_count = result_data.get("success_count", 0) or 0

        # 清理 markdown：删除 HTML 注释、独立数字行（页码）和已知页眉文本
        header_texts = collect_header_texts(elements, header_type="Header")
        markdown = clean_page_artifacts(markdown, exclude_lines=header_texts)

        # 提取纯文本：从 elements 拼接正文块（已排除 Footer 页码）
        text = self._extract_text_from_elements(elements)

        # fallback 到 markdown（去标记的简单处理，markdown 已清理页码）
        if not text and markdown:
            text = markdown

        # 可选 Markdown
        md_output = markdown if return_markdown else None

        # 元数据
        parsed_metadata: dict[str, Any] = {
            "task_id": None,  # 会在上层设置
            "job_id": job_result.job_id,
            "file_id": job_result.file_id,
            "success_count": success_count,
            "page_count": metadata.get("page_count", 0) if isinstance(metadata, dict) else 0,
            "has_images": extract_images
            and any(el.get("type") in ("image", "inline_object") for el in elements if isinstance(el, dict)),
            "element_count": len(elements),
        }

        return ParsedDocument(
            text=text,
            markdown=md_output,
            images=None,  # TextinParse 当前不导出本地图片文件
            metadata=parsed_metadata,
            parse_method="textin",
        )

    # 正文类型：NarrativeText（正文段落）、Title（标题）
    # 明确排除：Footer（页脚/页码）、Header（页眉）等非正文类型
    _TEXT_ELEMENT_TYPES = frozenset({"NarrativeText", "Title"})
    # 非正文元素类型（页眉页脚，fallback 路径排除）
    _EXCLUDED_ELEMENT_TYPES = frozenset({"Footer", "Header"})

    def _extract_text_from_elements(self, elements: list[Any]) -> str:
        """从 elements 列表提取纯文本（排除页眉页脚）

        TextinParse 元素类型参考 xparse-client parse.py 及实测：
        - NarrativeText / Title：正文和标题，保留
        - Footer：页脚（通常为页码），排除
        - Header：页眉，排除
        - Table / Image：结构化数据，不在纯文本中拼接

        Args:
            elements: ParseResponse.elements 列表（dict 形式）

        Returns:
            拼接后的纯文本（不含页眉页脚）
        """
        if not elements:
            return ""

        texts: list[str] = []

        # 第一轮：只取正文/标题类型，排除 Footer（页脚）和 Header（页眉）
        for el in elements:
            if not isinstance(el, dict):
                continue
            el_type = el.get("type")
            if el_type in self._TEXT_ELEMENT_TYPES:
                el_text = el.get("text", "")
                if el_text:
                    texts.append(strip_markdown_emphasis(el_text))

        # fallback：如果没拿到任何正文块，取所有非 Footer/Header 且有 text 的元素
        # （避免完全无输出，但仍排除页眉页脚）
        if not texts:
            for el in elements:
                if not isinstance(el, dict):
                    continue
                if el.get("type") in self._EXCLUDED_ELEMENT_TYPES:
                    continue
                el_text = el.get("text", "")
                if el_text:
                    texts.append(strip_markdown_emphasis(el_text))

        return "\n".join(texts)

    def _wrap_sdk_error(self, error: xc.XParseClientError) -> DocumentParsingError:
        """将 SDK 异常映射为项目内部异常

        Args:
            error: xparse_client SDK 抛出的异常

        Returns:
            项目内部的 DocumentParsingError 子类
        """
        message = str(error)

        if isinstance(error, xc.AuthenticationError):
            return TextinAPIError(f"TextinParse 认证失败: {message}")
        if isinstance(error, xc.InsufficientBalanceError):
            return TextinAPIError(f"TextinParse 余额不足: {message}")
        if isinstance(error, xc.PasswordProtectedError):
            return TextinAPIError(f"TextinParse 文件密码保护: {message}")
        if isinstance(error, xc.CorruptedFileError):
            return TextinAPIError(f"TextinParse 文件损坏: {message}")
        if isinstance(error, xc.UnsupportedFileTypeError):
            return FileFormatNotSupportedError(f"TextinParse 不支持的文件格式: {message}")
        if isinstance(error, xc.FileSizeError):
            return TextinAPIError(f"TextinParse 文件过大: {message}")
        if isinstance(error, xc.RateLimitError):
            return TextinAPIError(f"TextinParse 限流: {message}")
        if isinstance(error, xc.RequestTimeoutError):
            return ParsingTimeoutError(f"TextinParse 请求超时: {message}")
        if isinstance(error, xc.APIError):
            return TextinAPIError(f"TextinParse API 调用失败: {message}")
        if isinstance(error, xc.ConfigurationError):
            return TextinAPIError(f"TextinParse SDK 配置错误: {message}")

        return TextinAPIError(f"TextinParse 解析失败: {message}")
