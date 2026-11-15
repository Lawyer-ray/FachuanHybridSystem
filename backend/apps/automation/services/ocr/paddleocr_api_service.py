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
from dataclasses import dataclass
from typing import Any

import httpx

from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

# 配置里存的模型键 → PaddleOCR 服务端要求的模型名。
#
# ⚠️ 这两者**必须**区分开，否则线上直接报「模型传参错误」(code=10007)：
# 服务端只认 `PaddleOCR-VL-1.6` 这种带大写的官方模型名，而配置里长期沿用
# `paddleocr_vl_1_6` 这类小写下划线键（历史命名，改动会动到已落库的配置值）。
# 所以映射只放在发送前这一处，配置侧保持原键不变。
_MODEL_API_NAME_MAP: dict[str, str] = {
    "pp_ocrv5": "PP-OCRv5",
    "pp_ocrv6": "PP-OCRv6",
    "pp_structure_v3": "PP-StructureV3",
    "paddleocr_vl": "PaddleOCR-VL",
    "paddleocr_vl_1_5": "PaddleOCR-VL-1.5",
    "paddleocr_vl_1_6": "PaddleOCR-VL-1.6",
}

# 历史库里混存过两种写法：小写下划线键（paddleocr_vl_1_6）与官方名
# （PaddleOCR-VL-1.6 / PP-OCRv6）。两者都要能识别，否则老数据会掉进
# 「不支持的 PaddleOCR 模型」分支或发错名字。归一化函数把两者统一到小写键。


