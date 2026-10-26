"""记忆抽取的异步任务（django-q 入口）。

## 为什么是独立模块而不是塞进 task_runner

``task_runner`` 是「跑一轮 agent 对话」的任务，它的生命周期绑在会话的
``task_state`` 上；记忆抽取是**会话结束之后**的旁路任务，与那次运行的成功
与否无关（失败的会话也可能产出了值得记的偏好）。混在一起会让
``task_state`` 的语义变模糊，也会让抽取失败污染任务状态。

## 触发链

```
pi 进程内 agent_settled
  └─ memory-inject.ts?  →  不，由 Django 侧在 stream_chat 收尾时入队
       （见 services/chat_service.py 的 _schedule_memory_extraction）
            └─ submit_task("apps.agent.services.memory_tasks.extract_session_memories", session_id)
                 └─ memory_service.extract_memories_from_session（LLM 抽取 → pending）
```

**为什么不在 pi 扩展里触发**：扩展拿不到 django-q；且本系统每请求起一个
pi 进程、用完即关，取消路径走 ``abort_running=True``，``session_shutdown``
不保证干净触发。由 Django 在流结束处入队是唯一可靠的时机。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 抽取任务超时（秒）。一次会话一万多字的输入 + 一次 LLM 调用，60s 足够。
EXTRACT_TIMEOUT = 120


def enqueue_extraction(session_id: str) -> str | None:
    """把一次会话的记忆抽取丢到后台。

    任何异常都不上抛——抽取是增强能力，绝不能因为入队失败让主对话报错。
    返回 django-q task id，失败返回 None。
    """
    try:
        from apps.core.tasking import submit_task

        task_id = submit_task(
            "apps.agent.services.memory_tasks.extract_session_memories",
            session_id,
            task_name=f"agent-memory-extract:{session_id}",
            timeout=EXTRACT_TIMEOUT,
        )
        logger.info("记忆抽取已入队 session=%s task=%s", session_id, task_id)
        return str(task_id)
    except Exception:
        logger.warning("记忆抽取入队失败（忽略） session=%s", session_id, exc_info=True)
        return None


def extract_session_memories(session_id: str) -> dict[str, Any]:
    """django-q worker 内调用（**同步**函数）：抽取并落为 pending 记忆。"""
    from . import memory_service

    try:
        return memory_service.extract_memories_from_session(session_id)
    # worker 必须收口所有异常，否则任务状态永远卡在 running
    except Exception as exc:
        logger.exception("记忆抽取任务失败 session=%s", session_id)
        return {"ok": False, "reason": f"error: {exc}"}


def derive_preferences_for_user(user_id: int) -> dict[str, Any]:
    """从审批/运行历史推断偏好，落为 pending 记忆（可定时跑）。

    零 LLM、零幻觉：读的是 ``AgentApproval`` 与 ``AgentRun`` 的既有审计数据。
    """
    from apps.organization.models import Lawyer

    from . import memory_service

    lawyer = Lawyer.objects.filter(pk=user_id).first()
    if lawyer is None:
        return {"ok": False, "reason": "lawyer_not_found"}
    try:
        suggestions = memory_service.derive_preferences_from_behavior(lawyer)
        created = memory_service.persist_suggestions(lawyer, suggestions)
        return {"ok": True, "created": created}
    except Exception as exc:
        logger.exception("行为偏好推断失败 user=%s", user_id)
        return {"ok": False, "reason": f"error: {exc}"}


def dispatch_behavior_derivation() -> dict[str, Any]:
    """定时任务派发器：为每位活跃律师推断行为偏好。

    为什么要有派发器而不要在 schedule 里直接循环算：一次全所推断是
    N 位律师 × 2 次聚合查询，放在**同一个** django-q 任务里会形成长事务型
    任务，一个律师出错整批失败。派发器只做「列出候选人 + 逐个入队」，
    每个律师一个独立任务，互不影响，也便于在管理端看到单人的失败原因。

    「活跃」的口径：近 90 天有 AgentRun 的律师。没有使用记录的人推断不出
    任何东西（阈值是 ≥50 次运行），扫全所纯属浪费。
    """
    from datetime import timedelta

    from django.utils import timezone

    from ..models import AgentRun

    cutoff = timezone.now() - timedelta(days=90)
    active_ids = list(
        AgentRun.objects.filter(created_at__gte=cutoff, user__isnull=False).values_list("user_id", flat=True).distinct()
    )
    if not active_ids:
        return {"ok": True, "dispatched": 0}

    from apps.core.tasking import submit_task

    dispatched = 0
    for user_id in active_ids:
        try:
            submit_task(
                "apps.agent.services.memory_tasks.derive_preferences_for_user",
                user_id,
                task_name=f"agent-memory-derive:{user_id}",
                timeout=EXTRACT_TIMEOUT,
            )
            dispatched += 1
        except Exception:
            logger.warning("行为偏好推断入队失败 user=%s（忽略）", user_id, exc_info=True)
    logger.info("行为偏好推断已派发 %s 位律师", dispatched)
    return {"ok": True, "dispatched": dispatched}


def _register_schedules() -> None:
    """注册记忆相关定时任务（AgentConfig.ready 调用）。

    用 ``schedule_exists`` 守卫：重复部署不会产生重复任务。与
    ``apps/core/tasking/cleanup_tasks._register_schedules`` 同一模式。
    """
    try:
        from apps.core.tasking import ScheduleQueryService

        svc = ScheduleQueryService()
        # 每日一次：行为推断读的是审批与运行统计，一天一变更已足够。
        name = "agent:derive_behavior_memories"
        if not svc.schedule_exists(name):
            svc.create_interval_schedule(
                func="apps.agent.services.memory_tasks.dispatch_behavior_derivation",
                name=name,
                minutes=24 * 60,
            )
            logger.info("已注册定时任务: %s", name)
    except Exception:
        logger.debug("记忆定时任务注册跳过（未就绪）")
