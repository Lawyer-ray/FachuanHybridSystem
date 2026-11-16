"""MinerU API 后端实现

配置了回调（见 ``services/callback_config.py``）时，上传完成后不再轮询批量结果：
把 ``callback`` / ``seed`` 随上传申请一起发给 MinerU，结果由
`/api/v1/document-parsing/webhook/mineru` 推回。未配置时与原来完全一致。
"""

import json
import logging
import re
import tempfile
import time
import zipfile
from html import unescape
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from apps.core.exceptions import ValidationException
from apps.core.filesystem.filesystem_service import ensure_zip_within_limits
from apps.core.http.httpx_clients import get_sync_http_client
from apps.core.services.document_parse_provider_service import ParseProviderService
from apps.document_parsing.exceptions import MineruAPIError, ParsingTimeoutError
from apps.document_parsing.protocols.document_parser_protocol import (
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    NON_BODY_BLOCK_TYPES,
    ParsedDocument,
    PendingCallback,
    TextExtractionResult,
    normalize_block_type,
)
from apps.document_parsing.services.backends._page_artifacts import (
    clean_page_artifacts,
    collect_header_texts,
    normalize_text,
)
from apps.document_parsing.services.block_builder import attach_blocks
from apps.document_parsing.services.credential_pool import CredentialPool, get_credential_pool

logger = logging.getLogger(__name__)

#: 没有行级几何的块类型：MinerU 对它们只给整块 bbox（表格内容装在 span.html 里），
#: 下游不能当行级坐标用，因此这类块的 ``lines`` 固定为空列表。
_NO_LINE_LEVEL_BLOCK_TYPES: frozenset[str] = frozenset({BLOCK_TYPE_TABLE, BLOCK_TYPE_IMAGE})

#: model.json 的 bbox 是归一化 0-1，乘这个系数换成千分比 0-1000
#: （与 content_list 主路径同一口径，见 ``resolve_bbox_unit('mineru') == 'permille'``）。
_MODEL_JSON_BBOX_SCALE = 1000

#: 需要显式开启 OCR 的后缀（PDF 与图片）。其余办公文档（doc/docx/ppt/pptx/xls/xlsx）
#: 由 MinerU 先转 PDF 再解析，不传 ``is_ocr`` 走服务端默认，省一次识别。
_OCR_REQUIRED_SUFFIXES: frozenset[str] = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".jp2", ".webp", ".gif", ".bmp"})

#: 判断 ocr_text 行框是否落在 text 块 y 范围 / x 范围重叠时的容差（千分比）。
#: 两个文件来自不同的版面推理分支，同一条线的上下边界会有几像素级差异，
#: 不留容差会把真实匹配判成不匹配；留太多又会把邻行吞进来。±5 千分比 ≈ ±0.5% 页高。
_OCR_LINE_BBOX_TOLERANCE = 5

