"""MinerU API 后端实现"""

import logging
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from apps.core.http.httpx_clients import get_async_http_client, get_sync_http_client
from apps.core.services.system_config_service import SystemConfigService
from apps.document_parsing.exceptions import MineruAPIError, ParsingTimeoutError
from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult

logger = logging.getLogger(__name__)
_config_service = SystemConfigService()


class MineruBackend:
    """MinerU API 后端

    通过 MinerU 云服务解析文档，支持 PDF、DOC、PPT、Excel、图片等格式。
    """

    # 固定的配置（不需要用户管理）
    API_URL = "https://mineru.net/api/v4/extract/task"
    BATCH_URL = "https://mineru.net/api/v4/file-urls/batch"
    MODEL_VERSION = "vlm"
    POLL_INTERVAL = 2  # 轮询间隔（秒）
    POLL_TIMEOUT = 300  # 超时时间（秒）

    BATCH_RESULTS_URL = "https://mineru.net/api/v4/extract-results/batch"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
    ):
        """初始化 MinerU 后端

        Args:
            api_key: MinerU API Key（Bearer Token）。如果未提供，从 SystemConfig 读取
            timeout: HTTP 请求超时时间（秒）
        """
        self.api_key = api_key or _config_service.get_value_internal("MINERU_API_KEY")
        if not self.api_key:
            raise ValueError(
                "未配置 MinerU API Key。"
                "请在 SystemConfig 中设置 MINERU_API_KEY（http://127.0.0.1:8002/admin/core/systemconfig/）"
            )

        self.timeout = timeout

        logger.info(
            "初始化 MinerU 后端: timeout=%ds",
            self.timeout,
        )

    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """通过 MinerU API 解析文档

        Args:
            file_path: 文件路径
            file_type: 文件类型
            extract_tables: 是否提取表格（MinerU 默认提取）
            extract_images: 是否提取图片
            return_markdown: 是否返回 Markdown
            **kwargs: 其他参数

        Returns:
            ParsedDocument 解析结果
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        start_time = time.time()
        logger.info("开始 MinerU 解析: %s", file_path)

        try:
            # 1. 上传文件到 MinerU（上传后 MinerU 自动创建解析任务）
            batch_id = self._upload_file(file_path)

            # 2. 轮询批量结果
            result = self._poll_batch_result(batch_id)

            # 3. 下载并解析 ZIP 结果
            parsed = self._parse_result_zip(
                result["full_zip_url"],
                return_markdown=return_markdown,
                extract_images=extract_images,
            )

            duration = time.time() - start_time
            logger.info(
                "MinerU 解析完成: %s (%.2fs, %d 字符)",
                file_path,
                duration,
                len(parsed.text),
            )

            return parsed

        except (MineruAPIError, ParsingTimeoutError):
            raise
        except Exception as e:
            logger.error("MinerU 解析失败: %s - %s", file_path, str(e))
            raise MineruAPIError(f"MinerU 解析失败: {e}") from e

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
                method="mineru",
                metadata=parsed.metadata,
            )

        except Exception as e:
            logger.error("MinerU 文本提取失败: %s - %s", file_path, str(e))
            return TextExtractionResult(
                text="",
                success=False,
                method="mineru",
                metadata={"error": str(e)},
            )

    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格式"""
        return ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "jpg", "jpeg", "png"]

    def _upload_file(self, file_path: str) -> str:
        """上传文件到 MinerU，上传后 MinerU 自动创建解析任务

        Args:
            file_path: 本地文件路径

        Returns:
            batch_id（用于查询解析结果）
        """
        file_path_obj = Path(file_path)
        file_name = file_path_obj.name

        client = get_sync_http_client()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "files": [{"name": file_name, "data_id": uuid4().hex}],
            "model_version": self.MODEL_VERSION,
        }

        try:
            response = client.post(
                self.BATCH_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()

            logger.debug("batch API 响应: %s", result)

            if result.get("code") != 0:
                raise MineruAPIError(f"获取上传 URL 失败: {result.get('msg', '未知错误')}")

            batch_id: str = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]

            if not urls:
                raise MineruAPIError("未获取到上传 URL")

            upload_url = urls[0]

            # 上传文件到预签名 URL（不设置 Content-Type，签名不包含此 header）
            with open(file_path, "rb") as f:
                upload_response = client.put(
                    upload_url,
                    content=f.read(),
                    timeout=self.timeout,
                )
                upload_response.raise_for_status()

            logger.info("文件上传成功: %s (batch_id=%s)", file_name, batch_id)

            return batch_id

        except httpx.HTTPError as e:
            raise MineruAPIError(f"HTTP 请求失败: {e}") from e

    def _poll_batch_result(self, batch_id: str) -> dict:
        """轮询批量任务结果

        上传文件后 MinerU 自动创建解析任务，通过 batch_id 查询结果。

        Args:
            batch_id: 批次 ID（从 _upload_file 获取）

        Returns:
            包含 full_zip_url 的结果字典

        Raises:
            ParsingTimeoutError: 超时
            MineruAPIError: 任务失败
        """
        client = get_sync_http_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        url = f"{self.BATCH_RESULTS_URL}/{batch_id}"
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.POLL_TIMEOUT:
                raise ParsingTimeoutError(f"任务超时 ({self.POLL_TIMEOUT}秒): batch_id={batch_id}")

            try:
                response = client.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("code") != 0:
                    raise MineruAPIError(f"查询结果失败: {result.get('msg', '未知错误')}")

                extract_results = result.get("data", {}).get("extract_result", [])
                if not extract_results:
                    logger.debug("批量结果为空，等待中 (elapsed=%.1fs)", elapsed)
                    time.sleep(self.POLL_INTERVAL)
                    continue

                # 取第一个文件的结果
                file_result: dict = extract_results[0]
                state = file_result.get("state", "")

                if state == "done":
                    logger.info("MinerU 批量任务完成: %s", batch_id)
                    return file_result

                elif state == "failed":
                    err_msg = file_result.get("err_msg", "未知错误")
                    raise MineruAPIError(f"任务失败: {err_msg}")

                # waiting-file / pending / running — 继续轮询
                logger.debug(
                    "任务进行中: batch_id=%s (state=%s, elapsed=%.1fs)",
                    batch_id,
                    state,
                    elapsed,
                )
                time.sleep(self.POLL_INTERVAL)

            except MineruAPIError:
                raise
            except httpx.HTTPError as e:
                logger.warning("轮询请求失败: %s，将重试", e)
                time.sleep(self.POLL_INTERVAL)

    def _parse_result_zip(
        self,
        zip_url: str,
        return_markdown: bool = False,
        extract_images: bool = False,
    ) -> ParsedDocument:
        """下载并解析结果 ZIP 文件

        Args:
            zip_url: ZIP 文件 URL
            return_markdown: 是否包含 Markdown
            extract_images: 是否包含图片

        Returns:
            ParsedDocument 解析结果
        """
        client = get_sync_http_client()

        try:
            # 下载 ZIP
            response = client.get(zip_url, timeout=self.timeout)
            response.raise_for_status()

            # 解析 ZIP
            with tempfile.TemporaryDirectory() as tmp_dir:
                zip_path = Path(tmp_dir) / "result.zip"
                zip_path.write_bytes(response.content)

                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmp_dir)

                # 查找关键文件
                md_file = None
                content_list_file = None
                image_files = []

                for f in Path(tmp_dir).rglob("*"):
                    if f.suffix == ".md":
                        md_file = f
                    elif f.name.endswith("_content_list.json"):
                        content_list_file = f
                    elif f.suffix in (".jpg", ".jpeg", ".png"):
                        image_files.append(f)

                # 收集已知页眉文本（用于清理 markdown 残留）
                header_texts: list[str] = []
                if content_list_file:
                    header_texts = self._collect_header_texts_from_content_list(content_list_file)

                # 提取文本
                text = ""
                if content_list_file:
                    text = self._extract_text_from_content_list(content_list_file)
                elif md_file:
                    # fallback 到 markdown，需清理页眉页码
                    text = self._clean_page_artifacts(md_file.read_text(encoding="utf-8"), exclude_lines=header_texts)

                # 提取 Markdown
                markdown = None
                if return_markdown and md_file:
                    markdown = self._clean_page_artifacts(
                        md_file.read_text(encoding="utf-8"), exclude_lines=header_texts
                    )

                # 提取图片路径
                images = None
                if extract_images:
                    images = [str(f) for f in image_files]

                # 提取元数据
                metadata = {
                    "task_id": None,  # 会在上层设置
                    "has_images": len(image_files) > 0,
                    "image_count": len(image_files),
                }

                return ParsedDocument(
                    text=text,
                    markdown=markdown,
                    images=images,
                    metadata=metadata,
                    parse_method="mineru",
                )

        except zipfile.BadZipFile as e:
            raise MineruAPIError(f"结果 ZIP 文件损坏: {e}") from e
        except Exception as e:
            raise MineruAPIError(f"解析结果失败: {e}") from e

    def _extract_text_from_content_list(self, content_list_path: Path) -> str:
        """从 content_list.json 提取文本（排除页眉页脚）

        MinerU 将页眉识别为 header 类型、页脚为 footer、页码为 page_number，
        但部分页眉会被误识别为 text 类型。通过归一化匹配（去除标点后比较）
        过滤被误识别的页眉。

        Args:
            content_list_path: content_list.json 文件路径

        Returns:
            提取的文本（不含页眉页脚）
        """
        import json

        try:
            with open(content_list_path, encoding="utf-8") as f:
                content_list = json.load(f)

            # 收集 header/footer 类型的归一化文本（已知页眉页脚）
            excluded_norm: set[str] = set()
            for block in content_list:
                if block.get("type") in ("header", "footer"):
                    text = (block.get("text") or "").strip()
                    if text:
                        excluded_norm.add(self._normalize_text(text))

            # 提取 text 块，跳过匹配已知页眉页脚的
            texts = []
            for block in content_list:
                block_type = block.get("type", "")
                block_text = block.get("text", "")

                if block_type == "text" and block_text:
                    # 归一化后检查是否匹配已知页眉页脚
                    if self._normalize_text(block_text) in excluded_norm:
                        continue
                    texts.append(block_text)

            return "\n".join(texts)

        except Exception as e:
            logger.warning("解析 content_list.json 失败: %s", e)
            return ""

    def _collect_header_texts_from_content_list(self, content_list_path: Path) -> list[str]:
        """从 content_list.json 收集 header 类型的文本（用于清理 markdown）

        markdown 输出路径直接读取 md 文件，会包含页眉文本，
        需收集已知页眉后从 markdown 中删除。

        Args:
            content_list_path: content_list.json 文件路径

        Returns:
            页眉文本列表（去重）
        """
        import json

        try:
            with open(content_list_path, encoding="utf-8") as f:
                content_list = json.load(f)
        except Exception as e:
            logger.warning("读取 content_list.json 失败: %s", e)
            return []

        header_texts: list[str] = []
        seen: set[str] = set()
        for block in content_list:
            if block.get("type") != "header":
                continue
            text = (block.get("text") or "").strip()
            if text and text not in seen:
                seen.add(text)
                header_texts.append(text)
        return header_texts

    # 归一化正则：去除标点和空白，只保留字母数字汉字（用于页眉模糊匹配）
    _NORMALIZE_RE = re.compile(r"[^\w\u4e00-\u9fff]")

    def _normalize_text(self, text: str) -> str:
        """归一化文本：去除标点和空白，只保留字母数字汉字

        用于页眉模糊匹配（如"大笨蛋，蠢猪" vs "大笨蛋、蠢猪"归一化后相同）。
        """
        return self._NORMALIZE_RE.sub("", text)

    # 独立成行的纯数字（页码）：仅匹配行首到行尾只有数字的行
    _STANDALONE_PAGE_NUMBER_RE = re.compile(r"(?m)^\s*\d+\s*$")
    # HTML 注释（MinerU 偶尔用 <!-- --> 标记页码等元信息）
    _HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

    def _clean_page_artifacts(self, markdown: str, exclude_lines: list[str] | None = None) -> str:
        """清理 markdown 中的页眉页码痕迹

        1. 删除 HTML 注释块（可能存放页码等元信息）
        2. 删除独立成行的纯数字行（页码）
        3. 删除已知页眉文本（从 content_list header 类型收集）

        Args:
            markdown: 原始 markdown 文本
            exclude_lines: 已知页眉文本列表，从 markdown 中删除匹配的行

        Returns:
            清理后的 markdown
        """
        if not markdown:
            return markdown
        cleaned = self._HTML_COMMENT_RE.sub("", markdown)
        cleaned = self._STANDALONE_PAGE_NUMBER_RE.sub("", cleaned)
        # 删除已知页眉文本行
        if exclude_lines:
            for line in exclude_lines:
                escaped = re.escape(line)
                cleaned = re.sub(rf"(?m)^\s*{escaped}\s*$", "", cleaned)
        # 清理因删除行产生的多余空行（保留单个换行）
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    # ── 异步方法 ──────────────────────────────────────────────

    async def aparse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """异步通过 MinerU API 解析文档。

        轮询期间使用 asyncio.sleep 替代 time.sleep，不阻塞事件循环。
        """
        import asyncio
        import time as _time

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        start_time = _time.time()
        logger.info("开始 MinerU 异步解析: %s", file_path)

        try:
            batch_id = await self._aupload_file(file_path)
            result = await self._apoll_batch_result(batch_id)
            parsed = await self._aparse_result_zip(
                result["full_zip_url"],
                return_markdown=return_markdown,
                extract_images=extract_images,
            )

            duration = _time.time() - start_time
            logger.info("MinerU 异步解析完成: %s (%.2fs, %d 字符)", file_path, duration, len(parsed.text))
            return parsed

        except (MineruAPIError, ParsingTimeoutError):
            raise
        except Exception as e:
            logger.error("MinerU 异步解析失败: %s - %s", file_path, str(e))
            raise MineruAPIError(f"MinerU 解析失败: {e}") from e

    async def aextract_text(
        self,
        file_path: str,
        max_length: int | None = None,
        **kwargs: Any,
    ) -> TextExtractionResult:
        """异步提取文档纯文本。"""
        try:
            parsed = await self.aparse_document(
                file_path=file_path,
                extract_tables=False,
                extract_images=False,
                return_markdown=False,
                **kwargs,
            )

            text = parsed.text
            if max_length and len(text) > max_length:
                text = text[:max_length]

            return TextExtractionResult(text=text, success=True, method="mineru", metadata=parsed.metadata)

        except Exception as e:
            logger.error("MinerU 异步文本提取失败: %s - %s", file_path, str(e))
            return TextExtractionResult(text="", success=False, method="mineru", metadata={"error": str(e)})

    async def _aupload_file(self, file_path: str) -> str:
        """异步上传文件到 MinerU。"""
        import asyncio
        import uuid

        file_path_obj = Path(file_path)
        file_name = file_path_obj.name

        async_client = get_async_http_client()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "files": [{"name": file_name, "data_id": uuid.uuid4().hex}],
            "model_version": self.MODEL_VERSION,
        }

        try:
            response = await async_client.post(self.BATCH_URL, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                raise MineruAPIError(f"获取上传 URL 失败: {result.get('msg', '未知错误')}")

            batch_id: str = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]

            if not urls:
                raise MineruAPIError("未获取到上传 URL")

            upload_url = urls[0]

            # H2 修复：大文件读取改为异步，避免阻塞事件循环
            file_content = await asyncio.to_thread(Path(file_path).read_bytes)
            upload_response = await async_client.put(upload_url, content=file_content, timeout=self.timeout)
            upload_response.raise_for_status()

            logger.info("文件异步上传成功: %s (batch_id=%s)", file_name, batch_id)
            return batch_id

        except httpx.HTTPError as e:
            raise MineruAPIError(f"HTTP 请求失败: {e}") from e

    async def _apoll_batch_result(self, batch_id: str) -> dict:
        """异步轮询批量任务结果 — await asyncio.sleep 替代 time.sleep。"""
        import asyncio
        import time as _time

        async_client = get_async_http_client()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.BATCH_RESULTS_URL}/{batch_id}"
        start_time = _time.time()

        while True:
            elapsed = _time.time() - start_time
            if elapsed > self.POLL_TIMEOUT:
                raise ParsingTimeoutError(f"任务超时 ({self.POLL_TIMEOUT}秒): batch_id={batch_id}")

            try:
                response = await async_client.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()

                if result.get("code") != 0:
                    raise MineruAPIError(f"查询结果失败: {result.get('msg', '未知错误')}")

                extract_results = result.get("data", {}).get("extract_result", [])
                if not extract_results:
                    logger.debug("批量结果为空，等待中 (elapsed=%.1fs)", elapsed)
                    await asyncio.sleep(self.POLL_INTERVAL)
                    continue

                file_result: dict = extract_results[0]
                state = file_result.get("state", "")

                if state == "done":
                    logger.info("MinerU 批量任务完成: %s", batch_id)
                    return file_result
                elif state == "failed":
                    err_msg = file_result.get("err_msg", "未知错误")
                    raise MineruAPIError(f"任务失败: {err_msg}")

                logger.debug("任务进行中: batch_id=%s (state=%s, elapsed=%.1fs)", batch_id, state, elapsed)
                await asyncio.sleep(self.POLL_INTERVAL)

            except MineruAPIError:
                raise
            except httpx.HTTPError as e:
                logger.warning("轮询请求失败: %s，将重试", e)
                await asyncio.sleep(self.POLL_INTERVAL)

    async def _aparse_result_zip(
        self,
        zip_url: str,
        return_markdown: bool = False,
        extract_images: bool = False,
    ) -> ParsedDocument:
        """异步下载并解析结果 ZIP 文件。ZIP 解析是 CPU 密集型，用 asyncio.to_thread 卸载。"""
        import asyncio

        async_client = get_async_http_client()

        try:
            # 异步下载 ZIP
            response = await async_client.get(zip_url, timeout=self.timeout)
            response.raise_for_status()
            zip_content = response.content

            # ZIP 解析是 CPU 密集型，在线程池中执行
            return await asyncio.to_thread(self._parse_zip_content, zip_content, return_markdown, extract_images)

        except zipfile.BadZipFile as e:
            raise MineruAPIError(f"结果 ZIP 文件损坏: {e}") from e
        except Exception as e:
            raise MineruAPIError(f"解析结果失败: {e}") from e

    def _parse_zip_content(self, zip_content: bytes, return_markdown: bool, extract_images: bool) -> ParsedDocument:
        """同步解析 ZIP 内容（在线程池中被 _aparse_result_zip 调用）。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "result.zip"
            zip_path.write_bytes(zip_content)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)

            md_file = None
            content_list_file = None
            image_files = []

            for f in Path(tmp_dir).rglob("*"):
                if f.suffix == ".md":
                    md_file = f
                elif f.name.endswith("_content_list.json"):
                    content_list_file = f
                elif f.suffix in (".jpg", ".jpeg", ".png"):
                    image_files.append(f)

            # 收集已知页眉文本（用于清理 markdown 残留）
            header_texts: list[str] = []
            if content_list_file:
                header_texts = self._collect_header_texts_from_content_list(content_list_file)

            text = ""
            if content_list_file:
                text = self._extract_text_from_content_list(content_list_file)
            elif md_file:
                # fallback 到 markdown，需清理页眉页码
                text = self._clean_page_artifacts(md_file.read_text(encoding="utf-8"), exclude_lines=header_texts)

            markdown = None
            if return_markdown and md_file:
                markdown = self._clean_page_artifacts(md_file.read_text(encoding="utf-8"), exclude_lines=header_texts)

            images = None
            if extract_images:
                images = [str(f) for f in image_files]

            metadata = {
                "task_id": None,
                "has_images": len(image_files) > 0,
                "image_count": len(image_files),
            }

            return ParsedDocument(
                text=text,
                markdown=markdown,
                images=images,
                metadata=metadata,
                parse_method="mineru",
            )
