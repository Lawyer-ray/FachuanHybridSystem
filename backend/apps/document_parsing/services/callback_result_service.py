"""云端回调结果写回：把 webhook 推送的载荷落成 ``DocumentParsingTask`` 的终态。

写回口径**与 ``tasks.document_parsing_hook`` 完全一致**（同一组
``mark_completed`` / ``mark_failed`` 参数映射），因为两者都在回答同一个问题：
「这次解析最后是什么结果」。差别只在触发源——hook 拿的是 Django-Q 的 Task
对象，这里拿的是云端回调的 HTTP 请求体。

幂等：任务已处于终态就直接跳过。云端回调失败会重推（MinerU 最多 5 次），
重复推送不能把同一份结果反复写库，更不能把已完成的记录改回失败。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import F, Func, JSONField, Value

from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.services.callback_seed import record_id_from_uid

logger = logging.getLogger("apps.document_parsing")


class DocumentParsingCallbackResultService:
    """按平台把回调内容归一成结果字典，再写回任务记录。"""

    #: 云端报告「已完成」的状态值（各平台命名不同，统一在这里收口）
    _SUCCESS_STATUSES = frozenset({"completed", "partial_completed", "success", "done"})
    #: 云端报告「已失败」的状态值
    _FAILURE_STATUSES = frozenset({"failed", "error", "stopped", "deleted"})

    def resolve_mineru_task(self, uid: str, seed: str) -> DocumentParsingTask | None:
        """用回调里的 ``uid`` + ``seed`` 找回任务记录。

        uid 由本服务派出（``callback_uid``），seed 是我们存在记录上的随机串，
        两者必须同时对上同一行才返回——只对 uid 不对 seed，等于让任何知道记录
        id 的人都能伪造推送。
        """

        record_id = record_id_from_uid(uid)
        if record_id is None:
            return None
        return DocumentParsingTask.objects.filter(pk=record_id, callback_seed=seed).first()

    def resolve_textin_task(self, job_id: str) -> DocumentParsingTask | None:
        """用 Textin 回调里的 ``job_id`` 找回任务记录。

        job_id 在建任务时由本服务写进 ``metadata['callback_job_id']``（见
        ``task_dispatch_service`` 的绑定步骤），唯一且不可猜。
        """

        if not job_id:
            return None
        return DocumentParsingTask.objects.filter(metadata__callback_job_id=job_id).first()

    def bind_mineru_callback(self, record_id: int, seed: str) -> int:
        """把 MinerU 回调的 seed 记到任务上（回调时用 uid+seed 找回该任务）。

        uid 不需要存：它由 ``record_id`` 与随机后缀组成，验签通过的 uid 直接
        解析出记录 id（见 ``callback_seed.record_id_from_uid``）。
        """

        return DocumentParsingTask.objects.filter(pk=record_id).update(callback_seed=seed)

    def bind_textin_job(self, record_id: int, job_id: str) -> int:
        """把 Textin 的 job_id 记到任务元数据上（回调时据此找回该任务）。

        只合并单个键，不整行覆盖 ``metadata``——解析任务的 metadata 后续还要被
        结果写回占用。
        """

        return DocumentParsingTask.objects.filter(pk=record_id).update(
            metadata=Func(
                F("metadata"),
                Value({"callback_job_id": job_id}),
                function="jsonb_concat",
                output_field=JSONField(),
            )
        )

    def apply_result(self, task: DocumentParsingTask, result: dict[str, Any]) -> bool:
        """把归一后的结果写回任务记录。

        Returns:
            True=本次写入生效；False=记录已是终态，本次为重复推送，已跳过。
        """

        if task.status in (DocumentParsingTask.Status.COMPLETED, DocumentParsingTask.Status.FAILED):
            logger.info("回调重复推送，已忽略: task_id=%s status=%s", task.id, task.status)
            return False

        if result.get("success"):
            task.mark_completed(
                text=result.get("text", ""),
                markdown=result.get("markdown", ""),
                metadata=result.get("metadata", {}),
                backend_used=result.get("parse_method") or result.get("method") or "unknown",
                blocks=result.get("blocks") or [],
            )
            logger.info("回调写回完成: task_id=%s backend=%s", task.id, task.backend_used)
            return True

        task.mark_failed(result.get("error") or "未知错误")
        logger.info("回调写回失败状态: task_id=%s error=%s", task.id, task.error_message)
        return True

    def normalize_status(self, raw_status: str) -> str:
        """把云端状态字符串归为 ``success`` / ``failure`` / ``ignore``。"""

        status = (raw_status or "").strip().lower()
        if status in self._SUCCESS_STATUSES:
            return "success"
        if status in self._FAILURE_STATUSES:
            return "failure"
        return "ignore"


#: Textin 回调载荷的字段候选名。官方未公开字段名，SDK 也不含回调模型，
#: 所以同语义字段在此多写几个候选：命中哪个用哪个，全不命中就按「载荷不可
#: 识别」拒掉（不靠位置猜）。首次真实对接后应据此收敛为单一字段名。
_TEXTIN_STATUS_KEYS: tuple[str, ...] = ("status", "state", "job_status")
_TEXTIN_JOB_ID_KEYS: tuple[str, ...] = ("job_id", "jobId", "task_id", "taskId")
_TEXTIN_ERROR_KEYS: tuple[str, ...] = ("error_message", "errorMessage", "message", "err_msg")


def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    """按候选名取第一个非空字符串值。"""

    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def textin_callback_fields(payload: dict[str, Any]) -> tuple[str, str, str]:
    """从 Textin 回调载荷中取出 ``(status, job_id, error_message)``。

    兼容 ``{...}`` 与 ``{"data": {...}}`` 两种包裹方式：若顶层拿不到 job_id
    就下沉一层再试（回调平台习惯把业务字段包在 data 里）。
    """

    status = _first(payload, _TEXTIN_STATUS_KEYS)
    job_id = _first(payload, _TEXTIN_JOB_ID_KEYS)
    error = _first(payload, _TEXTIN_ERROR_KEYS)
    if job_id:
        return status, job_id, error

    inner = payload.get("data")
    if not isinstance(inner, dict):
        return status, "", error
    return (
        status or _first(inner, _TEXTIN_STATUS_KEYS),
        _first(inner, _TEXTIN_JOB_ID_KEYS),
        error or _first(inner, _TEXTIN_ERROR_KEYS),
    )


def mineru_callback_fields(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    """从 MinerU 回调 ``content`` 中取出 ``(state, full_zip_url, err_msg, data_id)``。

    回调 content 的真实结构官方文档未逐字给出（文档只描述了 checksum 与
    content 为 JSON 字符串）。这里按 MinerU 查询接口的形状读取
    ``data.extract_result[]``，单个结果取第一条（本服务一批只提交一个文件，
    见 ``_request_upload_url`` 的 files 只放一个元素）。

    ⚠️ 这是本模块唯一靠推断的解析，首次真实回调到达时应核对并收敛；
    形状不符时上层会把它当「载荷不可识别」拒掉，不会误写结果。
    """

    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    results = data.get("extract_result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return "", "", "", ""
    first = results[0]
    return (
        str(first.get("state") or "").strip(),
        str(first.get("full_zip_url") or "").strip(),
        str(first.get("err_msg") or "").strip(),
        str(first.get("data_id") or "").strip(),
    )
