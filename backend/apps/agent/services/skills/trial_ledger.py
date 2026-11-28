"""试跑的入账与日限流：**跑之前**落一行，跑完回填结果。

## 为什么另起一张 ``AgentSkillTrial`` 而不写 ``AgentRun``

``AgentRun.session`` 是非空外键，而试跑没有会话（见 ``trial.py`` 的「不写会话历史」
一节）。为了记账造一条假会话，代价是把假行推进律师的会话列表，并让
``AgentSession`` 的清理逻辑把假会话当真会话扫。试跑要记的只有几个规模量，一张窄表
既不欠账，也不污染运行时表。表结构的「为什么」写在 ``models/skill.py``。

## 为什么 ``reserve`` 必须在跑之前落行

日限流计的是「今天点了几次试跑」，不是「今天成功了几次」：一个超时或报错的试跑
照样起了一个子进程、烧了一次模型调用，不计数就等于给了一条免费重试通道。所以顺序
固定为 ``reserve``（查当日用量 → 落行）→ 跑 → ``finish``（回填成败）。失败也必须
``finish``，否则账上只剩「跑了但不知道结果」的行。

## 计数口径：本地自然日

``created_at__date=timezone.localdate()``，``reset_at`` 也按本地零点算。用 UTC 日期
会让北京时间早上 8 点之前算进前一天——审批人在自己以为是新的一天时被拦下，而
「什么时候恢复」还得跟一个不同的时区对齐，这种口径分叉没有任何报错。

## 并发：advisory lock 而不是 ``select_for_update``

用量为 0 时无行可锁，双击那个「试跑」按钮就能让两个请求都读到 ``used=limit-1``
然后各落一行。手法照 ``user_skills._lock_quota``：事务级咨询锁只管「查用量 + 插入」
这一段，非 PostgreSQL（本地 sqlite）跳过——日限是软上限，多算一两次不影响正确性。
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, time, timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from apps.agent.models import AgentSkill, AgentSkillTrial

from .constants import USER_PREFIX
from .errors import SkillQuotaExceeded

logger = logging.getLogger(__name__)

#: 每天每人的试跑次数上限（超限 429，文案里带恢复时刻）
DAILY_LIMIT_ENV = "FACHUAN_SKILL_TRIAL_DAILY_LIMIT"
DEFAULT_DAILY_LIMIT = 30

#: ``model`` 字段宽度（与 ``AgentSkillTrial.model`` 的 ``max_length`` 一致）
MODEL_MAX_CHARS = 100

_warned: set[str] = set()


def daily_limit() -> int:
    """每天每人的试跑次数上限：``FACHUAN_SKILL_TRIAL_DAILY_LIMIT``，缺省 30。

    非法值（非整数、0、负数）回落 30 并**只告警一次**：这个函数在每次试跑与每次
    查配额时都会被调，写错一个字会让日志被同一行刷满，反而盖住真正的错误。
    """
    raw = (os.environ.get(DAILY_LIMIT_ENV) or "").strip()
    if not raw:
        return DEFAULT_DAILY_LIMIT
    try:
        value = int(raw)
    except ValueError:
        _warn_once(f"{DAILY_LIMIT_ENV}={raw!r} 不是整数，按 {DEFAULT_DAILY_LIMIT} 处理")
        return DEFAULT_DAILY_LIMIT
    if value <= 0:
        _warn_once(f"{DAILY_LIMIT_ENV}={raw!r} 必须为正整数，按 {DEFAULT_DAILY_LIMIT} 处理")
        return DEFAULT_DAILY_LIMIT
    return value


def usage(user_id: int) -> dict[str, Any]:
    """当日的试跑用量（``GET /skills/trial-quota`` 的数据源）。

    ``remaining`` 下界取 0：限流被调小之后，已经跑超的当天不该显示成负数——前端
    拿它渲染进度条，负数会直接破图表。
    """
    limit = daily_limit()
    used = _used_today(user_id)
    return {"limit": limit, "used": used, "remaining": max(limit - used, 0), "reset_at": _reset_at()}


def reserve(*, user_id: int, skill: AgentSkill, backend: str, mode: str) -> AgentSkillTrial:
    """在跑之前落一行（并发点击也要计数），超限抛 ``SkillQuotaExceeded``。

    只用了 ``skill`` 的主键与 ``skill_key``：调用方可能从别的线程把它递进来，
    这里**不碰任何惰性关系**（碰了就是跨线程查库）。

    Raises:
        SkillQuotaExceeded: 今日次数已用完（API 层翻译成 429）。
    """
    with transaction.atomic():
        _lock_daily(user_id)
        limit = daily_limit()
        if _used_today(user_id) >= limit:
            raise SkillQuotaExceeded(_quota_message(limit))
        return AgentSkillTrial.objects.create(
            skill=skill,
            skill_key=f"{USER_PREFIX}{skill.pk}",
            user_id=user_id,
            backend=backend,
            mode=mode,
        )


def finish(
    row: AgentSkillTrial,
    *,
    ok: bool,
    duration_ms: int,
    response_chars: int,
    tool_calls_count: int,
    error: str,
    model: str | None,
) -> None:
    """回填本轮结果（成功失败都要调：失败那一轮同样产生了成本）。

    ``error`` 与 ``model`` 都按字段宽度截断：``error`` 只留原因，**不含**模型回复
    正文——试跑回答里可能出现律师没打算外传的业务表述。

    用 ``filter(pk=).update()`` 而不是 ``row.save()``：调用方手里那行是「开跑前的
    快照」，整行回写会把并发写入的其他字段一起盖回去。
    """
    AgentSkillTrial.objects.filter(pk=row.pk).update(
        ok=ok,
        duration_ms=max(int(duration_ms), 0),
        response_chars=max(int(response_chars), 0),
        tool_calls_count=max(int(tool_calls_count), 0),
        error=(error or "")[: AgentSkillTrial.ERROR_MAX_CHARS],
        model=(model or "")[:MODEL_MAX_CHARS],
    )


def _used_today(user_id: int) -> int:
    """今日已用次数（本地自然日，见模块 docstring 的「计数口径」）。"""
    return AgentSkillTrial.objects.filter(user_id=user_id, created_at__date=timezone.localdate()).count()


def _reset_at() -> str:
    """明日本地零点（ISO 8601）：限流文案与前端都按它说「什么时候恢复」。"""
    tz = timezone.get_current_timezone()
    tomorrow = timezone.localdate() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=tz).isoformat()


def _quota_message(limit: int) -> str:
    """超限文案：给出上限与恢复时刻，别让审批人只能干等到明天再试一次。"""
    return f"今日试跑次数已用完（{limit} 次/天），{_reset_at()} 后恢复"


def _lock_daily(user_id: int) -> None:
    """事务级咨询锁，把「查当日用量 + 插入」串行化（必须在 ``transaction.atomic()`` 内调）。

    非 PostgreSQL（本地 sqlite）直接跳过：日限是软上限，并发超出几次不影响正确性，
    而 sqlite 根本没有咨询锁。
    """
    if connection.vendor != "postgresql":
        return
    digest = hashlib.sha256(f"agent_skill:trial:{user_id}".encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _warn_once(message: str) -> None:
    """同一个非法配置只喊一次（见 ``daily_limit`` 的说明）。"""
    if message in _warned:
        return
    _warned.add(message)
    logger.warning("%s", message)
