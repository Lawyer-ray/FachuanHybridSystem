"""MinerU API 后端实现"""

import logging
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from apps.core.http.httpx_clients import get_sync_http_client
from apps.core.services.document_parse_provider_service import ParseProviderService
from apps.document_parsing.exceptions import MineruAPIError, ParsingTimeoutError
from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult
from apps.document_parsing.services.backends._page_artifacts import (
    clean_page_artifacts,
    collect_header_texts,
    normalize_text,
)
from apps.document_parsing.services.credential_pool import CredentialPool, get_credential_pool

logger = logging.getLogger(__name__)


class MineruBackend:
    """MinerU API 后端

    通过 MinerU 云服务解析文档，支持 PDF、DOC、PPT、Excel、图片等格式。
    凭证来自「解析平台」管理页（DocumentParseProvider），多凭证自动轮询、
    每凭证并发上限 + 失败冷却（见 credential_pool）。
    """

    # 本后端对应的平台服务类型（DocumentParseProvider.ProviderType）
    provider_type: str = "mineru"

    # 固定的配置（不需要用户管理）
    API_URL = "https://mineru.net/api/v4/extract/task"
    BATCH_URL = "https://mineru.net/api/v4/file-urls/batch"
    MODEL_VERSION = "vlm"
    POLL_INTERVAL = 1  # 轮询间隔（秒）
    POLL_TIMEOUT = 60  # 超时时间（秒）

    BATCH_RESULTS_URL = "https://mineru.net/api/v4/extract-results/batch"

    # 后端能力声明：云端后端含 HTTP 上传 + 轮询，阻塞时间长，需异步执行
    requires_async_execution: bool = True

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
        provider: Any = None,
    ):
        """初始化 MinerU 后端

        Args:
            api_key: 显式提供的 API Key（Bearer Token），支持逗号/换行/空格分隔的多 key。
                     仅用于显式覆盖；日常应由「解析平台」管理页配置。
            timeout: HTTP 请求超时时间（秒）
            provider: DocumentParseProvider 实例；不传时按类型自动选择优先级最高的启用平台。
        """
        if api_key:
            keys = [k.strip() for k in re.split(r"[,\s\r\n]+", str(api_key)) if k.strip()]
            if not keys:
                raise ValueError("MinerU API Key 解析后为空，请检查配置内容。")
            self._pool: CredentialPool = CredentialPool(keys, 0)
            provider_name = "__explicit_mineru"
        else:
            resolved = provider or ParseProviderService.get_provider(self.provider_type)
            if resolved is None:
                raise ValueError(
                    "未配置 MinerU 解析平台。"
                    "请在「解析平台」管理页新增 MinerU 平台并填写凭证"
                    "（http://127.0.0.1:8002/admin/core/documentparseprovider/）"
                )
            creds = [k for k in resolved.parsed_credentials() if k]
            if not creds:
                raise ValueError("MinerU 解析平台未填写凭证，请先补充 API Key。")
            self._pool = get_credential_pool(
                provider_key=str(resolved.name),
                credentials=creds,
                concurrency_per_key=resolved.concurrency_per_key,
            )
            provider_name = str(resolved.name)

        self.timeout = timeout
        self._active_key: str | None = None  # 由 parse_document 设置
        self._provider_name = provider_name

        logger.info(
            "初始化 MinerU 后端: provider=%s keys=%d limit=%d timeout=%ds",
            self._provider_name,
            len(self._pool.credentials),
            self._pool.limit,
            self.timeout,
        )

    @property
    def api_key(self) -> str:
        """返回当前使用的 API key（兼容单 key 场景）。"""
        if self._active_key is not None:
            return self._active_key
        return self._pool.credentials[0] if self._pool.credentials else ""

    def _acquire_key(self) -> tuple[str, int]:
        """从凭证池占用一个 API key。

        Returns:
            (key, idx)：idx 用于事后释放。
        """
        idx = self._pool.acquire()
        if idx is None:
            raise MineruAPIError("MinerU 所有凭证仍在失败冷却中，请稍后重试")
        return self._pool.credentials[idx], idx

    def _release_key(self, idx: int | None, *, success: bool) -> None:
        if idx is not None:
            self._pool.release(idx, success=success)

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

        # 每次解析任务占用一个 key，"_upload_file" 与 "_poll_batch_result" 共用该 key
        self._active_key, idx = self._acquire_key()
        success = False
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

            success = True
            return parsed

        except (MineruAPIError, ParsingTimeoutError):
            raise
        except Exception as e:
            logger.error("MinerU 解析失败: %s - %s", file_path, str(e))
            raise MineruAPIError(f"MinerU 解析失败: {e}") from e
        finally:
            self._release_key(idx, success=success)

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
            "Authorization": f"Bearer {self._active_key}",
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
            "Authorization": f"Bearer {self._active_key}",
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
                    text = clean_page_artifacts(md_file.read_text(encoding="utf-8"), exclude_lines=header_texts)

                # 提取 Markdown
                markdown = None
                if return_markdown and md_file:
                    markdown = clean_page_artifacts(md_file.read_text(encoding="utf-8"), exclude_lines=header_texts)

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
                        excluded_norm.add(normalize_text(text))

            # 提取 text 块，跳过匹配已知页眉页脚的
            texts = []
            for block in content_list:
                block_type = block.get("type", "")
                block_text = block.get("text", "")

                if block_type == "text" and block_text:
                    # 归一化后检查是否匹配已知页眉页脚
                    if normalize_text(block_text) in excluded_norm:
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

        return collect_header_texts(content_list, header_type="header")
