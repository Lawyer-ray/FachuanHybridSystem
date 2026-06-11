"""MinerU API 后端实现"""

import logging
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from apps.core.services.system_config_service import SystemConfigService
from apps.core.http.httpx_clients import get_sync_http_client
from apps.document_parsing.exceptions import (
    MineruAPIError,
    ParsingTimeoutError,
)
from apps.document_parsing.protocols.document_parser_protocol import (
    ParsedDocument,
    TextExtractionResult,
)

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

    def __init__(
        self,
        api_key: str = None,
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
            # 1. 上传文件到 MinerU
            file_url = self._upload_file(file_path)

            # 2. 创建解析任务
            task_id = self._create_task(
                file_url=file_url,
                file_type=file_type,
                extract_images=extract_images,
            )

            # 3. 轮询获取结果
            result = self._poll_result(task_id)

            # 4. 下载并解析 ZIP 结果
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
        max_length: Optional[int] = None,
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

    def get_supported_formats(self) -> List[str]:
        """获取支持的文件格式"""
        return ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "jpg", "jpeg", "png"]

    def _upload_file(self, file_path: str) -> str:
        """上传文件到 MinerU，获取文件 URL

        Args:
            file_path: 本地文件路径

        Returns:
            文件 URL
        """
        file_path_obj = Path(file_path)
        file_name = file_path_obj.name

        # 请求上传 URL
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

            if result.get("code") != 0:
                raise MineruAPIError(
                    f"获取上传 URL 失败: {result.get('msg', '未知错误')}"
                )

            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]

            if not urls:
                raise MineruAPIError("未获取到上传 URL")

            upload_url = urls[0]
            file_size = file_path_obj.stat().st_size

            # 上传文件到预签名 URL
            with open(file_path, "rb") as f:
                upload_response = client.put(
                    upload_url,
                    content=f.read(),
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=self.timeout,
                )
                logger.debug(
                    "PUT 上传响应: status=%d, headers=%s, file_size=%d",
                    upload_response.status_code,
                    dict(upload_response.headers),
                    file_size,
                )
                upload_response.raise_for_status()

            logger.info("文件上传成功: %s (batch_id=%s)", file_name, batch_id)

            # 返回 MinerU 内部文件 URL（用于创建任务）
            return upload_url

        except httpx.HTTPError as e:
            raise MineruAPIError(f"HTTP 请求失败: {e}") from e

    def _create_task(
        self,
        file_url: str,
        file_type: str = "pdf",
        extract_images: bool = False,
    ) -> str:
        """创建 MinerU 解析任务

        Args:
            file_url: 文件 URL
            file_type: 文件类型
            extract_images: 是否提取图片

        Returns:
            任务 ID
        """
        client = get_sync_http_client()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "url": file_url,
            "model_version": self.MODEL_VERSION,
        }

        try:
            response = client.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                raise MineruAPIError(
                    f"创建任务失败: {result.get('msg', '未知错误')}"
                )

            task_id = result["data"]["task_id"]
            logger.info("MinerU 任务创建成功: task_id=%s", task_id)

            return task_id

        except httpx.HTTPError as e:
            raise MineruAPIError(f"创建任务失败: {e}") from e

    def _poll_result(self, task_id: str) -> dict:
        """轮询获取解析结果

        Args:
            task_id: 任务 ID

        Returns:
            任务结果

        Raises:
            ParsingTimeoutError: 超时
            MineruAPIError: 任务失败
        """
        client = get_sync_http_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        url = f"{self.API_URL}/{task_id}"
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.POLL_TIMEOUT:
                raise ParsingTimeoutError(
                    f"任务超时 ({self.POLL_TIMEOUT}秒): {task_id}"
                )

            try:
                response = client.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

                state = result.get("data", {}).get("state", "")

                if state == "done":
                    logger.info("MinerU 任务完成: %s", task_id)
                    return result["data"]

                elif state == "failed":
                    err_msg = result.get("data", {}).get("err_msg", "未知错误")
                    raise MineruAPIError(f"任务失败: {err_msg}")

                # 继续轮询
                logger.debug(
                    "任务进行中: %s (state=%s, elapsed=%.1fs)",
                    task_id,
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

                # 提取文本
                text = ""
                if content_list_file:
                    text = self._extract_text_from_content_list(content_list_file)
                elif md_file:
                    text = md_file.read_text(encoding="utf-8")

                # 提取 Markdown
                markdown = None
                if return_markdown and md_file:
                    markdown = md_file.read_text(encoding="utf-8")

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
        """从 content_list.json 提取文本

        Args:
            content_list_path: content_list.json 文件路径

        Returns:
            提取的文本
        """
        import json

        try:
            with open(content_list_path, "r", encoding="utf-8") as f:
                content_list = json.load(f)

            # 按顺序提取所有文本块
            texts = []
            for block in content_list:
                block_type = block.get("type", "")
                block_text = block.get("text", "")

                if block_type == "text" and block_text:
                    texts.append(block_text)

            return "\n".join(texts)

        except Exception as e:
            logger.warning("解析 content_list.json 失败: %s", e)
            return ""