#: 是否要 MinerU 做公式识别。全链路只往一个方向取：**关**。
#
# 官方文档（https://mineru.net/apiManage/docs，两处均如此写）：
# 「是否开启公式识别，默认 true。特别注意：对于 vlm 模型，这个参数只会影响
#   行内公式的解析。」也就是说在 vlm 下它管不到行间公式（``$$…$$``），
# 只管正文里夹着的 ``$…$``。
#
# 选 false 的依据是实测（2026-11，vlm + is_ocr=true，同一份含公式的合成 PDF
# 各跑一次）：text / markdown / 每个块的文本与类型序列 **逐字节完全一致**，
# 行间公式块照样产出。行内公式这一侧我们本来就不消费——``text`` 主路径只取
# ``type == "text"``（见 ``_extract_text_from_content_list``），公式块进不了 text；
# 要公式内容得读 ``markdown`` 或 ``blocks``（``BLOCK_TYPE_FORMULA``）。
#
# 保守取向由此而来：关掉它换不来质量，也换不来时间（实测两边耗时互有高低，
# 差异在噪声里），唯一的收益是「不把表格里的小角标、印章边上的符号误判成
# 行内公式」。真出现误判，公式块也只是被单独标成一个块，不会吞掉别的内容。
#
# 什么时候回头看：若将来允许把行内公式原样交给下游（例如让 LLM 读含公式的
# 鉴定意见、利息计算书并需要 ``$r$`` 这类记号），或者抽查发现 markdown 里
# ``$…$`` 出现的位置本该是普通文字/金额，就打开它重跑一次 A/B。
_ENABLE_FORMULA = False


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
    POLL_TIMEOUT = 360  # 6 分钟，为解析任务轮询和结果下载预留队列时间

    #: 单次轮询请求的超时（秒）。
    #
    # ⚠️ 故意比 `self.timeout`（元数据请求的 30s）短得多，且**不能用它做总时长判据**。
    #
    # 实测事故（2026-11-16，164 页全本双引擎）：
    #   · POLL_TIMEOUT = 360s，但 MinerU 那一路实际跑了 4347s（72 分钟）
    #   · 日志里「轮询请求失败」只有 8 条 —— 说明绝大部分时间在**静默阻塞**，
    #     不是在失败重试
    #
    # 根因：httpx 的 `timeout` 是「单次连接/读写」超时，不是墙钟总时长。
    # TCP 连接半死（对端网关丢了状态、NAT 表过时）时，内核会按系统级重传策略
    # 死等 —— macOS 默认 75s 起，多次重传可达十几分钟。这期间 `client.get()`
    # 根本不返回，`while` 里那句 `elapsed > POLL_TIMEOUT` 永远轮不到执行。
    #
    # 所以超时控制必须两道：
    #   ① 单次请求短超时（这个值）—— 让卡住的连接尽快失败而不是死等；
    #   ② 循环里的墙钟检查（POLL_TIMEOUT）—— 仍需保留，防「每次都刚好没超时」的累积。
    POLL_REQUEST_TIMEOUT = 15

    #: 轮询请求**连续**失败多少次就放弃。
    #
    # 与 POLL_TIMEOUT 是两条路：
    #   · 云端在跑但慢 → 请求都成功（state=running），靠 POLL_TIMEOUT 收口
    #   · 本地网络/代理挂了 → 请求一直失败，靠这个计数收口
    # 不去重试到时间耗尽，是因为后者重试再多次也不会自愈，只是白占 worker 槽位。
    POLL_MAX_CONSECUTIVE_ERRORS = 8

    RESULT_DOWNLOAD_ATTEMPTS = 3

    # 文件上传专用的**每阶段最小超时**（秒）。
    #
    # 为什么不能继续用 `self.timeout`（默认 30s）上传：那个值是为**元数据请求**
    # （申请上传 URL、查询批次状态，都是几百字节的 JSON）定的。拿它去 PUT 一个
    # 65MB 的卷宗，在普通宽带上要几十秒，实测直接 `write operation timed out`——
    # 双引擎里 MinerU 这一侧就永远拿不到结果，只剩 PaddleOCR-VL 单边，比对失去意义。
    #
    # 用**按体积换算**而不是一个写死的大值：小文件不必白等，大文件也不会因为
    # 固定上限而装不下。上传时长与体积近似线性，这里留 4 倍余量。
    UPLOAD_MIN_TIMEOUT = 120  # 小文件也不少于这个值（握手/重定向/TLS 建立）
    UPLOAD_BYTES_PER_SECOND = 512 * 1024  # 保守估算带宽（512KB/s），越大越宽容
    UPLOAD_TIMEOUT_SLACK = 4.0  # 给带宽波动/DNS/重定向往返留的倍数
    UPLOAD_MAX_TIMEOUT = 3600  # 上限：再大就该分片传了，不要让单请求无限挂着
    UPLOAD_ATTEMPTS = 3

    BATCH_RESULTS_URL = "https://mineru.net/api/v4/extract-results/batch"

    # 后端能力声明：云端后端含 HTTP 上传 + 轮询，阻塞时间长，需异步执行
    requires_async_execution: bool = True

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
        provider: Any = None,
        upload_timeout: float | None = None,
    ):
        """初始化 MinerU 后端

        Args:
            api_key: 显式提供的 API Key（Bearer Token），支持逗号/换行/空格分隔的多 key。
                     仅用于显式覆盖；日常应由「解析平台」管理页配置。
            timeout: **元数据请求**的超时时间（秒）。文件上传不走它，见
                `_upload_timeout_for`——一个大文件用 30s 传是必然失败的。
            provider: DocumentParseProvider 实例；不传时按类型自动选择优先级最高的启用平台。
            upload_timeout: 显式指定文件上传超时（秒）。不传则按文件体积换算。
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
        # None = 按每个文件的体积现算（见 _upload_timeout_for）。
        # 显式传入时就是个固定上限，主要给测试与特殊部署用。
        self.upload_timeout = upload_timeout
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
            **kwargs: ``callback_url`` / ``callback_seed`` 同时给出时走回调
                （上传完即返回，结果由 `/api/v1/document-parsing/webhook/mineru` 写回）；
                否则走原有轮询

        Returns:
            ParsedDocument 解析结果
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        start_time = time.time()
        logger.info("开始 MinerU 解析: %s", file_path)

        callback_url = str(kwargs.get("callback_url") or "").strip()
        callback_seed = str(kwargs.get("callback_seed") or "").strip()
        if callback_url and not callback_seed:
            # MinerU 要求用 callback 时必须带 seed，否则其侧会拒掉整个请求；
            # 与其发一个注定失败的上传，不如当作未启用回调
            logger.warning("MinerU 收到 callback_url 但缺少 callback_seed，本次回退轮询: %s", file_path)
            callback_url = ""

        # 每次解析任务占用一个 key，"_upload_file" 与 "_poll_batch_result" 共用该 key
        self._active_key, idx = self._acquire_key()
        success = False
        try:
            # 1. 上传文件到 MinerU（上传后 MinerU 自动创建解析任务）
            batch_id = self._upload_file(file_path, callback=callback_url or None, seed=callback_seed or None)

            if callback_url:
                # 回调路径：任务已在云端，立即返回。上传成功即算本次占用成功，
                # 云端后续失败由回调侧记到任务记录上。
                logger.info("MinerU 任务已提交，等待回调: %s (batch_id=%s)", file_path, batch_id)
                success = True
                return ParsedDocument(
                    text="",
                    markdown=None,
                    metadata={"batch_id": batch_id},
                    parse_method="mineru",
                    pending_callback=PendingCallback(provider=self.provider_type, job_id=batch_id),
                )

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

    def _upload_timeout_for(self, file_size_bytes: int) -> httpx.Timeout:
        """按文件体积算一个**分阶段**的上传超时。

        为什么要分阶段（httpx.Timeout 的四个参数各管一段）而不是一个总数：

        · `connect` / `write` 只需要把请求头和字节流递交给 socket，几乎与文件大小
          无关，但链路上的一次 TLS 握手或 DNS 解析抖动就可能吃掉十来秒——
          留 `UPLOAD_MIN_TIMEOUT` 的底；
        · `read` 是等对方返回状态码。预签名上传的目标是对象存储，大文件时它可能
          花较久才回 200；这一项必须跟着体积走，否则就是本次事故的复现。

        体积到时间的换算用保守带宽（512KB/s）再乘 4 倍余量：65MB 卷宗算出约
        520s，而实测常见家用宽带下只需几十秒——宁可多等，也不要再在 30s 上搏一次。
        """
        if self.upload_timeout is not None:
            total = float(self.upload_timeout)
        else:
            estimated = file_size_bytes / self.UPLOAD_BYTES_PER_SECOND * self.UPLOAD_TIMEOUT_SLACK
            total = max(float(self.UPLOAD_MIN_TIMEOUT), estimated)
            total = min(total, float(self.UPLOAD_MAX_TIMEOUT))
        return httpx.Timeout(total, connect=self.UPLOAD_MIN_TIMEOUT, write=total, read=total)

    def _request_upload_url(
        self,
        file_name: str,
        *,
        callback: str | None = None,
        seed: str | None = None,
    ) -> tuple[str, str]:
        """申请预签名上传地址，返回 ``(batch_id, upload_url)``。

        ``callback`` / ``seed`` 是 MinerU 的回调参数：callback 是解析完成后要 POST
        的 URL，seed 是签名种子（用 callback 时必填，其回调 checksum =
        sha256(uid + seed + content)）。两者传 None 表示不启用回调、保持轮询。

        这是几百字节的 JSON 往返，用元数据超时（`self.timeout`）就够了；
        它可能返回 5xx/限流，所以包一层轻量重试。

        payload 的字段位置**不能凭直觉放**：走的是批量接口
        ``/api/v4/file-urls/batch``，``is_ocr`` 是 ``files[]`` 元素里的字段
        （官方文档写作 ``file.is_ocr``）；顶层 ``is_ocr`` 只属于单文件接口
        ``/api/v4/extract/task``。放错层服务端会静默忽略——不报错，只是回到
        默认 ``is_ocr=false``。

        关于 ``is_ocr`` 的实测事实（2026-11，vlm）：**它在 vlm 模型下不产生
        任何差异**。同一份文字层为 0 的扫描件分别以 ``is_ocr=false`` /
        ``true`` 各跑一次，返回正文逐字节相同（单页 84 字符；164 页件前 3 页
        均 860 字符）。即 vlm 本来就会对无文字层的页面做 OCR，官方文档那句
        「默认 false，仅对 pipeline、vlm 模型有效」在 vlm 下的实际含义是
        「参数可识别」，而不是「关掉就不 OCR」。

        既然如此为什么仍显式传 ``true``：
          · ``MODEL_VERSION`` 是可改的。一旦有人切回 ``pipeline``，默认
            ``is_ocr=false`` 会让扫描件解析成空白——这是静默的，不会报错。
            显式传值让两种模型都安全。
          · 省掉「靠默认值碰对」的隐式依赖。
        """
        # 见上：vlm 下无实际作用，是为 pipeline 兼容与显式意图，不是性能开关。
        client = get_sync_http_client()
        suffix = Path(file_name).suffix.lower()
        file_entry: dict[str, Any] = {"name": file_name, "data_id": uuid4().hex}
        if suffix in _OCR_REQUIRED_SUFFIXES:
            # vlm 下此值实测无作用（见 _request_upload_url 的 docstring），
            # 显式传 true 是为了 MODEL_VERSION 改回 pipeline 时扫描件仍能出字。
            file_entry["is_ocr"] = True
            # 与顶层同一个值，理由见 ``_ENABLE_FORMULA``。批量接口的文档把
            # ``enable_formula`` 列在顶层；元素内这一份是为对齐 ``file.is_ocr``
            # 的写法，两边取值必须一致，不能一处 true 一处 false。
            file_entry["enable_formula"] = _ENABLE_FORMULA
        payload: dict[str, Any] = {
            "files": [file_entry],
            "model_version": self.MODEL_VERSION,
            "language": "ch",
            "enable_table": True,
            "enable_formula": _ENABLE_FORMULA,
        }
        if callback and seed:
            payload["callback"] = callback
            payload["seed"] = seed
        last_error: Exception | None = None
        for attempt in range(1, self.UPLOAD_ATTEMPTS + 1):
            try:
                response = client.post(
                    self.BATCH_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._active_key}",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()
                logger.debug("batch API 响应: %s", result)
                if result.get("code") != 0:
                    raise MineruAPIError(f"获取上传 URL 失败: {result.get('msg', '未知错误')}")
                urls = result["data"]["file_urls"]
                if not urls:
                    raise MineruAPIError("未获取到上传 URL")
                return str(result["data"]["batch_id"]), str(urls[0])
            except (httpx.HTTPError, KeyError) as e:
                last_error = e
                if attempt == self.UPLOAD_ATTEMPTS:
                    break
                logger.warning("获取 MinerU 上传 URL 失败，准备重试 (%d/%d): %s", attempt, self.UPLOAD_ATTEMPTS, e)
                time.sleep(attempt)
        raise MineruAPIError(f"HTTP 请求失败: {last_error}") from last_error

    def _put_file_streaming(self, upload_url: str, file_path_obj: Path) -> None:
        """把文件流式 PUT 到预签名地址。

        两个关键点：

        1. **不整包进内存**。改用 `content=文件句柄` 让 httpx 分块读盘（原来是
           `f.read()` 把 65MB 一次性拉到内存，并发跑多个引擎时内存峰值极难看）。
           用 file object 而非生成器：httpx 能据此算出 Content-Length，对象存储
           的预签名校验才过。
        2. **每次重试重开文件**。失败的 PUT 可能已把句柄读空，复用一个漂移的
           偏移量会传出一份残缺字节（对象存储不校验内容，会当成成功）。

        Content-Type 仍然刻意不设：预签名 URL 的签名不包含这个 header，
        多带一个反而会验签失败。
        """
        size = file_path_obj.stat().st_size
        timeout = self._upload_timeout_for(size)
        last_error: Exception | None = None
        for attempt in range(1, self.UPLOAD_ATTEMPTS + 1):
            try:
                # 独立客户端 + trust_env 与结果下载同口径：上传走代理隧道时偶发
                # 提前断流，重试轮换直连能绕过去。
                with (
                    open(file_path_obj, "rb") as handle,
                    httpx.Client(timeout=timeout, follow_redirects=True, trust_env=attempt % 2 == 1) as uploader,
                ):
                    response = uploader.put(upload_url, content=handle)
                    response.raise_for_status()
                return
            except httpx.HTTPError as e:
                last_error = e
                if attempt == self.UPLOAD_ATTEMPTS:
                    break
                logger.warning(
                    "MinerU 文件上传失败（%.1f MB，超时 %ss），准备重试 (%d/%d): %s",
                    size / 1024 / 1024,
                    int(timeout.read or 0),
                    attempt,
                    self.UPLOAD_ATTEMPTS,
                    e,
                )
                time.sleep(attempt)
        raise MineruAPIError(f"文件上传失败（{size / 1024 / 1024:.1f} MB）: {last_error}") from last_error

    def _upload_file(self, file_path: str, *, callback: str | None = None, seed: str | None = None) -> str:
        """上传文件到 MinerU，上传后 MinerU 自动创建解析任务。

        ``callback`` / ``seed`` 透传给上传申请接口（见 ``_request_upload_url``）。

        分两步，超时口径不同（详见 `_upload_timeout_for`）：

        1. 申请预签名地址：几百字节 JSON，用元数据超时；
        2. 把文件本体流式 PUT 上去：耗时随体积线性增长，必须按体积给时间。

        原始实现两步共用一个 30s 超时、且把整个文件 read() 进内存，65MB 卷宗
        实测直接 `write operation timed out`——双引擎里 MinerU 这一侧永远缺结果。

        Returns:
            batch_id（用于查询解析结果）
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise MineruAPIError(f"待上传文件不存在: {file_path}")
        file_name = file_path_obj.name

        batch_id, upload_url = self._request_upload_url(file_name, callback=callback, seed=seed)
        self._put_file_streaming(upload_url, file_path_obj)
        logger.info(
            "文件上传成功: %s (%.1f MB, batch_id=%s)",
            file_name,
            file_path_obj.stat().st_size / 1024 / 1024,
            batch_id,
        )
        return batch_id

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
        headers = {
            "Authorization": f"Bearer {self._active_key}",
        }

        url = f"{self.BATCH_RESULTS_URL}/{batch_id}"
        start_time = time.time()
        consecutive_errors = 0
        last_state = "尚未拿到响应"

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.POLL_TIMEOUT:
                # 把「实际跑了多久」与「最后一次看到的 state」一起写进去：
                # 只有裸的「任务超时 (360秒)」无法区分「云端真慢」与「本地网络死了」。
                raise ParsingTimeoutError(
                    f"任务超时 ({self.POLL_TIMEOUT}秒, 实际 {elapsed:.0f}s): batch_id={batch_id}, 最后状态={last_state}"
                )

            try:
                # 每次都新建客户端：共享工厂客户端的长连接经历一次 SSL 断连后会处于
                # 半死状态，而复用它正是上面那次 72 分钟阻塞的直接土壤。
                with httpx.Client(timeout=self.POLL_REQUEST_TIMEOUT, follow_redirects=True) as client:
                    response = client.get(url, headers=headers)
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
                last_state = str(state)
                consecutive_errors = 0  # 拿到有效响应就清零：连续失败只算「一直失败」
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
                consecutive_errors += 1
                logger.warning("轮询请求失败（连续第 %d 次）: %s，将重试", consecutive_errors, e)
                # 连接一直不通时不要空转到 POLL_TIMEOUT：连续失败达到上限就直接报错。
                # 理由：这是**本地网络层**的问题（DNS / 代理 / TLS），重试再多次也不会好，
                # 只会把 worker 死死占住一个队列槽位。而云端「跑得慢」是正常态，走
                # POLL_TIMEOUT 那条路。两者要分开报，否则排障时无法区分。
                if consecutive_errors >= self.POLL_MAX_CONSECUTIVE_ERRORS:
                    raise MineruAPIError(
                        f"轮询连续失败 {consecutive_errors} 次"
                        f"（{type(e).__name__}: {e}），判断为本地网络/代理不可用，已放弃: "
                        f"batch_id={batch_id}"
                    ) from e
                time.sleep(self.POLL_INTERVAL)

    def _download_result_zip(self, zip_url: str, zip_path: Path) -> None:
        """流式下载结果 ZIP 到 ``zip_path``（8192 块写盘，不整包入内存）。

        重试策略（沿用既有行为）：
        - 奇数轮按环境默认（可能走代理），偶数轮 ``trust_env=False`` 绕开代理直连：
          结果存储 CDN 经代理隧道偶发 TLS 掐断（UNEXPECTED_EOF），直连可绕过；
          必须经代理出网的环境则由奇数轮承担。两路交替保证至少各试一次。
        - 每次重试新建连接池，避免复用被对象存储关闭的 TLS keep-alive 连接
          （刻意不走共享工厂客户端）。
        """
        for attempt in range(1, self.RESULT_DOWNLOAD_ATTEMPTS + 1):
            trust_env = attempt % 2 == 1
            try:
                with httpx.Client(
                    timeout=max(self.timeout, 60), follow_redirects=True, trust_env=trust_env
                ) as download_client:
                    with download_client.stream("GET", zip_url) as response:
                        response.raise_for_status()
                        with open(zip_path, "wb") as f:
                            for chunk in response.iter_bytes(8192):
                                f.write(chunk)
                return
            except httpx.HTTPError:
                if attempt == self.RESULT_DOWNLOAD_ATTEMPTS:
                    raise
                logger.warning(
                    "MinerU 结果下载失败（trust_env=%s），准备重试 (%d/%d)",
                    trust_env,
                    attempt,
                    self.RESULT_DOWNLOAD_ATTEMPTS,
                )
                time.sleep(attempt)
        raise MineruAPIError("MinerU 结果下载失败：没有收到响应")

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
        try:
            # 解析 ZIP（流式下载，见 _download_result_zip）
            with tempfile.TemporaryDirectory() as tmp_dir:
                zip_path = Path(tmp_dir) / "result.zip"
                self._download_result_zip(zip_url, zip_path)

                with zipfile.ZipFile(zip_path, "r") as zf:
                    # 解压炸弹防护：按 ZIP 头声明的总量 / 成员数拒绝超限再 extractall
                    try:
                        ensure_zip_within_limits(zf)
                    except ValidationException as exc:
                        raise MineruAPIError(f"结果 ZIP 超出安全解压上限，已拒绝: {exc.message}") from exc
                    zf.extractall(tmp_dir)

                # 查找关键文件
                md_file = None
                content_list_file = None
                layout_file = None
                model_file = None
                image_files = []

                for f in Path(tmp_dir).rglob("*"):
                    if f.suffix == ".md":
                        md_file = f
                    elif f.name.endswith("_content_list.json"):
                        content_list_file = f
                    elif f.name == "layout.json":
                        layout_file = f
                    elif f.name.endswith("_model.json"):
                        model_file = f
                    elif f.suffix in (".jpg", ".jpeg", ".png"):
                        image_files.append(f)

                # 收集已知页眉文本（用于清理 markdown 残留）
                header_texts: list[str] = []
                if content_list_file:
                    header_texts = self._collect_header_texts_from_content_list(content_list_file)

                # 提取文本
                text = ""
                layout = None
                if content_list_file:
                    text = self._extract_text_from_content_list(content_list_file)
                    layout = self._extract_page_layout_from_content_list(content_list_file)
                    # content_list 只有块级 bbox 且完全没有页面尺寸；layout.json 补上
                    # page_size 与行/span 级 box。它是增强信息，缺了或格式不对都退回
                    # content_list 的原样结果，不影响 text/markdown 主链路。
                    if layout and layout_file:
                        self._merge_layout_json_details(layout, layout_file)
                    # model.json 的 ocr_text 是逐行 bbox（content_list/layout.json 都没有）：
                    # 它是唯一能给出「块里每一行各自在哪」的信息源。同样是增强信息，
                    # 缺失或结构不符时只丢行框，不影响 text/markdown 主链路。
                    if layout and model_file:
                        self._merge_model_json_lines(layout, model_file)
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
                    "page_count": (layout or {}).get("page_count", 0),
                }

                return attach_blocks(
                    ParsedDocument(
                        text=text,
                        markdown=markdown,
                        images=images,
                        metadata=metadata,
                        parse_method="mineru",
                        layout=layout,
                    )
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

        ⚠️ 必须含表格：MinerU 的表格块 ``text`` 字段**恒为空字符串**，内容全在
        ``table_body`` 的 HTML 里。此前本方法只取 ``type == "text"``，导致表格
        内容 100% 从 ``parsed.text`` 消失（实测 8 页卷宗：7 个表格、table_body
        合计 5292 字符，text 里 0 字符）。法律卷宗的金额、账号、当事人清单大量
        在表格里，这是静默丢数据。

        表格 HTML 去标签的口径与 ``_extract_page_layout_from_content_list`` 里
        的 ``page["text"]`` 完全一致（去标签 + 反转义 + 空白折叠），两条路径
        必须同源，否则 ``text`` 与 ``blocks`` 会看出不同内容。图片块同理取
        ``image_caption`` / ``image_footnote``。

        Args:
            content_list_path: content_list.json 文件路径

        Returns:
            提取的文本（不含页眉页脚，但含表格正文与图表说明）
        """
        try:
            with open(content_list_path, encoding="utf-8") as f:
                content_list = json.load(f)

            # 收集 header/footer 类型的归一化文本 → 出现次数。
            # 记次数而不是去重，是因为「出现 1 次」不能证明它是跨页页眉（也可能
            # 只是误标成 header 的正文标题，那种不能连正文一起吞）。
            excluded_norm: dict[str, int] = {}
            for block in content_list:
                if block.get("type") in ("header", "footer"):
                    text = (block.get("text") or "").strip()
                    if text:
                        key = normalize_text(text)
                        excluded_norm[key] = excluded_norm.get(key, 0) + 1

            # 提取正文块，跳过匹配已知页眉页脚的
            texts = []
            for block in content_list:
                block_type = block.get("type", "")
                # 页眉/页脚/页码不进正文（每页重复一遍会把正文淹掉）。
                # ``_content_block_text`` 只负责取块自身文本，不替调用方做取舍。
                if block_type in ("header", "footer", "page_number"):
                    continue
                block_text = self._content_block_text(block)
                if not block_text:
                    continue

                if block_type == "text" and self._is_repeated_header(block_text, excluded_norm):
                    continue
                texts.append(block_text)

            return "\n".join(texts)

        except Exception as e:
            logger.warning("解析 content_list.json 失败: %s", e)
            return ""

    @staticmethod
    def _is_repeated_header(block_text: str, excluded_norm: set[str], *, seen: int = 0) -> bool:
        """这个 text 块是否就是页眉/页脚从页面上方/下方重复冒出来的那一行。

        单纯「归一化相等」会把**正文里的同名内容一起吞掉**。法律文书里这种情况
        很常见：页眉是「民事判决书」，正文首个标题也是「民事判决书」；页眉是
        「（20XX）X XX 民初 XXX 号」，正文引用案号时也会出现同一串。此前这些正文首段被
        当成重复页眉直接丢弃（已复现：header='民事判决书' + text='民事判决书'
        时输出为空）。

        现在的判据只认「**多次重复**」：同一个归一化文本在 header/footer 里
        出现至少 2 次，才能当作跨页重复的页眉（真页眉每页都有）；只出现过
        1 次的，视为可能是正文标题，保留。

        Args:
            block_text: 待判断的 text 块内容
            excluded_norm: 已归一的 header/footer 文本 → 出现次数
            seen: 未使用（保留位，兼容旧调用签名）

        Returns:
            True 表示可以丢弃。
        """
        count = excluded_norm.get(normalize_text(block_text), 0)
        return count >= 2

    @staticmethod
    def _content_block_text(block: dict[str, Any]) -> str:
        """取一个 content_list 块的可读文本（表格/图片不再是空字符串）。

        与 ``_extract_page_layout_from_content_list`` 里构建 ``page["text"]`` 的
        口径严格同源：改这里必须同步改那里，否则 ``parsed.text`` 与
        ``parsed.blocks`` 会给出不一样的内容，下游按哪份为准都会出错。

        取舍说明：
        - 表格块的 ``text`` 恒为空，正文在 ``table_body``（HTML）。去标签后保留
          单元格文字，会丢掉行列结构——需要结构的下游应该读 ``blocks`` /
          ``markdown``，这里只保证「内容不丢」。
        - 表格/图片块的 ``text`` 为空时退回 caption + footnote，避免纯图表标注
          的块整个消失。
        - 页眉/页脚/页码**照常返回块自身文本**，是否并入正文由调用方决定
          （``_extract_text_from_content_list`` 不并入；layout 的 ``blocks[]``
          保留它，仅不汇总进 ``page["text"]``）。
        """
        block_type = str(block.get("type") or "")

        text = str(block.get("text") or "").strip()
        table_body = str(block.get("table_body") or "").strip()
        if block_type == "table" and table_body:
            text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", table_body))).strip()

        # caption / footnote 只在正文为空时回退使用——**不拿标题顶替真实内容**。
        # 「表 1 借款明细」这类表题确实有信息量，但既有约定（见
        # test_text非空时不使用标题覆盖）是正文优先；两条路径必须同源，
        # 否则 ``text`` 与 ``blocks`` 会给出不同结果。
        if not text:
            captions = block.get("table_caption") or block.get("image_caption") or []
            footnotes = block.get("table_footnote") or block.get("image_footnote") or []
            if isinstance(captions, str):
                captions = [captions]
            if isinstance(footnotes, str):
                footnotes = [footnotes]
            text = " ".join(str(item).strip() for item in [*captions, *footnotes] if str(item).strip())

        return text

    def _extract_page_layout_from_content_list(self, content_list_path: Path) -> dict[str, Any]:
        """保留 MinerU 内容块的原始页码、版面框与表格数据。"""
        try:
            content_list = json.loads(content_list_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 MinerU content_list 版面失败: %s", exc)
            return {"page_count": 0, "pages": []}

        raw_page_indices = [
            int(block["page_idx"])
            for block in content_list
            if isinstance(block, dict) and str(block.get("page_idx", "")).lstrip("-").isdigit()
        ]
        zero_based = 0 in raw_page_indices
        page_map: dict[int, dict[str, Any]] = {}
        for block in content_list:
            if not isinstance(block, dict):
                continue
            raw_page_idx = block.get("page_idx")
            try:
                page_idx = int(str(raw_page_idx))
            except (TypeError, ValueError):
                continue
            page_no = page_idx + 1 if zero_based else page_idx
            if page_no < 1:
                continue

            block_type = str(block.get("type") or "")
            # 文本口径与 ``_extract_text_from_content_list`` 共用同一个方法：
            # ``parsed.text`` 与 ``parsed.blocks`` 必须给出同一份内容。
            block_text = self._content_block_text(block)
            table_body = str(block.get("table_body") or "").strip()

            page = page_map.setdefault(page_no, {"page_no": page_no, "blocks": [], "text": ""})
            page["blocks"].append(
                {
                    "type": block_type,
                    "text_level": block.get("text_level"),
                    "text": block_text,
                    "bbox": block.get("bbox") or block.get("box"),
                    "table_body": table_body or None,
                }
            )
            if block_type not in {"header", "footer", "page_number"} and block_text:
                page["text"] = f"{page['text']}\n{block_text}".strip()

        pages = [page_map[page_no] for page_no in sorted(page_map)]
        return {"page_count": max(page_map, default=0), "pages": pages, "page_index_base": 0 if zero_based else 1}

    def _merge_layout_json_details(self, layout: dict[str, Any], layout_file: Path) -> None:
        """把 layout.json 的页面尺寸与行级 box 原地补进 content_list 版 layout。

        为什么需要：content_list.json 只有块级 bbox，既没有页面尺寸（归一化坐标时
        缺宽高会退化成「无坐标」），也没有行/span 级 box，无法定位到「这一行可能认错了」。
        同一个 ZIP 里的 layout.json 两样都有（坐标同为千分比 0-1000）。

        做法刻意是**合并而非替换**：page_no 与 blocks 仍以 content_list 为准（那是当前
        主路径，且 content_list 覆盖了 layout.json 里 discarded_blocks 之外的正文顺序），
        layout.json 只贡献它独有的字段（width/height、blocks[].lines）。

        降级：文件缺失 / JSON 损坏 / 结构不符时保持 layout 原样，只记 warning。

        Args:
            layout: ``_extract_page_layout_from_content_list`` 的返回值（原地修改）。
            layout_file: 结果 ZIP 内的 layout.json 路径。
        """
        page_details = self._parse_layout_json(layout_file)
        if not page_details:
            return

        pages = layout.get("pages")
        if not isinstance(pages, list):
            return

        for page in pages:
            if not isinstance(page, dict):
                continue
            page_no = page.get("page_no")
            try:
                page_no = int(str(page_no))
            except (TypeError, ValueError):
                continue
            detail = page_details.get(page_no)
            if detail is None:
                continue

            if detail.get("width") and detail.get("height"):
                page["width"] = detail["width"]
                page["height"] = detail["height"]

            page_blocks = page.get("blocks")
            if not isinstance(page_blocks, list):
                continue
            self._attach_block_lines(page_blocks, detail.get("blocks") or [])

    def _attach_block_lines(self, page_blocks: list[Any], detail_blocks: list[dict[str, Any]]) -> None:
        """把 layout.json 的行级信息按页内顺序对回 content_list 的块。

        为什么**不能**按 bbox 相等对：实测两者坐标单位不同（同一个「地址：…」块）：

        =======================  =========================  ============
        content_list.json          [209, 89, 666, 118]        千分比 0-1000
        layout.json                [128, 90, 408, 119]        绝对像素（612×1008）
        =======================  =========================  ============

        换算式：``209 / 1000 × 612 = 127.9 ≈ 128``。所以 content_list 是千分比、
        layout.json 是像素（与 ``bbox.py`` 里 ``resolve_bbox_unit('mineru') == 'permille'``
        的判断一致——主路径走 content_list）。任何跨文件的 bbox 相等比较都恒不成立。

        为什么可以按顺序对：两个文件是同一页的同一排版顺序，逐块 zip 实测完全对应；
        差别只在 content_list 额外带了 ``header`` / ``footer`` / ``page_number``
        这些被 layout.json 放进 ``discarded_blocks`` 的块。因此这里**跳过非正文块**
        再顺序推进，而不是按下标硬切。

        对不上的块保持没有 ``lines`` 字段——宁可承认「这行拿不到行级坐标」，
        也不把邻近块的行粘过来。

        只有普通正文块挂 ``lines``：表格/图片块在 layout.json 里的那一行是**整块**
        的 box（与块 bbox 完全重合，实测如此），不是单元格几何。给它挂 ``lines``
        会让下游误以为能按行/单元格定位表格内容，所以这类块只拿 ``html``，
        行级坐标如实为空。
        """
        cursor = 0
        for page_block in page_blocks:
            if not isinstance(page_block, dict):
                continue
            block_type = normalize_block_type(str(page_block.get("type") or ""))
            if block_type in NON_BODY_BLOCK_TYPES:
                continue  # 页眉页脚在 layout.json 的 discarded_blocks 里，不参与对齐
            if cursor >= len(detail_blocks):
                return
            detail_block = detail_blocks[cursor]
            cursor += 1

            if block_type in _NO_LINE_LEVEL_BLOCK_TYPES:
                # 表格/图片只有整块坐标，行级信息按空列表如实反映（不为空就不写字段）
                page_block["lines"] = []
            else:
                page_block["lines"] = detail_block["lines"]
            if detail_block.get("html"):
                page_block["html"] = detail_block["html"]

    def _parse_layout_json(self, layout_file: Path) -> dict[int, dict[str, Any]]:
        """解析 MinerU 结果 ZIP 里的 layout.json，按页码返回页面尺寸与块级行信息。

        返回形状（页码为 1 起，与 content_list 主路径同一口径）::

            {1: {"width": 612, "height": 1008,
                 "blocks": [{"type": "text", "bbox": [...],
                             "lines": [{"bbox": [...],
                                        "spans": [{"bbox": [...], "type": "text",
                                                    "content": "..."}]}]}]}}

        为什么只用 ``preproc_blocks``：它与 content_list 是同一粒度的正文视图，
        ``para_blocks`` 是更粗的段落合并视图，``discarded_blocks`` 是页眉页脚（不进正文）。

        表格/图片块在这里**会**解析出一行，但其 bbox 与整块 bbox 完全重合、表格内容
        装在 ``spans[].html``——它不提供单元格几何。是否把它当行级坐标用由
        ``_attach_block_lines`` 判断（这两类块的 ``lines`` 会被置空），本函数只管如实取值。

        Args:
            layout_file: layout.json 路径。

        Returns:
            ``{页码: 页面详情}``；文件损坏或结构不符时返回空字典（调用方据此降级）。
        """
        try:
            raw = json.loads(layout_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 MinerU layout.json 失败，按无行级坐标处理: %s", exc)
            return {}

        pdf_info = raw.get("pdf_info") if isinstance(raw, dict) else None
        if not isinstance(pdf_info, list):
            logger.warning("MinerU layout.json 结构不符（缺少 pdf_info 列表），按无行级坐标处理")
            return {}

        pages: dict[int, dict[str, Any]] = {}
        for page_info in pdf_info:
            if not isinstance(page_info, dict):
                continue
            try:
                # layout.json 的 page_idx 与 content_list 一致是 0 起，统一转 1 起页码
                page_no = int(str(page_info.get("page_idx"))) + 1
            except (TypeError, ValueError):
                continue
            if page_no < 1:
                continue

            page_size = page_info.get("page_size")
            width: float | None = None
            height: float | None = None
            if isinstance(page_size, (list, tuple)) and len(page_size) >= 2:
                try:
                    width = round(float(page_size[0]), 2)
                    height = round(float(page_size[1]), 2)
                except (TypeError, ValueError):
                    width = height = None

            blocks: list[dict[str, Any]] = []
            preproc_blocks = page_info.get("preproc_blocks")
            for raw_block in preproc_blocks if isinstance(preproc_blocks, list) else []:
                if not isinstance(raw_block, dict):
                    continue
                blocks.append(self._parse_layout_block(raw_block))

            pages[page_no] = {"width": width, "height": height, "blocks": blocks}

        return pages

    def _parse_layout_block(self, raw_block: dict[str, Any]) -> dict[str, Any]:
        """把 layout.json 的一个 ``preproc_blocks`` 条目转成块级行信息。

        两类形状要一起吃下：
        - 文本块：``lines[].spans[]`` 直接挂在块上（span.type == "text"，内容是 ``content``）
        - 表格/图片块：块上没有 ``lines``，只有子块 ``blocks[]``（table_body / image_body），
          那一行挂在子块里（span.type == "table" 装 ``html``，``image`` 装 ``image_path``）

        子块存在时以子块为准：那才是 MinerU 给出实际几何的一层。
        """
        block_type = str(raw_block.get("type") or "")
        lines_source = raw_block.get("lines")
        if not isinstance(lines_source, list):
            lines_source = []
            child_blocks = raw_block.get("blocks")
            for child in child_blocks if isinstance(child_blocks, list) else []:
                if not isinstance(child, dict):
                    continue
                child_lines = child.get("lines")
                if isinstance(child_lines, list):
                    lines_source.extend(child_lines)

        lines: list[dict[str, Any]] = []
        html = ""
        for raw_line in lines_source:
            if not isinstance(raw_line, dict):
                continue
            spans: list[dict[str, Any]] = []
            raw_spans = raw_line.get("spans")
            for raw_span in raw_spans if isinstance(raw_spans, list) else []:
                if not isinstance(raw_span, dict):
                    continue
                span_html = str(raw_span.get("html") or "")
                if span_html and not html:
                    html = span_html
                spans.append(
                    {
                        "bbox": raw_span.get("bbox"),
                        "type": str(raw_span.get("type") or ""),
                        "sub_type": raw_span.get("sub_type"),
                        "content": str(raw_span.get("content") or ""),
                    }
                )
            lines.append({"bbox": raw_line.get("bbox"), "spans": spans})

        return {
            "type": block_type,
            "sub_type": raw_block.get("sub_type"),
            "bbox": raw_block.get("bbox"),
            "lines": lines,
            "html": html,
        }

    def _merge_model_json_lines(self, layout: dict[str, Any], model_file: Path) -> None:
        """把 model.json 的 ocr_text 逐行框原地挂到 content_list 版 layout 的 text 块上。

        为什么需要单独一份：content_list 只有块级 bbox，layout.json 的行 box 实测
        与块 bbox 完全重合（是「整块又是一行」，不是真实逐行）。model.json 里的
        ``ocr_text`` 才是逐行坐标，缺了它就没有「块里第几行在哪」这层信息。

        为什么与 ``_merge_layout_json_details`` 顺序无关：两者写不同字段
        （``lines``/``html``/页面宽高 vs ``line_boxes``），且各自只读自己的文件，
        互不依赖对方的输出。

        降级：文件缺失 / JSON 损坏 / 结构不符时保持 layout 原样，只记 warning。

        Args:
            layout: ``_extract_page_layout_from_content_list`` 的返回值（原地修改）。
            model_file: 结果 ZIP 内的 model.json 路径。
        """
        page_lines = self._parse_model_json_lines(model_file)
        if not page_lines:
            return

        pages = layout.get("pages")
        if not isinstance(pages, list):
            return

        for page in pages:
            if not isinstance(page, dict):
                continue
            try:
                page_no = int(str(page.get("page_no")))
            except (TypeError, ValueError):
                continue
            ocr_lines = page_lines.get(page_no)
            if not ocr_lines:
                continue  # 表格页实测 0 个 ocr_text：不挂行框就是如实反馈

            page_blocks = page.get("blocks")
            if not isinstance(page_blocks, list):
                continue
            self._attach_ocr_text_lines(page_blocks, ocr_lines)

    def _parse_model_json_lines(self, model_file: Path) -> dict[int, list[dict[str, Any]]]:
        """解析 MinerU 结果 ZIP 里的 model.json，按页码返回 ocr_text 的逐行框。

        返回形状（页码为 1 起，与 content_list 主路径同一口径）::

            {1: [{"bbox": [519, 630, 716, 652], "type": "ocr_text"}, ...]}

        为什么是二维数组：model.json 外层是页、内层是该页的元素（实测第一页 29 个元素，
        其中 15 个 ocr_text），没有 ``pdf_info`` 包装，与 layout.json 完全不同的结构。

        为什么只取 ``ocr_text``：只有它带逐行 bbox 且没有文字（``text`` 恒为空、
        ``score`` 恒为 1.0，两者都是假数据，一律不用）。其它类型的元素 bbox
        已经由 content_list 提供，重复取无意义。

        为什么必须乘 1000：model.json 的 bbox 是**归一化 0-1**（实测
        ``[0.209, 0.088, 0.666, 0.11]``），而 content_list 是千分比 0-1000
        （同一块 ``[209, 89, 666, 118]``）、layout.json 是绝对像素。不统一口径就无法
        拿 ocr_text 去和 text 块的 bbox 做任何比较。

        Args:
            model_file: model.json 路径。

        Returns:
            ``{页码: [行框]}``；文件损坏或结构不符时返回空字典（调用方据此降级）。
        """
        try:
            raw = json.loads(model_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 MinerU model.json 失败，按无逐行坐标处理: %s", exc)
            return {}

        if not isinstance(raw, list):
            logger.warning("MinerU model.json 结构不符（顶层不是页数组），按无逐行坐标处理")
            return {}

        pages: dict[int, list[dict[str, Any]]] = {}
        for page_index, page_elements in enumerate(raw):
            # 外层下标即页序（与 content_list 的 page_idx 一致是 0 起），统一转 1 起页码
            page_no = page_index + 1
            if not isinstance(page_elements, list):
                continue

            lines: list[dict[str, Any]] = []
            for element in page_elements:
                if not isinstance(element, dict):
                    continue
                if str(element.get("type") or "") != "ocr_text":
                    continue
                bbox = self._scaled_model_bbox(element.get("bbox"))
                if bbox is None:
                    continue
                lines.append({"bbox": bbox, "type": "ocr_text"})

            if lines:
                pages[page_no] = lines

        return pages

    def _scaled_model_bbox(self, raw_bbox: Any) -> list[int] | None:
        """把 model.json 的归一化 bbox（0-1）换算成千分比整数。

        坐标非法时返回 None 而不是猜 0：0 会变成一个位于页角、看起来「能对上」的假框。
        """
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return None
        try:
            values = [round(float(raw_bbox[index]) * _MODEL_JSON_BBOX_SCALE) for index in range(4)]
        except (TypeError, ValueError):
            return None
        return values

    def _attach_ocr_text_lines(
        self,
        page_blocks: list[Any],
        ocr_lines: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """把 ocr_text 的行框按 y 范围对回 text 块，给出逐行坐标（``line_boxes``）。

        匹配规则（刻意严格，宁可对不上也不猜）：

        1. ocr_text 的 y 范围**完全落在** text 块的 y 范围内（±5 千分比容差）——
           只有完全包在块里的行才属于这个块，跨出块边的要么是邻块的行，
           要么是块 bbox 本身偏了，两种都不该硬配。
        2. x 范围有重叠——横向必须落在同一列；只有 y 重叠的话，同高的左右两栏
           会把彼此的行偷走。
        3. 匹配到的框数**必须等于**块内非空行数（``content.split("\n")`` 去掉空行），
           否则**放弃**、不挂 ``line_boxes``。框数与行数不等时无从知道哪行配哪个框，
           硬配就是编造坐标。
        4. 匹配成功后按 y 升序排列，与 content 的行序一一对应（MinerU 的 ocr_text
           在数组里也是 y 递增，但排序不依赖这个巧合）。

        为什么不管页眉页脚：实测 ocr_text 根本不含页眉（header 块匹配到 0 个框），
        所以只处理 ``text`` 块，header/footer/page_number 一律不动——不为它们
        去「找框凑数」。

        为什么表格/图片块不管：内容装在 html 里，行意义不同，它们的行级坐标
        本就该是空的（见 ``_NO_LINE_LEVEL_BLOCK_TYPES``）。

        Args:
            page_blocks: content_list 版的页内块列表（原地修改）。
            ocr_lines: ``_parse_model_json_lines`` 给出的该页行框（千分比）。

        Returns:
            ``(挂上 line_boxes 的块数, 尝试过但放弃的块数)``，供调用方记日志。
        """
        attached = 0
        skipped = 0

        for page_block in page_blocks:
            if not isinstance(page_block, dict):
                continue
            # 只认 content_list 原生的 ``text``：标题等其它正文类型行数与块粒度不一致，
            # 页眉页脚则本身就横平竖直地和 ocr_text 错开（实测 0 框）。
            if str(page_block.get("type") or "") != BLOCK_TYPE_TEXT:
                continue

            text = str(page_block.get("text") or "")
            line_count = len([line for line in text.split("\n") if line.strip()])
            if line_count < 1:
                continue

            block_bbox = self._permille_bbox(page_block.get("bbox"))
            if block_bbox is None:
                continue

            matched = self._match_ocr_lines_in_block(block_bbox, ocr_lines)
            if len(matched) != line_count:
                # 红线：框数 != 行数就放弃。记录差多少，便于判断是「折行但 content 没 \n」
                # 还是「块 bbox 本身偏了」。
                skipped += 1
                logger.debug(
                    "ocr_text 行框数与块行数不一致，不挂 line_boxes: 框=%d 行=%d 块=%s 文本=%r",
                    len(matched),
                    line_count,
                    block_bbox,
                    text[:30],
                )
                continue

            # 按 y 升序 = 阅读顺序，与 content 的行序一致
            matched.sort(key=lambda line: (line[1], line[0]))
            page_block["line_boxes"] = [{"bbox": line} for line in matched]
            attached += 1

        return attached, skipped

    def _match_ocr_lines_in_block(
        self,
        block_bbox: list[int],
        ocr_lines: list[dict[str, Any]],
    ) -> list[list[int]]:
        """找出完全落在该 text 块内、且横向同列的所有 ocr_text 框（千分比）。

        规则见 ``_attach_ocr_text_lines``：y 完全包含（±容差）、x 有重叠。
        只返回框本身，不在这里判行数——数量是否吻合由调用方裁决。
        """
        block_x0, block_y0, block_x1, block_y1 = block_bbox
        matched: list[list[int]] = []
        for line in ocr_lines:
            line_bbox = self._permille_bbox(line.get("bbox"))
            if line_bbox is None:
                continue
            line_x0, line_y0, line_x1, line_y1 = line_bbox
            # y 完全包含：行的上下边都在块内（留容差）
            if line_y0 < block_y0 - _OCR_LINE_BBOX_TOLERANCE:
                continue
            if line_y1 > block_y1 + _OCR_LINE_BBOX_TOLERANCE:
                continue
            # x 有重叠：横向必须落在同一列
            if min(line_x1, block_x1) - max(line_x0, block_x0) <= 0:
                continue
            matched.append(line_bbox)
        return matched

    def _permille_bbox(self, raw_bbox: Any) -> list[int] | None:
        """把千分比 bbox 归一为 4 个整数 ``[x0, y0, x1, y1]``；非法时返回 None。

        content_list 的 bbox 实测已是 0-1000 整数，这里只做「取整 + 校验形状」，
        不再换算，避免把已经是千分比的坐标再乘一次 1000。
        """
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return None
        try:
            return [round(float(raw_bbox[index])) for index in range(4)]
        except (TypeError, ValueError):
            return None

    def _collect_header_texts_from_content_list(self, content_list_path: Path) -> list[str]:
        """从 content_list.json 收集 header 类型的文本（用于清理 markdown）

        markdown 输出路径直接读取 md 文件，会包含页眉文本，
        需收集已知页眉后从 markdown 中删除。

        Args:
            content_list_path: content_list.json 文件路径

        Returns:
            页眉文本列表（去重）
        """
        try:
            with open(content_list_path, encoding="utf-8") as f:
                content_list = json.load(f)
        except Exception as e:
            logger.warning("读取 content_list.json 失败: %s", e)
            return []

        return collect_header_texts(content_list, header_type="header")
