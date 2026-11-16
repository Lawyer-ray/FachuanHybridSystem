"""云端回调的平台分发：验签 → 定位任务 → 建结果 → 写回。

API 层只负责取原始字节/请求头并装配响应，业务判定全在这里（四层架构：
API 不做 ORM、不写业务分支）。平台差异以 dict dispatch 表达，新增平台只需
在 ``handle`` 的映射表里加一项。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.services.callback_config import textin_callback_secret
from apps.document_parsing.services.callback_result_service import (
    DocumentParsingCallbackResultService,
    mineru_callback_fields,
    textin_callback_fields,
)
from apps.document_parsing.services.webhook_signature import (
    TEXTIN_SIGNATURE_HEADER,
    verify_mineru_checksum,
    verify_textin_signature,
)

logger = logging.getLogger("apps.document_parsing")

#: 回调处理结论。对外只区分两类：可以回 200 的，和必须回非 200 的。
#: 云端以「非 200 就重推」作为送达判定，所以只有真正确认处理过才回 200——
#: 验签失败/定位不到任务一律非 200，避免伪造推送被当成成功而不再重试真推送。
ACCEPTED = "accepted"
DUPLICATE = "duplicate"
REJECTED_SIGNATURE = "signature"
REJECTED_UNRECOGNIZED = "unrecognized"
REJECTED_TASK_NOT_FOUND = "task_not_found"
REJECTED_PROVIDER_DISABLED = "provider_disabled"


class DocumentParsingCallbackDispatchService:
    """按平台校验并写回云端回调。"""

    def __init__(self) -> None:
        self._results = DocumentParsingCallbackResultService()

    def handle(self, provider: str, body: bytes, headers: dict[str, str]) -> str:
        """处理一次回调，返回处理结论（API 层据此映射状态码）。"""
        handler = {"mineru": self._handle_mineru, "textin": self._handle_textin}.get(provider)
        if handler is None:
            return REJECTED_UNRECOGNIZED
        return handler(body, headers)

    # ── MinerU ────────────────────────────────────────────────

    def _handle_mineru(self, body: bytes, headers: dict[str, str]) -> str:
        """MinerU 回调：checksum = sha256(uid + seed + content)。

        ``uid`` 随我们发给 MinerU 的 callback URL 带出去，回调时原样出现在
        ``X-Callback-Url`` 请求头里；``seed`` 是我方为每条记录生成的随机串。
        两者都已登记在任务记录上，验签之外再对一次库，旧 seed 的重放也过不去。
        """
        payload = _decode_json(body)
        if payload is None:
            return REJECTED_UNRECOGNIZED

        uid = _query_param(headers.get("x-callback-url", ""), "uid")
        seed = _str_field(payload, "seed")
        checksum = _str_field(payload, "checksum")
        content = payload.get("content")
        content_text = content if isinstance(content, str) else ""

        if not verify_mineru_checksum(uid=uid, seed=seed, content=content_text, checksum=checksum):
            logger.warning("MinerU 回调验签失败: uid=%s", uid)
            return REJECTED_SIGNATURE

        task = self._results.resolve_mineru_task(uid, seed)
        if task is None:
            logger.warning("MinerU 回调找不到对应任务: uid=%s", uid)
            return REJECTED_TASK_NOT_FOUND

        content_payload = _decode_json(content_text.encode())
        if content_payload is None:
            return REJECTED_UNRECOGNIZED
        state, zip_url, err_msg, _data_id = mineru_callback_fields(content_payload)
        verdict = self._results.normalize_status(state)
        if verdict == "ignore":
            logger.warning("MinerU 回调状态不可识别: task_id=%s state=%r", task.id, state)
            return REJECTED_UNRECOGNIZED
        if verdict == "failure":
            return self._write(task, {"success": False, "error": err_msg or f"MinerU 解析失败(state={state})"})
        if not zip_url:
            return self._write(task, {"success": False, "error": "MinerU 回调缺少 full_zip_url，无法取结果"})
        return self._write(task, self._build_mineru_result(task, zip_url))

    def _build_mineru_result(self, task: DocumentParsingTask, zip_url: str) -> dict[str, Any]:
        """下载并解析 MinerU 结果 ZIP，产出与 hook 同形的结果字典。

        直接复用后端既有实现（``_parse_result_zip`` 内含解压炸弹防护与
        content_list / layout / model.json 合并），不另写一套解析。
        """
        from apps.document_parsing.services.backends.mineru_backend import MineruBackend
        from apps.document_parsing.tasks import _coverage_dict, _serialize_block

        try:
            backend = MineruBackend()
            parsed = backend._parse_result_zip(zip_url, return_markdown=True, extract_images=False)
        except Exception as exc:
            logger.exception("MinerU 回调结果下载/解析失败: task_id=%s", task.id)
            return {"success": False, "error": f"MinerU 结果下载或解析失败: {exc}"}

        return {
            "success": True,
            "text": parsed.text,
            "markdown": parsed.markdown or "",
            "metadata": parsed.metadata or {},
            "parse_method": parsed.parse_method or "mineru",
            "blocks": [_serialize_block(block) for block in (getattr(parsed, "blocks", None) or [])],
            "coverage": _coverage_dict(getattr(parsed, "coverage", None)),
        }

    # ── Textin ────────────────────────────────────────────────

    def _handle_textin(self, body: bytes, headers: dict[str, str]) -> str:
        """Textin 回调处理。

        ⚠️ 未核实的适配：Textin 官方 webhook 的签名字段名与算法未公开，SDK 也不含
        回调模型。当前按「共享密钥 + ``X-Webhook-Signature:
        sha256(secret + raw_body)``」约定双向校验——这是本服务自定的约定，不是
        从官方文档反推的。首次真实对接时必须核对真实载荷并替换两处：
          · ``textin_callback_fields``（状态/任务/错误字段候选名）
          · ``verify_textin_signature``（签名算法与头名）
        在此之前该平台默认不启用回调（``TEXTIN_CALLBACK_SECRET`` 不配即走轮询），
        所以这段未核实的适配不会影响线上解析。
        """
        signature = headers.get(TEXTIN_SIGNATURE_HEADER.lower(), "")
        if not verify_textin_signature(secret=textin_callback_secret(), raw_body=body, signature=signature):
            logger.warning("Textin 回调验签失败")
            return REJECTED_SIGNATURE

        payload = _decode_json(body)
        if payload is None:
            return REJECTED_UNRECOGNIZED
        status, job_id, error = textin_callback_fields(payload)
        task = self._results.resolve_textin_task(job_id)
        if task is None:
            logger.warning("Textin 回调找不到对应任务: job_id=%s", job_id)
            return REJECTED_TASK_NOT_FOUND

        verdict = self._results.normalize_status(status)
        if verdict == "ignore":
            logger.warning("Textin 回调状态不可识别: task_id=%s status=%r", task.id, status)
            return REJECTED_UNRECOGNIZED
        if verdict == "failure":
            return self._write(task, {"success": False, "error": error or f"Textin 解析失败(status={status})"})
        return self._write(task, self._build_textin_result(task, payload))

    def _build_textin_result(self, task: DocumentParsingTask, payload: dict[str, Any]) -> dict[str, Any]:
        """下载并解析 Textin 结果 JSON，产出与 hook 同形的结果字典。

        result_url 优先取回调载荷；缺失时按登记的 job_id 回查一次终态。
        两种来源都拿不到才判失败（不猜 URL）。
        """
        from apps.document_parsing.services.backends.textin_backend import TextinBackend
        from apps.document_parsing.tasks import _coverage_dict, _serialize_block

        job_id = _job_id_of(task)
        try:
            backend = TextinBackend()
        except Exception as exc:
            logger.exception("Textin 回调无法构建后端（凭证缺失？）: task_id=%s", task.id)
            return {"success": False, "error": f"Textin 回调处理失败（后端不可用）: {exc}"}

        result_url = _first_url(payload)
        if not result_url and job_id:
            result_url = _refetch_result_url(backend, task, job_id)
        if not result_url:
            return {"success": False, "error": "Textin 回调缺少 result_url，且回查未拿到结果地址"}

        try:
            parsed = backend.parse_result_from_url(
                result_url, return_markdown=True, extract_images=False, job_id=job_id
            )
        except Exception as exc:
            logger.exception("Textin 回调结果下载/解析失败: task_id=%s", task.id)
            return {"success": False, "error": f"Textin 结果下载或解析失败: {exc}"}

        return {
            "success": True,
            "text": parsed.text,
            "markdown": parsed.markdown or "",
            "metadata": parsed.metadata or {},
            "parse_method": parsed.parse_method or "textin",
            "blocks": [_serialize_block(block) for block in (getattr(parsed, "blocks", None) or [])],
            "coverage": _coverage_dict(getattr(parsed, "coverage", None)),
        }

    # ── 公共 ──────────────────────────────────────────────────

    def _write(self, task: DocumentParsingTask, result: dict[str, Any]) -> str:
        applied = self._results.apply_result(task, result)
        return ACCEPTED if applied else DUPLICATE


def _decode_json(raw: bytes) -> dict[str, Any] | None:
    """把字节解成 dict；不是合法 JSON 对象时返回 None。"""
    try:
        payload = json.loads(raw or b"null")
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _str_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _query_param(url: str, key: str) -> str:
    """取 URL 上的查询参数（MinerU 把我们 callback URL 里的 uid 原样带回）。"""
    if not url:
        return ""
    try:
        values = parse_qs(urlparse(url).query).get(key) or []
    except ValueError:
        return ""
    return values[0].strip() if values else ""


def _first_url(payload: dict[str, Any]) -> str:
    """在 Textin 载荷里找结果地址（顶层或 data 内，字段名多候选）。"""
    data = payload.get("data")
    for container in (payload, data):
        if not isinstance(container, dict):
            continue
        for key in ("result_url", "resultUrl"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _job_id_of(task: DocumentParsingTask) -> str:
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    return str(metadata.get("callback_job_id") or "")


def _refetch_result_url(backend: Any, task: DocumentParsingTask, job_id: str) -> str:
    """回调没带 result_url 时，按登记的 job_id 现查一次终态。"""
    try:
        status = backend.fetch_job(job_id)
    except Exception:
        logger.exception("Textin 回查任务状态失败: task_id=%s job_id=%s", task.id, job_id)
        return ""
    return str(getattr(status, "result_url", "") or "")