def normalize_model_key(raw: str) -> str:
    """任意写法 → 小写配置键；未知值原样（小写）返回。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    if text in _MODEL_API_NAME_MAP:
        return text
    for key, api_name in _MODEL_API_NAME_MAP.items():
        if text == api_name or text.lower() == api_name.lower():
            return key
    return text.lower()


# 模型 → API 端点类型映射（键统一为小写配置键）
_OCR_ENDPOINT_MODELS = {"pp_ocrv5", "pp_ocrv6", "pp_structure_v3"}
_LAYOUT_ENDPOINT_MODELS = {"paddleocr_vl", "paddleocr_vl_1_5", "paddleocr_vl_1_6"}

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

# 请求超时（秒）
_REQUEST_TIMEOUT = 120.0


@dataclass(frozen=True)
class PaddleOCRApiResult:
    """PaddleOCR API 识别结果"""

    text: str  # 合并后的文本
    raw_texts: list[str]  # 原始文本列表
    model: str  # 使用的模型名称


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

    def __init__(self, model: str | None = None) -> None:
        """
        初始化 PaddleOCR API 引擎

        Args:
            model: 模型名称，None 时从 SystemConfig 读取
        """
        self._model = model
        self._config_service = SystemConfigService()

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
    def api_token(self) -> str:
        """获取 API Token"""
        return str(self._config_service.get_value("PADDLEOCR_API_TOKEN", "") or "")

    def _is_configured(self) -> bool:
        """检查是否已配置必要的 API 参数"""
        return bool(self.api_url and self.api_token)

    def recognize_bytes(self, image_bytes: bytes, is_pdf: bool = False) -> PaddleOCRApiResult:  # pragma: no cover
        """
        识别图片/PDF字节数据中的文字

        使用异步 Job 模式：提交任务 → 轮询状态 → 获取结果。

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件

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
                    "useDocOrientationClassify": False,
                    "useDocUnwarping": False,
                    "useTextlineOrientation": False,
                }
            )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": False,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            )

        headers = {
            "Authorization": f"bearer {self.api_token}",
        }

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

        logger.info(
            "PaddleOCR API 调用: model=%s (api_name=%s), file_type=%s, data_size=%d",
            model,
            self.api_model_name,
            file_type,
            len(image_bytes),
        )

        try:
            # 提交 Job
            with httpx.Client(timeout=30) as client:
                response = client.post(self.api_url, headers=headers, data=data, files=files)

            if response.status_code != 200:
                logger.warning(
                    "PaddleOCR API 提交失败: status=%d, body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError(f"PaddleOCR API 返回错误: HTTP {response.status_code}")

            resp_data = response.json()
            job_id = resp_data.get("data", {}).get("jobId")
            if not job_id:
                raise RuntimeError(f"PaddleOCR API 未返回 jobId: {resp_data}")

            logger.info("PaddleOCR API Job 已提交: jobId=%s", job_id)

            # 轮询 Job 状态
            max_polls = int(_REQUEST_TIMEOUT / 3)
            for _ in range(max_polls):
                time.sleep(3)
                with httpx.Client(timeout=30) as client:
                    poll_resp = client.get(f"{self.api_url}/{job_id}", headers=headers)

                if poll_resp.status_code != 200:
                    continue

                poll_data = poll_resp.json()
                state = poll_data.get("data", {}).get("state", "")

                if state == "done":
                    result_url = poll_data.get("data", {}).get("resultUrl", {})
                    jsonl_url = result_url.get("jsonUrl", "")
                    if not jsonl_url:
                        raise RuntimeError("PaddleOCR API 完成但无 jsonUrl")

                    # 下载结果。
                    # v2 Job API 的 jsonUrl 返回的是**单行完整 JSON**（`{logId, result:{...}}`），
                    # 不是每行一条的 JSONL。先按完整 JSON 解，失败再退回 JSONL 逐行解析
                    # （兼容旧版或将来改回流式的情况）。
                    with httpx.Client(timeout=30) as client:
                        result_resp = client.get(jsonl_url)
                    return self._parse_job_result(result_resp.text, model)

                elif state == "failed":
                    error_msg = poll_data.get("data", {}).get("errorMsg", "未知错误")
                    raise RuntimeError(f"PaddleOCR API Job 失败: {error_msg}")

            raise RuntimeError(f"PaddleOCR API Job 超时（{_REQUEST_TIMEOUT}s）")

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e

    def _parse_job_result(self, raw_text: str, model: str) -> PaddleOCRApiResult:
        """解析 Job API 的结果体。

        v2 Job API 实测返回单行完整 JSON：``{"logId": ..., "result": {"ocrResults": [...]}}``
        （版面类模型是 ``result.layoutParsingResults``）。旧版/流式则可能是 JSONL。
        两者都支持：先试完整 JSON，失败再按 JSONL 逐行。
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
        """
        all_texts: list[str] = []
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
                continue
            all_texts.extend(parsed.raw_texts)

        merged = "\n".join(all_texts)
        logger.info("PaddleOCR API (JSONL) 识别完成: model=%s, text_len=%d", model, len(merged))
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

    def _parse_response(self, data: dict[str, Any], model: str) -> PaddleOCRApiResult:
        """
        解析 API 响应

        PP-OCRv5 / PP-OCRv6 / PP-StructureV3: result.ocrResults[].prunedResult
        PaddleOCR-VL / VL-1.5 / VL-1.6: result.layoutParsingResults[].markdown.text
        """
        result = data.get("result", {})

        if model in _OCR_ENDPOINT_MODELS:
            return self._parse_ocr_response(result, model)
        elif model in _LAYOUT_ENDPOINT_MODELS:
            return self._parse_layout_response(result, model)
        else:
            raise RuntimeError(f"不支持的 PaddleOCR 模型: {model}")

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
        """解析版面分析端点响应（PaddleOCR-VL / VL-1.5）"""
        layout_results = result.get("layoutParsingResults", [])
        all_texts: list[str] = []

        for item in layout_results:
            markdown_data = item.get("markdown", {})
            all_texts.extend(self._collect_text_fragments(markdown_data))

        merged = "\n".join(all_texts)
        logger.info("PaddleOCR API (Layout) 识别完成: model=%s, text_len=%d", model, len(merged))
        return PaddleOCRApiResult(text=merged, raw_texts=all_texts, model=model)

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

    # ── 异步方法 ──────────────────────────────────────────────

    async def arecognize_bytes(
        self, image_bytes: bytes, is_pdf: bool = False
    ) -> PaddleOCRApiResult:  # pragma: no cover
        """
        异步识别图片/PDF字节数据中的文字

        使用异步 Job 模式：提交任务 → 异步轮询（asyncio.sleep） → 获取结果。
        相比同步版本，轮询等待期间不阻塞事件循环。

        Args:
            image_bytes: 图片或 PDF 字节数据
            is_pdf: 是否为 PDF 文件

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
                    "useDocOrientationClassify": False,
                    "useDocUnwarping": False,
                    "useTextlineOrientation": False,
                }
            )
        elif model in _LAYOUT_ENDPOINT_MODELS:
            optional_payload.update(
                {
                    "useDocOrientationClassify": False,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            )

        headers = {"Authorization": f"bearer {self.api_token}"}
        # 同步版同一限制：必须发官方模型名，否则 400「模型传参错误」(code=10007)
        data = {"model": self.api_model_name, "optionalPayload": json.dumps(optional_payload)}
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}

        logger.info(
            "PaddleOCR API 异步调用: model=%s (api_name=%s), file_type=%s, data_size=%d",
            model,
            self.api_model_name,
            file_type,
            len(image_bytes),
        )

        try:
            # 提交 Job
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.api_url, headers=headers, data=data, files=files)

            if response.status_code != 200:
                logger.warning("PaddleOCR API 提交失败: status=%d, body=%s", response.status_code, response.text[:500])
                raise RuntimeError(f"PaddleOCR API 返回错误: HTTP {response.status_code}")

            resp_data = response.json()
            job_id = resp_data.get("data", {}).get("jobId")
            if not job_id:
                raise RuntimeError(f"PaddleOCR API 未返回 jobId: {resp_data}")

            logger.info("PaddleOCR API Job 已提交: jobId=%s", job_id)

            # 异步轮询 — 关键改进：await asyncio.sleep 替代 time.sleep，不阻塞事件循环
            max_polls = int(_REQUEST_TIMEOUT / 3)
            async with httpx.AsyncClient(timeout=30) as poll_client:
                for _ in range(max_polls):
                    await asyncio.sleep(3)
                    poll_resp = await poll_client.get(f"{self.api_url}/{job_id}", headers=headers)

                    if poll_resp.status_code != 200:
                        continue

                    poll_data = poll_resp.json()
                    state = poll_data.get("data", {}).get("state", "")

                    if state == "done":
                        result_url = poll_data.get("data", {}).get("resultUrl", {})
                        jsonl_url = result_url.get("jsonUrl", "")
                        if not jsonl_url:
                            raise RuntimeError("PaddleOCR API 完成但无 jsonUrl")

                        jsonl_resp = await poll_client.get(jsonl_url)
                        return self._parse_job_result(jsonl_resp.text, model)

                    elif state == "failed":
                        error_msg = poll_data.get("data", {}).get("errorMsg", "未知错误")
                        raise RuntimeError(f"PaddleOCR API Job 失败: {error_msg}")

            raise RuntimeError(f"PaddleOCR API Job 超时（{_REQUEST_TIMEOUT}s）")

        except httpx.TimeoutException as e:
            logger.warning("PaddleOCR API 超时: %s", e)
            raise RuntimeError(f"PaddleOCR API 超时: {e}") from e
        except httpx.HTTPError as e:
            logger.warning("PaddleOCR API 网络错误: %s", e)
            raise RuntimeError(f"PaddleOCR API 网络错误: {e}") from e

    async def aextract_text(self, image_bytes: bytes) -> PaddleOCRApiResult:
        """异步提取图片中的文字。"""
        return await self.arecognize_bytes(image_bytes, is_pdf=False)

    async def aextract_text_from_pdf(self, pdf_bytes: bytes) -> PaddleOCRApiResult:
        """异步提取 PDF 中的文字。"""
        return await self.arecognize_bytes(pdf_bytes, is_pdf=True)
