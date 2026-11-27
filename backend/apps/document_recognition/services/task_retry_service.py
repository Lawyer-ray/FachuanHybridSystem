"""识别任务重跑服务（从 API 层下沉，2026-11-27）。

为什么必须是一层服务：``retry_task`` 原来在 API 层读模型、判状态机、
逐字段改模型再 ``task.save(update_fields=[...])``、最后提交 q 任务——四层架构
（``docs/harness/backend/four-layer.md``）里 API 只做参数提取与响应装配，
模型写入与业务状态机属于 Service。搬到本模块后 API 只剩「调一次 + 回读状态」。

重跑口径（逐条保持原样，未放宽也未收紧）：

- ``success``：拒绝（结果已落库，重跑会覆盖用户可能已确认的日期候选）；
- ``processing`` 且未僵死：拒绝（还在正常跑或者排着，重跑会产生双跑）；
- ``failed`` / 疑似僵死的 ``processing``：重置为 ``pending`` 再提交执行任务。
  重跑复用同一个 task 行与同一个已存文件，不堆垃圾任务、也不重传字节。

``STALLED_THRESHOLD_SECONDS`` / ``_elapsed_seconds`` / ``_is_stalled`` 一并搬到这里：
「能否重跑」依赖「processing 是否已僵死」这条业务判据，判据只能有一份；
API 侧仍按 ``document_recognition_api.<名字>`` import（响应字段装配与既有单测）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.utils import timezone

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.document_recognition")

# 任务疑似僵死的阈值（秒）。
#
# 正常识别 1-3 秒；即使 LLM 慢到 90 秒也能在 timeout=600 的 q 任务里跑完。
# 取 180 秒：足够覆盖“网关抖动 + 重试”，又能在真的卡住时比前端 10 分钟硬
# 超时早得多地告知用户。教训（2026-10-28）：本机 Clash 把内网网关当成外网
# 走代理，LLM 持续 502 重试，单次识别实测 439 秒，而界面全程只显示“识别中”。
STALLED_THRESHOLD_SECONDS = 180


def _as_datetime(value: Any) -> datetime | None:
    """把字段值收窄为 datetime；非 datetime（None / 测试替身）一律当缺失。

    为什么要这层：本模块的集成测试会 `patch` task service 返回 MagicMock，
    直接调 `.isoformat()` 会抛 AttributeError，接口从 200 变成 500
    （CI `backend-integration-smoke` 真实踩到）。诊断字段是**附加**信息，
    拿不到就该退化成 None，绝不能让主接口挂掉。
    """
    return value if isinstance(value, datetime) else None


def _elapsed_seconds(task: Any) -> int | None:
    """任务已耗时（秒）。时间字段不可用时返回 None（不抛异常）。"""
    start = _as_datetime(getattr(task, "started_at", None)) or _as_datetime(getattr(task, "created_at", None))
    if start is None:
        return None
    end = _as_datetime(getattr(task, "finished_at", None)) or timezone.now()
    # timezone-aware 与 naive 可能混存（旧数据），统一后再算差
    try:
        delta = end - start
    except TypeError:
        delta = end.replace(tzinfo=None) - start.replace(tzinfo=None)
    return max(0, int(delta.total_seconds()))


def _is_stalled(task: Any) -> bool:
    """processing 且已耗时超过阈值 → 疑似僵死。

    只对 processing 判：pending 是正常排队，success/failed 是终态。
    """
    if getattr(task, "status", None) != "processing":
        return False
    elapsed = _elapsed_seconds(task)
    return elapsed is not None and elapsed >= STALLED_THRESHOLD_SECONDS


class RetryTaskService:
    """识别任务重跑：状态机判定 + 重置字段 + 提交执行任务。"""

    def retry(self, task_id: int, user: Any | None = None) -> int:
        """重跑一次识别任务，返回任务 id（返回即表示 q 任务已提交）。

        归属过滤沿用任务服务口径（管理员见全量，普通用户仅见自己的与存量 NULL
        任务，非归属人与不存在同样 404）。

        Raises:
            NotFoundError: 任务不存在或对当前用户不可见（由任务服务抛出，404）
            ValidationException: ``TASK_ALREADY_SUCCESS`` / ``TASK_STILL_RUNNING``
        """
        from apps.core.tasking import submit_task
        from apps.document_recognition.models import DocumentRecognitionStatus
        from apps.document_recognition.services.task_service import DocumentRecognitionTaskService

        task = DocumentRecognitionTaskService().get_task(task_id, select_case=True, user=user)

        if task.status == DocumentRecognitionStatus.SUCCESS:
            raise ValidationException(
                message="该任务已识别成功，无需重跑",
                code="TASK_ALREADY_SUCCESS",
                errors={},
            )
        # failed 或 processing-但疑似僵死 → 可重跑；其余（pending / 正常 processing）拒绝
        if task.status == DocumentRecognitionStatus.PROCESSING and not _is_stalled(task):
            raise ValidationException(
                message="任务正在识别中，请等待完成",
                code="TASK_STILL_RUNNING",
                errors={},
            )

        # 重置为 pending：worker 拉起时会自己置回 processing
        # 2026-11-23 审计修复：error_message 是 NOT NULL CharField，写 None 会让这次
        # task.save() 抛 IntegrityError → 「重跑失败任务」接口直接 500。空值用空串
        # （与 services/date_capture_service.py:217 的正确写法同口径）。
        task.status = DocumentRecognitionStatus.PENDING
        task.error_message = ""
        task.started_at = None
        task.finished_at = None
        task.save(update_fields=["status", "error_message", "started_at", "finished_at"])

        submit_task(
            "apps.document_recognition.tasks.execute_document_recognition_task",
            task.id,
            task_name=f"document_recognition_{task.id}_retry",
            timeout=600,
        )
        # task.id 在 ORM 上仍是 Any（get_task 返回 Any），显式 int() 收窄，
        # 否则 mypy 报 no-any-return
        return int(task.id)
