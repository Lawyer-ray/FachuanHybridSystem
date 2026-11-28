"""
PaddleOCR API 云端引擎

调用百度 AI 开放平台的 PaddleOCR API，支持：
- PP-OCRv5：纯文字 OCR，适合证件/快递单号/简单文字提取
- PP-StructureV3：文档结构化分析，适合表格/版面分析
- PaddleOCR-VL：版面分析 + OCR（输出 Markdown），适合复杂文档/合同
- PaddleOCR-VL-1.5：VL 升级版，更高精度版面分析，适合法律文书/密集排版文档

API_URL / Token 通过 SystemConfig 管理。
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx

from apps.core.services.system_config_service import SystemConfigService
from apps.document_parsing.services.credential_pool import failure_reason_of_active_exception, get_credential_pool

# 拆分后的原地 re-export：实现已下沉到兄弟模块，路径不变——调用方与单测
# 仍按 ``paddleocr_api_service.<名字>`` import，公开签名与行为一致。
#   - 纯解析层（结果数据类、表格几何 / 方向解析、HTML 表格 → GFM、模型键归一）
#     → ``paddleocr_response_parser``
#   - 图片落盘（``persist_images``）→ ``paddleocr_image_store``
# 私有正则表（``_TABLE_RE`` 等）与 ``_PAGE_ANGLES`` / ``_TABLE_CELL_TAG_RE``
# 只在解析层内部使用，不再从本模块透出。
from .paddleocr_image_store import persist_images
from .paddleocr_response_parser import (
    _DOC_ORIENTATION_MODELS,
    _LAYOUT_ENDPOINT_MODELS,
    _MODEL_API_NAME_MAP,
    _OCR_ENDPOINT_MODELS,
    _STRUCTURED_TABLE_MODEL,
    PaddleOCRApiImage,
    PaddleOCRApiResult,
    ParsedPageOrientation,
    ParsedTableResult,
    _as_cell_boxes,
    _as_image_size,
    _as_page_angle,
    _as_pixel_box,
    _as_pruned_result,
    _as_rec_texts,
    _as_text_boxes,
    _cell_text,
    _collect_markdown_images,
    _convert_html_tables_to_markdown,
    _count_html_cells,
    _html_table_to_markdown,
    _layout_pages,
    _page_orientation,
    _parse_pruned_tables,
    _parse_table_entry,
    _replace_html_table,
    _span_value,
    normalize_model_key,
    parse_page_orientations,
    parse_table_results,
    parse_table_results_by_page,
)

logger = logging.getLogger(__name__)

# 全部模型统一走 v2 异步 Job API 的单一端点。
#
# 历史包袱：早期是「每模型一个 URL」的同步端点（PADDLEOCR_OCR_API_URL /
# PADDLEOCR_VL_API_URL / PADDLEOCR_VL15_API_URL），那些 aistudio 体验域名已全部
# 失效（返回 500）。v2 Job API 用同一个 URL + `model` 参数区分产品线。
_UNIFIED_JOB_API_URL_KEY = "PADDLEOCR_JOB_API_URL"

# 兼容保留：旧配置键仍在库中时不再被读取（迁移 0012 已删除，此处仅防御性兜底）
_MODEL_URL_KEY_MAP: dict[str, str] = dict.fromkeys(_MODEL_API_NAME_MAP, _UNIFIED_JOB_API_URL_KEY)

# 文件类型：0=PDF, 1=图片
_FILE_TYPE_PDF = 0
_FILE_TYPE_IMAGE = 1

# ── 轮询总超时预算 ────────────────────────────────────────────
#
# 历史值 120s 是纯经验拍出来的，实测单页 PaddleOCR-VL-1.6 就要 ~29s，
# 多页 PDF（整份文件上传，服务端逐页跑）必然超过 120s → 每次都走到「Job 超时」，
# 识别成果白等。所以下限抬到 300s：单页也留足 10 倍余量，抵住服务端排队抖动。
_JOB_TIMEOUT_FLOOR_SECONDS = 300.0
# 每页按「单页实测 × 安全系数」计预算。50s 足够覆盖实测的 29s
# （版面分析 + OCR + 表格识别都在里面），又不至于让一份 100 页的 PDF 把
# 上游 web 请求吊死到几小时。
_JOB_TIMEOUT_PER_PAGE_SECONDS = 50.0

# 轮询间隔（秒）。服务端单页要几十秒，3s 间隔既能较快感知 done，
# 也不会把 Job 查询打成刷接口。
_POLL_INTERVAL_SECONDS = 3.0

# 连接级重试次数。
#
# ⚠️ 语义必须说清楚：``httpx.HTTPTransport(retries=N)`` **只对「连接建立失败」生效**
# （DNS 解析失败、TCP 建连被拒/超时），它不会重发已经送出去的请求。
# 提交任务这类非幂等 POST 因此不会被重复提交——这正是我们想要的；
# 而「请求发出去了但服务端 5xx / 连接中途断开」由下面的轮询容忍逻辑处理。
_HTTP_CONNECT_RETRIES = 2

# 分级超时（秒）。
#
# 为什么要分级而不是给一个总数：
# - connect 短：连不上就是连不上，快速失败让上层尽早重试/告警，不必干等；
# - read/write 长：上传整份 PDF（几 MB~几十 MB）与下载结果 JSON 都可能很慢，
#   给短了会在慢网络下平白失败；
# - pool 短：连接池排队说明并发打满了，等太久只是把请求堆在内存里。
_HTTP_CONNECT_TIMEOUT_SECONDS = 10.0
_HTTP_POOL_TIMEOUT_SECONDS = 10.0

# 轮询（GET 状态 / 下载结果）的读超时：单次读操作的上限，与「Job 总时长」无关。
_HTTP_POLL_READ_TIMEOUT_SECONDS = 60.0
# 提交（POST multipart 上传整份文件）的读写超时，上传慢于轮询是常态。
# 文件越大传得越久，但生命周期总上限由调用方传入的 job_timeout 兜底。
_HTTP_SUBMIT_READ_TIMEOUT_SECONDS = 120.0

# 轮询时允许的「连续失败」次数（5xx / 429 / 网络抖动）。
#
# 为什么要容忍：Job 已经在服务端跑着，一次 502 或一次 keep-alive 连接被对端
# 掐断，并不代表任务失败；立刻抛错等于把已经烧掉的算力白白丢掉。
# 但也不能无限容忍——连续失败往往意味着端点真的挂了，所以超阈值才抛，
# 并且必须是「连续」而非「累计」，偶发抖动不会把额度耗光。
_MAX_CONSECUTIVE_POLL_FAILURES = 5


def _read_extract_progress(poll_data: dict[str, Any]) -> tuple[int, int | None] | None:
    """从轮询响应里取 ``data.extractProgress``；取不到返回 None。

    服务端未给出 totalPages 时 total 返回 None（下游自己决定展示方式），
    不编造 100% 之类的假进度。脏数据（非 int、负数）一律当未知丢弃。
    """
    payload = poll_data.get("data")
    if not isinstance(payload, dict):
        return None
    progress = payload.get("extractProgress")
    if not isinstance(progress, dict):
        return None

    # 服务端字段可能缺省为 None，直接 int(None) 会抛；先取出来再判定。
    raw_extracted = progress.get("extractedPages")
    if raw_extracted is None:
        return None
    try:
        extracted = int(raw_extracted)
    except (TypeError, ValueError):
        return None
    if extracted < 0:
        return None

    raw_total = progress.get("totalPages")
    total: int | None = None
    if raw_total is not None:
        try:
            total = int(raw_total)
        except (TypeError, ValueError):
            total = None
    if total is not None and total <= 0:
        total = None
    return extracted, total


def _safe_report_progress(
    on_progress: Callable[[int, int | None], None] | None,
    extracted: int,
    total: int | None,
) -> None:
    """调用进度回调，**任何异常都吞掉**。

    回调是旁路观测手段（前端进度条/日志），识别结果才是主目标；
    回调自身写库失败、连接已断等异常绝不允许把识别任务弄挂。
    """
    if on_progress is None:
        return
    try:
        on_progress(extracted, total)
    except Exception as exc:  # 回调异常必须被隔离，不能影响识别
        logger.warning("PaddleOCR 进度回调异常（已忽略）: %s", exc)


def _is_pollable_failure(status_code: int) -> bool:
    """该状态码是否算「可容忍的瞬时失败」。

    5xx 是服务端临时故障，429 是限流——两者都会自愈，值得再等下一轮；
    4xx（鉴权失败、jobId 不存在等）重试一百次也一样，必须立刻失败。
    """
    return status_code >= 500 or status_code == 429


def _default_job_timeout(page_count: int | None = None) -> float:
    """按页数算轮询总超时（秒）。

    公式：``max(基准下限 300s, 页数 × 单页预算 50s)``。
    页数未知（None）时只用基准下限——不能瞎猜，也不为此引入 PDF 解析依赖。

    为什么用 max 而不是「下限 + 页数×预算」：OCR 并行度不确定，页数少时按页
    算出来的值会小于单页实测余量，取 max 保证任何情况都不低于 300s。
    """
    if not page_count or page_count <= 0:
        return _JOB_TIMEOUT_FLOOR_SECONDS
    return max(_JOB_TIMEOUT_FLOOR_SECONDS, float(page_count) * _JOB_TIMEOUT_PER_PAGE_SECONDS)


def _build_http_timeout(read_timeout: float) -> httpx.Timeout:
    """构造分级超时：连接/池短，读/写长（理由见上方常量注释）。"""
    return httpx.Timeout(
        connect=_HTTP_CONNECT_TIMEOUT_SECONDS,
        read=max(read_timeout, _HTTP_POLL_READ_TIMEOUT_SECONDS),
        write=max(read_timeout, _HTTP_POLL_READ_TIMEOUT_SECONDS),
        pool=_HTTP_POOL_TIMEOUT_SECONDS,
    )


def _build_http_transport() -> httpx.HTTPTransport:
    """同步传输层：带连接级重试（只重试建连失败，不重发请求，见常量注释）。"""
    return httpx.HTTPTransport(retries=_HTTP_CONNECT_RETRIES)


def _build_async_http_transport() -> httpx.AsyncHTTPTransport:
    """异步传输层：与同步版同一套连接级重试语义。"""
    return httpx.AsyncHTTPTransport(retries=_HTTP_CONNECT_RETRIES)


class PaddleOCRApiEngine:
    """PaddleOCR API 云端引擎"""

    def _looks_like_json_noise(self, text: str) -> bool:
        """判断是否为结构化 JSON/调试噪声文本。"""
        candidate = text.strip()
        if len(candidate) < 10:
            return False

        if (candidate.startswith("{") and candidate.endswith("}")) or (
            candidate.startswith("[") and candidate.endswith("]")
        ):
            return True

        if re.search(r'"[A-Za-z_][\w-]*"\s*:', candidate):
            return True

        json_chars = sum(1 for c in candidate if c in '{}[]":,')
        if len(candidate) >= 30 and (json_chars / len(candidate)) > 0.30:
            return True

        return False

    def __init__(self, model: str | None = None, timeout: float | None = None) -> None:
        """
        初始化 PaddleOCR API 引擎

        Args:
            model: 模型名称，None 时从 SystemConfig 读取
            timeout: 轮询总超时（秒）。None（默认）表示按页数动态计算，
                见 ``_default_job_timeout``：单页/页数未知取基准下限 300s，
                已知页数取 ``max(300s, 页数 × 50s)``。显式传入则一律照用，
                方便测试与特殊场景压住上限。
        """
        self._model = model
        self._timeout = timeout
        self._config_service = SystemConfigService()
        # 凭证池的注册键。生产固定用 "paddleocr"（全部 Worker 共享同一池）；
        # 测试可用 ``_pool_key`` 属性改成唯一值，避免不同用例的失败冷却互相污染。
        self._pool_key = "paddleocr"

    @property
    def model(self) -> str:
        """当前模型的小写配置键（兼容库里的官方名写法）。"""
        raw = self._model or str(self._config_service.get_value("PADDLEOCR_API_MODEL", "pp_ocrv5") or "pp_ocrv5")
        return normalize_model_key(raw)

    @property
    def api_url(self) -> str:
        """获取 API URL（所有模型共用 v2 Job API 端点）"""
        url_key = _MODEL_URL_KEY_MAP.get(self.model, _UNIFIED_JOB_API_URL_KEY)
        return str(self._config_service.get_value(url_key, "") or "")

    @property
    def api_model_name(self) -> str:
        """配置里的模型键 → 服务端认可的官方模型名（发送给 API 的 `model` 字段）。"""
        return _MODEL_API_NAME_MAP.get(self.model, self.model)

    @property
    def api_tokens(self) -> list[str]:
        """解析配置里的全部 token（支持多 Key 并发，每行一个）。

        为什么需要多 token：PaddleOCR 单 Key 有明显的提交排队（实测会返回
        ``10010 任务提交队列已满``），而一份 164 页卷宗按页串行要 80 分钟。
        配置里允许每行填一个 Key，由凭证池轮询分配，既能并发又能绕开单 Key 限流。

        分隔符兼容：换行、逗号、分号都算——用户在 Admin textarea 里习惯不一，
        与其要求「必须换行」，不如都认。空行/空白自动丢弃，避免拿到空 token 去请求。
        """
        raw = str(self._config_service.get_value("PADDLEOCR_API_TOKEN", "") or "")
        return [part.strip() for part in re.split(r"[\r\n,;]+", raw) if part.strip()]

    @property
    def api_token(self) -> str:
        """首个可用 token（向后兼容：单 Key 部署下与旧行为一致）。

        ⚠️ 真实请求**不要**用它——多 Key 场景下必须走凭证池拿绑定 token，
        否则永远打第一个 Key，等于没配多 Key。保留此属性只是为了让
        ``_is_configured`` 与外部旧调用方不炸。
        """
        tokens = self.api_tokens
        return tokens[0] if tokens else ""

    def _credential_pool(self) -> Any:
        """取本引擎对应的凭证池（进程内共享）。

        复用 ``document_parsing`` 的 CredentialPool：它已经做好了轮询分配、
        每 Key 并发上限、按失败原因分档的冷却（瞬时 30s / 鉴权 30min / 额度耗尽到
        下一个配额重置点）与日额度记账。自己再写一份只会多一处语义漂移。

        并发上限固定为 1：PaddleOCR 的任务是「提交 → 轮询 → 下载」长周期，
        同一 Key 上并发多个 Job 更容易撞队列满。1 意味着「一 Key 同时只跑一单」，
        多 Key 才能真正并行。
        """
        tokens = self.api_tokens
        return get_credential_pool(
            provider_key=self._pool_key,
            credentials=tokens,
            concurrency_per_key=1,
        )

    def _is_configured(self) -> bool:
        """检查是否已配置必要的 API 参数"""
        return bool(self.api_url and self.api_tokens)

    def _resolve_job_timeout(self, page_count: int | None) -> float:
        """确定本次 Job 的轮询总超时（秒）。

        只此一处：同步/异步两个入口都调它，避免「同步改了异步忘改」的漂移。
        显式 timeout 优先（全部页数一视同仁），否则按页数动态算。
        """
        if self._timeout is not None:
            return float(self._timeout)
        return _default_job_timeout(page_count)

    def _poll_max_attempts(self, job_timeout: float) -> int:
        """轮询次数上限 = 总超时 / 轮询间隔。

        不用「总超时 / 单次请求超时」是因为 sleep 与请求耗时叠加后刻度难对齐；
        按间隔算出来就是「最多等 job_timeout 秒」这个直观含义。
        """
        return max(1, int(job_timeout / _POLL_INTERVAL_SECONDS))

    def _validate_submit_response(self, response: httpx.Response) -> dict[str, Any]:
        """校验提交响应并返回 jobId 所在的 data 段。同步/异步共用。"""
        if response.status_code != 200:
            logger.warning(
                "PaddleOCR API 提交失败: status=%d, body=%s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(f"PaddleOCR API 返回错误: HTTP {response.status_code}")

        resp_data: dict[str, Any] = response.json()
        if not resp_data.get("data", {}).get("jobId"):
            raise RuntimeError(f"PaddleOCR API 未返回 jobId: {resp_data}")
        return resp_data

    def _validate_result_download(self, response: httpx.Response) -> None:
        """校验结果下载响应。同步/异步共用。

        S43-03（2026-11-23 二轮审计）：原实现下载 jsonUrl 后不看状态码就直接解析。
        httpx 对 4xx/5xx 不抛异常，于是 403（直链过期）/5xx/网关 HTML 错误页会落到
        _parse_job_result：不是被当成「识别成功但一个字都没有」，就是把错误体里的
        字符串字段当成 OCR 正文返回。现在下载失败必须显式抛错。
        """
        if response.status_code != 200:
            raise RuntimeError(f"PaddleOCR API 结果下载失败: HTTP {response.status_code}, body={response.text[:200]}")

    def recognize_bytes(
        self,
        image_bytes: bytes,
        is_pdf: bool = False,
        page_count: int | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> PaddleOCRApiResult:  # pragma: no cover
        """
        识别图片/PDF字节数据中的文字

        使用异步 Job 模式：提交任务 → 轮询状态 → 获取结果。

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件
            page_count: 已知页数，用于按页扩展轮询超时；None 表示未知（只用基准下限）。
                不为了估页数去引入 PDF 解析依赖——调用方知道就传，不知道就不传。
            on_progress: 进度回调 ``on_progress(extracted, total)``。
                extracted 为已处理页数，total 为总页数，服务端未给出时 total 为 None。
                回调抛出的任何异常都会被吞掉（不能因为回调把识别弄挂）。

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        import time

        if not self._is_configured():
            raise RuntimeError("PaddleOCR API 未配置：请先在系统配置中设置 API URL 和 Token")

        model = self.model
        file_type = _FILE_TYPE_PDF if is_pdf else _FILE_TYPE_IMAGE

        # 构建可选参数
        optional_payload: dict[str, Any] = {
            "fileType": file_type,
        }
        if model in _OCR_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useTextlineOrientation": False,
                }
            )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            )

        # 从凭证池拿一个 Key，并在**整个任务周期**（提交 → 轮询 → 下载）绑定使用。
        # 绝不能提交用 A、轮询用 B：Job 归属提交者账号，换 Key 查会 404/无权限。
        pool = self._credential_pool()
        token_idx = pool.acquire()
        if token_idx is None:
            # 全部 Key 都在冷却（连续失败）——宁可明确报错，也不要拿失效 Key 硬打。
            raise RuntimeError("PaddleOCR API 所有凭证均在失败冷却中，请稍后重试")
        headers = {
            "Authorization": f"bearer {pool.credentials[token_idx]}",
        }
        # 任务是否成功：决定归还时是否让该 Key 进冷却。
        token_ok = False
        # 页数用于凭证池的日额度记账：图片固定 1 页，PDF 先看调用方给的页数，
        # 解析出逐页结构后再用实际页数记账（服务端回多少页就记多少页）。
        processed_pages = 1 if not is_pdf else int(page_count or 0)

        # multipart/form-data 上传。
        # `model` 必须发官方模型名（如 PaddleOCR-VL-1.6），不能发配置键（paddleocr_vl_1_6），
        # 否则服务端返回 400「模型传参错误」(code=10007)。
        data = {
            "model": self.api_model_name,
            "optionalPayload": json.dumps(optional_payload),
        }
        files = {
            "file": ("image.jpg", image_bytes, "image/jpeg"),
        }

        # 整份 PDF 一次上传，服务端逐页处理；页数已知就按页扩预算，否则用基准下限。
        job_timeout = self._resolve_job_timeout(page_count if is_pdf else None)
        max_polls = self._poll_max_attempts(job_timeout)

        logger.info(
            "PaddleOCR API 调用: model=%s (api_name=%s), file_type=%s, data_size=%d, job_timeout=%.0fs, max_polls=%d",
            model,
            self.api_model_name,
            file_type,
            len(image_bytes),
            job_timeout,
            max_polls,
        )

        # 连续失败计数：轮询期间的 5xx/429/网络抖动都能容忍，但只忍「连续」几次
        consecutive_failures = 0
        # 状态变化日志的去重标记：轮询可能几十轮，每轮刷一条日志只会淹没真实告警
        last_logged_state: str | None = None

        try:
            # 一个 Client 贯穿「提交 → 轮询 → 下载结果」：
            # 复用同一条 keep-alive 连接，省掉每轮重新 TLS 握手的开销；
            # 更重要的是不把 Client 建在轮询循环里，避免每 3 秒漏掉一批连接池。
            with httpx.Client(
                timeout=_build_http_timeout(_HTTP_SUBMIT_READ_TIMEOUT_SECONDS),
                transport=_build_http_transport(),
                follow_redirects=True,
            ) as client:
                # 提交 Job
                response = client.post(self.api_url, headers=headers, data=data, files=files)
                resp_data = self._validate_submit_response(response)
                job_id = resp_data["data"]["jobId"]

                logger.info("PaddleOCR API Job 已提交: jobId=%s", job_id)

                # 轮询 Job 状态
                for _ in range(max_polls):
                    time.sleep(_POLL_INTERVAL_SECONDS)

                    try:
                        poll_resp = client.get(f"{self.api_url}/{job_id}", headers=headers)
                    except httpx.TransportError as exc:
                        # 网络抖动（读超时、连接被对端关闭）不等于任务失败：
                        # Job 还在服务端跑着，下一轮很可能就恢复了。
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 轮询网络异常（连续第 %d/%d 次）: %s",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            exc,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: {exc}") from exc
                        continue

                    if poll_resp.status_code != 200:
                        if not _is_pollable_failure(poll_resp.status_code):
                            # 4xx（鉴权/jobId 不存在）重试无意义，立刻失败暴露问题
                            raise RuntimeError(f"PaddleOCR API 轮询失败: HTTP {poll_resp.status_code}")
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 轮询瞬时失败（连续第 %d/%d 次）: HTTP %d",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            poll_resp.status_code,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(
                                f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: HTTP {poll_resp.status_code}"
                            )
                        continue

                    # 走到这里说明服务端正常应答，连续失败计数归零
                    consecutive_failures = 0

                    poll_data = poll_resp.json()
                    payload = poll_data.get("data", {})
                    state = payload.get("state", "") if isinstance(payload, dict) else ""

                    if state != last_logged_state:
                        logger.info("PaddleOCR API Job 状态变化: jobId=%s, state=%s", job_id, state)
                        last_logged_state = state

                    if state == "done":
                        result_url = payload.get("resultUrl", {})
                        jsonl_url = result_url.get("jsonUrl", "") if isinstance(result_url, dict) else ""
                        if not jsonl_url:
                            raise RuntimeError("PaddleOCR API 完成但无 jsonUrl")

                        # 下载结果。jsonUrl 的返回形态**随输入类型不同**（实测）：
                        # - 传图片：单行完整 JSON（`{logId, result:{...}}`）
                        # - 传 PDF：**多行 JSONL**（每行带一部分页）
                        # 所以不能假定单行：_parse_job_result 先试完整 JSON，失败再逐行解。
                        result_resp = client.get(
                            jsonl_url, timeout=_build_http_timeout(_HTTP_POLL_READ_TIMEOUT_SECONDS)
                        )
                        # 下载失败（403/5xx/网关错误页）必须在解析前抛出，否则会被当成空结果。
                        self._validate_result_download(result_resp)
                        # 走到这里才算这个 Key 真的可用；finally 据此决定是否让它进冷却。
                        parsed = self._parse_job_result(result_resp.text, model)
                        token_ok = True
                        if parsed.layout_results:
                            processed_pages = len(parsed.layout_results)
                        return parsed

                    # 进度：done 时已无意义，只在处理中读取，避免把最后一跳重复报给调用方
                    progress = _read_extract_progress(poll_data)
                    if progress is not None:
                        _safe_report_progress(on_progress, *progress)

                    if state == "failed":
                        error_msg = payload.get("errorMsg", "未知错误")
                        raise RuntimeError(f"PaddleOCR API Job 失败: {error_msg}")

            raise RuntimeError(f"PaddleOCR API Job 超时（{job_timeout:.0f}s）")

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e
        finally:
            # 无论成功、失败还是抛异常，都必须归还槽位：
            # 遗忘一次就永久占住一个并发名额，多 Key 池会逐渐“假死”。
            # 失败档位按真实异常判定（401/403→auth，429/额度→quota，其余→transient）；
            # 只有成功时才能确定页数，失败不记账（部分消耗不可知，宁可不记也不双算）。
            pool.release(
                token_idx,
                success=token_ok,
                reason=failure_reason_of_active_exception(),
                pages=processed_pages if token_ok else 0,
            )

    def _parse_job_result(self, raw_text: str, model: str) -> PaddleOCRApiResult:
        """解析 Job API 的结果体。

        v2 Job API 的 jsonUrl 返回形态**随输入类型不同**（实测 2026-11-15，真实 Job API）：

        - **传图片**（单页 jpg）：单行完整 JSON，``{"logId": ..., "result": {...}}``，约 9k 字符；
        - **传 PDF**（多页）：**多行 JSONL**，每行带一部分页（5 页切片回 2 行、约 71k 字符），
          因为一页一条会把几百页的响应挤成几 MB 的单行。

        （``{"logId": ..., "result": {"ocrResults": [...]}}`` 是 OCR 类模型，版面类模型是
        ``result.layoutParsingResults``。）

        所以两者都必须支持：先试完整 JSON，失败再按 JSONL 逐行解析。
        只按单行解会让 PDF 路径的 ``layout_results`` 恒为空，双引擎比对拿不到 VL 数据。
        """
        text = raw_text.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
                return self._parse_response(parsed, model)
        return self._parse_jsonl_response(raw_text, model)

    def _parse_jsonl_response(self, jsonl_text: str, model: str) -> PaddleOCRApiResult:
        """解析 JSONL 格式的 PaddleOCR API 结果。

        每条 line 可能是 ``{"result": {...}}`` 外层包装，也可能是裸的 result，
        统一取到 ``result`` 再交给 ``_parse_response``，避免两套解析路径漂移。

        ⚠️ PDF 与图片的返回形态**不同**（实测）：
        - 传图片：单行完整 JSON
        - 传 PDF：**多行 JSONL**（每行带一部分页；实测 5 页切片回 2 行，
          行与页不是一一对应）
        所以 ``_parse_job_result`` 不能只按单行解——否则 PDF 路径拿到的
        ``layout_results`` 永远是空的，双引擎比对也就永远没有 VL 数据。
        （这也是为什么下面要**逐行累加**而不是取第一行。）
        """
        all_texts: list[str] = []
        # 逐页版面结构汇聚：多行 JSONL 时每行各自带一部分页面，必须合并而不是只取第一行。
        all_layout_results: list[dict[str, Any]] = []
        all_images: list[PaddleOCRApiImage] = []
        # 表格几何同样要跨行合并：PDF 一片可能切成多行 JSONL，只取某一行就会丢表。
        all_tables: list[ParsedTableResult] = []
        # 逐页的那一份按行序拼接：外层下标就是送检页序，交给调用方按页对齐。
        all_table_pages: list[list[ParsedTableResult]] = []
        # 方向同样逐页累加。**裸片段行不补位**：补了会让页序与 table_pages/layout_results
        # 错位一格，而错位一格就意味着把 A 页的 angle 用到 B 页上。
        all_orientations: list[ParsedPageOrientation] = []
        for line in jsonl_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue

            # 统一收敛到 `result`：有外层就剥掉，没有就当它本身就是 result。
            nested = item.get("result")
            result: dict[str, Any] = nested if isinstance(nested, dict) else item

            # 先看它是否带了预期的容器键（ocrResults / layoutParsingResults）。
            # 裸片段（如单独一行 ``{"rec_texts": [...]}``）没有容器结构，直接交给
            # `_parse_response` 会因找不到容器而返回空文本——历史流式响应里这很常见，
            # 所以这类行改走通用文本提取。
            has_container = isinstance(result.get("ocrResults"), list) or isinstance(
                result.get("layoutParsingResults"), list
            )
            if not has_container:
                # rec_texts 优先按行提取（保持原有顺序语义），否则走通用片段收集。
                rec_texts = self._collect_rec_texts(result)
                all_texts.extend(rec_texts if rec_texts else self._collect_text_fragments(result))
                continue

            try:
                parsed = self._parse_response({"result": result}, model)
            except RuntimeError:
                # 未知 model 类型时退回通用文本提取，不让一行坏数据弄挂整个任务
                all_texts.extend(self._collect_text_fragments(result))
                continue
            all_texts.extend(parsed.raw_texts)
            # 逐页结构与图片同样要合并：下游（双引擎比对）靠它们拿页码与 block 坐标，
            # 只汇总文本会让 PDF 路径的 layout_results 永远为空。
            all_layout_results.extend(parsed.layout_results)
            all_images.extend(parsed.images)
            all_tables.extend(parsed.tables)
            all_table_pages.extend(parsed.table_pages)
            all_orientations.extend(parsed.page_orientations)

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (JSONL) 识别完成: model=%s, text_len=%d, layout_pages=%d, images=%d",
            model,
            len(merged),
            len(all_layout_results),
            len(all_images),
        )
        return PaddleOCRApiResult(
            text=merged,
            raw_texts=all_texts,
            model=model,
            images=all_images,
            layout_results=all_layout_results,
            tables=all_tables,
            table_pages=all_table_pages,
            page_orientations=all_orientations,
        )

    def _parse_response(self, data: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """
        解析 API 响应

        PP-OCRv5 / PP-OCRv6 / PP-StructureV3: result.ocrResults[].prunedResult
        PaddleOCR-VL / VL-1.5 / VL-1.6: result.layoutParsingResults[].markdown.text
        """
        result = data.get("result", {})

        if model in _OCR_ENDPOINT_MODELS:
            parsed = self._parse_ocr_response(result, model)
            if model == _STRUCTURED_TABLE_MODEL:
                # PP-StructureV3 要**同时**读两个信封：正文仍只来自 ocrResults（调用方
                # 行为不变），量到的表格几何在 layoutParsingResults（见 parse_table_results）。
                parsed = replace(
                    parsed,
                    tables=parse_table_results(result),
                    table_pages=parse_table_results_by_page(result),
                )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            parsed = self._parse_layout_response(result, model)
        else:
            raise RuntimeError(f"不支持的 PaddleOCR 模型: {model}")

        # 方向逐页透出（单行 JSON 与 JSONL 两条路径共用本方法，所以挂在这里而不是各分支里）。
        orientations = parse_page_orientations(result)
        turned = [item.angle for item in orientations if item.angle]
        if turned:
            logger.info(
                "PaddleOCR 页面方向分类命中: model=%s, pages=%d, angles=%s（坐标在转正帧，需反变换）",
                model,
                len(orientations),
                turned,
            )
        return replace(parsed, page_orientations=orientations)

    def _collect_text_fragments(self, value: Any) -> list[str]:
        """从任意嵌套结构中提取可读文本片段。"""
        fragments: list[str] = []

        if value is None:
            return fragments

        if isinstance(value, str):
            text = value.strip()
            if text and not self._looks_like_json_noise(text):
                fragments.append(text)
            return fragments

        if isinstance(value, list):
            for item in value:
                fragments.extend(self._collect_text_fragments(item))
            return fragments

        if isinstance(value, dict):
            # 常见文本键优先，随后再遍历其余键，避免漏掉嵌套文本
            priority_keys = ("text", "value", "content", "prunedResult", "markdown")
            visited_keys: set[str] = set()

            for key in priority_keys:
                if key in value:
                    visited_keys.add(key)
                    fragments.extend(self._collect_text_fragments(value[key]))

            for key, item in value.items():
                if key in visited_keys:
                    continue
                fragments.extend(self._collect_text_fragments(item))

            return fragments

        text = str(value).strip()
        if text:
            fragments.append(text)

        return fragments

    def _collect_rec_texts(self, value: Any) -> list[str]:
        """仅提取 rec_texts 字段值（支持嵌套与 JSON 字符串）。"""
        texts: list[str] = []

        if value is None:
            return texts

        if isinstance(value, str):
            candidate = value.strip()
            if candidate.startswith("{") or candidate.startswith("["):
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    return texts
                return self._collect_rec_texts(parsed)
            return texts

        if isinstance(value, list):
            for item in value:
                texts.extend(self._collect_rec_texts(item))
            return texts

        if isinstance(value, dict):
            rec_values = value.get("rec_texts")
            if isinstance(rec_values, list):
                for rec in rec_values:
                    if isinstance(rec, str):
                        rec_text = rec.strip()
                        if rec_text:
                            texts.append(rec_text)

            for nested in value.values():
                texts.extend(self._collect_rec_texts(nested))

            if texts:
                # 去重并保持顺序
                deduplicated = list(dict.fromkeys(texts))
                return deduplicated

        return texts

    def _parse_ocr_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析 OCR 端点响应（PP-OCRv5 / PP-StructureV3）"""
        ocr_results = result.get("ocrResults", [])
        all_texts: list[str] = []
        rec_texts_hit = 0

        for item in ocr_results:
            pruned = item.get("prunedResult", "")
            rec_texts = self._collect_rec_texts(pruned)
            if rec_texts:
                rec_texts_hit += 1
                all_texts.extend(rec_texts)
                continue

            # 兼容兜底：当 rec_texts 缺失时，退回通用提取
            all_texts.extend(self._collect_text_fragments(pruned))

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (OCR) 识别完成: model=%s, text_len=%d, rec_texts_hit=%d/%d",
            model,
            len(merged),
            rec_texts_hit,
            len(ocr_results),
        )
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

    def _parse_layout_response(self, result: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """解析版面分析端点响应（PaddleOCR-VL / VL-1.5 / VL-1.6）。

        只取 ``markdown["text"]``：
        ``markdown`` 里还有 ``images``（相对路径 → bcebos 绝对 URL）。早期实现用
        ``_collect_text_fragments(markdown)`` 递归整个 dict，把图片 URL 当正文收进
        raw_texts（实测污染样如 ``https://pplines-online.bj.bcebos.com/...jpg``），
        下游会把链接当条款正文用。所以此处不走递归，正文只认 text 字符串。

        图片不丢：从 ``markdown["images"]`` 收集成 ``PaddleOCRApiImage``，由调用方
        决定是否下载/落盘（此时 data 为 None）。
        """
        layout_results = result.get("layoutParsingResults", [])
        all_texts: list[str] = []
        images: list[PaddleOCRApiImage] = []

        for item in layout_results:
            markdown_data = item.get("markdown", {})
            if not isinstance(markdown_data, dict):
                continue

            # 正文：只认 markdown["text"]。表中 HTML 表格在 PaddleOCR-VL 输出里很常见，
            # 原样输出会让下游 Markdown 渲染成一坨 raw HTML，所以先转 GFM 再切行。
            markdown_text = markdown_data.get("text")
            if isinstance(markdown_text, str) and markdown_text.strip():
                converted = _convert_html_tables_to_markdown(markdown_text)
                # 切分粒度与 _parse_ocr_response 一致：非空行即一条 raw_text
                all_texts.extend(line.strip() for line in converted.splitlines() if line.strip())

            images.extend(_collect_markdown_images(markdown_data.get("images")))

        merged = "\n".join(all_texts)
        logger.info(
            "PaddleOCR API (Layout) 识别完成: model=%s, text_len=%d, images=%d",
            model,
            len(merged),
            len(images),
        )
        # 逐页结构原样带上：双引擎比对靠它拿页码与 block 坐标（见 layout_results 字段注释）。
        # 只收 dict 项，脏数据直接滤掉——下游按「没有逐页结构」降级，不会拿到半个结果。
        layout_results_out = [item for item in layout_results if isinstance(item, dict)]
        return PaddleOCRApiResult(
            text=merged,
            raw_texts=all_texts,
            model=model,
            images=images,
            layout_results=layout_results_out,
        )

    def extract_text(self, image_bytes: bytes) -> PaddleOCRApiResult:
        """
        提取图片中的文字（兼容 OCRService 接口）

        Args:
            image_bytes: 图片字节数据

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        return self.recognize_bytes(image_bytes, is_pdf=False)

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> PaddleOCRApiResult:
        """
        提取 PDF 中的文字

        Args:
            pdf_bytes: PDF 字节数据

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        return self.recognize_bytes(pdf_bytes, is_pdf=True)

    def download_images(
        self,
        images: list[PaddleOCRApiImage],
        *,
        max_workers: int = 4,
        timeout: float = _HTTP_POLL_READ_TIMEOUT_SECONDS,
    ) -> list[PaddleOCRApiImage]:
        """把版面解析产出的图片（印章/照片/图表裁剪）真实下载下来。

        为什么需要这一步：``markdown["text"]`` 里引用的是 ``imgs/img_in_seal_box_xxx.jpg``
        这种**相对路径**，它在任何地方都不存在——真实地址在 ``markdown["images"]`` 的
        value 里（bcebos 签名 URL）。不下载的话，印章图在 Markdown 里就是一个死链；
        而卷宗里「这枚章盖在哪、是什么章」本身是证据，丢了就找不回来。

        设计取舍：
        - **只下载、不落盘**。本方法是纯传输层，不依赖 Django storage；落盘由调用方
          决定（见 ``persist_images``），这样 OCR 引擎能在 Celery / 脚本 / 测试里裸用。
        - **失败不抛**。单张图 404/超时不应该让整份识别结果作废：该图 ``data`` 保持
          None，调用方按「有 URL 没字节」降级处理（例如只存 URL 留待后补）。
        - **并发下载**。一页可能有十几张印章/照片，串行下载会让识别总耗时翻倍。
        - 签名 URL 会过期，所以下载必须紧跟在识别之后，不能留到第二天补。

        Args:
            images: 待下载的图片（来自 ``PaddleOCRApiResult.images``）
            max_workers: 并发数上限；太高会被对象存储限流
            timeout: 单张图的下载读超时

        Returns:
            与入参同序的新列表；已存在的 ``data`` 不会被覆盖。
        """
        if not images:
            return []

        # 已有字节的（例如上层重试第二次）不必重复下载。
        pending = [img for img in images if img.data is None and img.url]
        if not pending:
            return list(images)

        downloaded: dict[str, bytes] = {}

        def _fetch(image: PaddleOCRApiImage) -> tuple[str, bytes | None]:
            """下载单张图；任何失败都归为 None，由调用方降级处理。"""
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(
                        connect=_HTTP_CONNECT_TIMEOUT_SECONDS,
                        read=timeout,
                        write=timeout,
                        pool=_HTTP_POOL_TIMEOUT_SECONDS,
                    ),
                    transport=httpx.HTTPTransport(retries=_HTTP_CONNECT_RETRIES),
                    follow_redirects=True,
                ) as client:
                    resp = client.get(image.url)
                if resp.status_code != 200:
                    logger.warning(
                        "PaddleOCR 图片下载失败: key=%s status=%d",
                        image.key,
                        resp.status_code,
                    )
                    return image.key, None
                return image.key, resp.content
            except httpx.HTTPError as exc:
                # 超时/连接错都是可容忍的：图丢了不阻断识别结果落地。
                logger.warning("PaddleOCR 图片下载异常: key=%s err=%s", image.key, exc)
                return image.key, None

        # 并发上限取 min(max_workers, 待下载数)：一张图时不必开线程池。
        workers = max(1, min(max_workers, len(pending)))
        if workers == 1:
            for image in pending:
                key, data = _fetch(image)
                if data is not None:
                    downloaded[key] = data
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=workers) as pool:
                for key, data in pool.map(_fetch, pending):
                    if data is not None:
                        downloaded[key] = data

        logger.info(
            "PaddleOCR 图片下载完成: 成功 %d/%d",
            len(downloaded),
            len(pending),
        )
        #
        # 回填字节：同一 key 可能对应多张（同页重复引用），统一按 key 查下载结果。
        # 未下载成功的图保持 data=None，但**保留 url**——上层可存 URL 等后补，
        # 比直接丢掉信息好。
        result: list[PaddleOCRApiImage] = []
        for img in images:
            if img.data is not None:
                result.append(img)
                continue
            payload = downloaded.get(img.key)
            if payload is None:
                result.append(img)
            else:
                result.append(
                    PaddleOCRApiImage(
                        key=img.key,
                        url=img.url,
                        data=payload,
                        content_type=img.content_type,
                    )
                )
        return result

    # ── 异步方法 ──────────────────────────────────────────────

    async def arecognize_bytes(
        self,
        image_bytes: bytes,
        is_pdf: bool = False,
        page_count: int | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> PaddleOCRApiResult:  # pragma: no cover
        """
        异步识别图片/PDF字节数据中的文字

        使用异步 Job 模式：提交任务 → 异步轮询（asyncio.sleep） → 获取结果。
        相比同步版本，轮询等待期间不阻塞事件循环。

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件
            page_count: 已知页数，用于按页扩展轮询超时；None 表示未知（只用基准下限）。
            on_progress: 进度回调 ``on_progress(extracted, total)``，语义与同步版一致：
                total 未知时为 None；回调抛出的任何异常都会被吞掉。

        Returns:
            PaddleOCRApiResult: 识别结果
        """
        import asyncio

        if not self._is_configured():
            raise RuntimeError("PaddleOCR API 未配置：请先在系统配置中设置 API URL 和 Token")

        model = self.model
        file_type = _FILE_TYPE_PDF if is_pdf else _FILE_TYPE_IMAGE

        optional_payload: dict[str, Any] = {"fileType": file_type}
        if model in _OCR_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useTextlineOrientation": False,
                }
            )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": model in _DOC_ORIENTATION_MODELS,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            )

        # 与同步版同一套凭证池逻辑：一个 Key 绑定整个任务周期，结束时归还。
        # 注意 acquire 是同步的（池用 threading.Lock），在协程里不可等待，
        # 但它只是几次加锁与数组访问，耗时极短，不会阻塞事件循环。
        pool = self._credential_pool()
        token_idx = pool.acquire()
        if token_idx is None:
            raise RuntimeError("PaddleOCR API 所有凭证均在失败冷却中，请稍后重试")
        headers = {"Authorization": f"bearer {pool.credentials[token_idx]}"}
        token_ok = False
        # 与同步版同口径：图片固定 1 页，PDF 先用调用方给的页数，结果带逐页结构再用实际页数
        processed_pages = 1 if not is_pdf else int(page_count or 0)

        # 同步版同一限制：必须发官方模型名，否则 400「模型传参错误」(code=10007)
        data = {"model": self.api_model_name, "optionalPayload": json.dumps(optional_payload)}
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}

        # 与同步版共用同一套超时/轮询刻度算法，避免两份逻辑漂移
        job_timeout = self._resolve_job_timeout(page_count if is_pdf else None)
        max_polls = self._poll_max_attempts(job_timeout)

        logger.info(
            "PaddleOCR API 异步调用: model=%s (api_name=%s), file_type=%s, data_size=%d, job_timeout=%.0fs, max_polls=%d",
            model,
            self.api_model_name,
            file_type,
            len(image_bytes),
            job_timeout,
            max_polls,
        )

        # 连续失败计数与状态日志去重，语义同同步版
        consecutive_failures = 0
        last_logged_state: str | None = None

        try:
            # 同一个 AsyncClient 贯穿提交 → 轮询 → 下载。
            # 注意生命周期：必须把整个轮询包在 with 里，不能像历史实现那样
            # 「提交一个 client、轮询另一个 client」——那个写法既浪费连接，
            # 又让提交用的 client 在轮询开始前就被关闭。
            async with httpx.AsyncClient(
                timeout=_build_http_timeout(_HTTP_SUBMIT_READ_TIMEOUT_SECONDS),
                transport=_build_async_http_transport(),
                follow_redirects=True,
            ) as client:
                # 提交 Job
                response = await client.post(self.api_url, headers=headers, data=data, files=files)
                resp_data = self._validate_submit_response(response)
                job_id = resp_data["data"]["jobId"]

                logger.info("PaddleOCR API Job 已提交: jobId=%s", job_id)

                # 异步轮询 — await asyncio.sleep 不阻塞事件循环
                for _ in range(max_polls):
                    await asyncio.sleep(_POLL_INTERVAL_SECONDS)

                    try:
                        poll_resp = await client.get(f"{self.api_url}/{job_id}", headers=headers)
                    except httpx.TransportError as exc:
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 异步轮询网络异常（连续第 %d/%d 次）: %s",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            exc,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: {exc}") from exc
                        continue

                    if poll_resp.status_code != 200:
                        if not _is_pollable_failure(poll_resp.status_code):
                            raise RuntimeError(f"PaddleOCR API 轮询失败: HTTP {poll_resp.status_code}")
                        consecutive_failures += 1
                        logger.warning(
                            "PaddleOCR API 异步轮询瞬时失败（连续第 %d/%d 次）: HTTP %d",
                            consecutive_failures,
                            _MAX_CONSECUTIVE_POLL_FAILURES,
                            poll_resp.status_code,
                        )
                        if consecutive_failures >= _MAX_CONSECUTIVE_POLL_FAILURES:
                            raise RuntimeError(
                                f"PaddleOCR API 轮询连续失败 {consecutive_failures} 次: HTTP {poll_resp.status_code}"
                            )
                        continue

                    consecutive_failures = 0

                    poll_data = poll_resp.json()
                    payload = poll_data.get("data", {})
                    state = payload.get("state", "") if isinstance(payload, dict) else ""

                    if state != last_logged_state:
                        logger.info("PaddleOCR API 异步 Job 状态变化: jobId=%s, state=%s", job_id, state)
                        last_logged_state = state

                    if state == "done":
                        result_url = payload.get("resultUrl", {})
                        jsonl_url = result_url.get("jsonUrl", "") if isinstance(result_url, dict) else ""
                        if not jsonl_url:
                            raise RuntimeError("PaddleOCR API 完成但无 jsonUrl")

                        # 下载结果（jsonUrl 可能是 bcebos 直链，不一定带 Authorization）
                        jsonl_resp = await client.get(
                            jsonl_url, timeout=_build_http_timeout(_HTTP_POLL_READ_TIMEOUT_SECONDS)
                        )
                        # S43-03：与同步版一致——下载失败先抛错，不能静默解析成空文本。
                        self._validate_result_download(jsonl_resp)
                        parsed = self._parse_job_result(jsonl_resp.text, model)
                        token_ok = True
                        if parsed.layout_results:
                            processed_pages = len(parsed.layout_results)
                        return parsed

                    progress = _read_extract_progress(poll_data)
                    if progress is not None:
                        _safe_report_progress(on_progress, *progress)

                    if state == "failed":
                        error_msg = payload.get("errorMsg", "未知错误")
                        raise RuntimeError(f"PaddleOCR API Job 失败: {error_msg}")

            raise RuntimeError(f"PaddleOCR API Job 超时（{job_timeout:.0f}s）")

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e
        finally:
            # 与同步版同理：不归还就永久占一个并发名额，多 Key 池会逐渐假死。
            pool.release(
                token_idx,
                success=token_ok,
                reason=failure_reason_of_active_exception(),
                pages=processed_pages if token_ok else 0,
            )

    async def aextract_text(self, image_bytes: bytes) -> PaddleOCRApiResult:
        """异步提取图片中的文字。"""
        return await self.arecognize_bytes(image_bytes, is_pdf=False)

    async def aextract_text_from_pdf(self, pdf_bytes: bytes) -> PaddleOCRApiResult:
        """异步提取 PDF 中的文字。"""
        return await self.arecognize_bytes(pdf_bytes, is_pdf=True)
