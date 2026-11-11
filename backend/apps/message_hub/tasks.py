"""信息中转站定时任务。"""

from __future__ import annotations

import logging
import socket
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("apps.message_hub")

TASK_FUNC = "apps.message_hub.tasks.sync_all_sources"
TASK_NAME = "message_hub:sync_all_sources"

# 调度心跳间隔（分钟）。调度器只负责「每分钟看一眼哪些来源到点了」，
# 真正的拉取频率由每个来源自己的 poll_interval_minutes 决定。
# 心跳取 1 分钟是为了让各来源的周期误差不超过 1 分钟；
# 没有来源到点时这一轮只做一次 DB 查询，开销可忽略。
_SCHEDULE_HEARTBEAT_MINUTES = 1

# 防重叠锁：TTL 略小于心跳间隔（调度重叠/延迟时只允许一轮提交）
_SYNC_LOCK_KEY = "message_hub:sync_all_sources:lock"
_SYNC_LOCK_TTL_SECONDS = 60
# 一张网 Playwright 类 fetcher 的单源同步超时（覆盖全局 600s 默认值）
_COURT_FETCH_TIMEOUT_SECONDS = 1800


def _is_expected_sync_error(exc: Exception) -> bool:
    """判断是否为可预期的网络/环境/运行时异常，避免刷整段堆栈。"""
    if isinstance(exc, (socket.gaierror, TimeoutError, ConnectionError)):
        return True

    msg = str(exc).lower()
    expected_tokens = (
        "err_internet_disconnected",
        "name or service not known",
        "nodename nor servname provided",
        "connection refused",
        "temporarily unavailable",
        "timeout",
        "greenlet.error",  # Playwright 跨线程 greenlet 切换失败
        "cannot switch to a different thread",  # 同上
        "sync api inside the asyncio loop",  # Playwright Sync API 在 asyncio 中误用
        "target closed",  # 浏览器/页面已关闭
        "browser has been closed",  # 浏览器实例已关闭
        "disconnected",  # Playwright 连接断开
    )
    return any(token in msg for token in expected_tokens)


def sync_source_by_id(source_id: int, window_days: int | None = None) -> None:
    """同步单个消息来源，供 django-q async_task 调用。

    Args:
        source_id: 消息来源 id。
        window_days: 只看最近 N 天。前端手动同步传 ``DEFAULT_SYNC_WINDOW_DAYS``；
            后台定时同步传 ``None``（按来源 ``sync_since`` 全量回填，仅首次生效）。

    不加 ``pragma: no cover``：重生成本体只有 ORM 查询 + fetcher 调用，
    fetcher 可 patch，**完全能真跑**。曾经盖着 pragma，于是本函数唯一
    的守门测试停在旧签名上长期变红也没人发现——分支不可见的代价
    比“少写几条测试”大得多。
    """
    from apps.message_hub.models import MessageSource
    from apps.message_hub.services import get_fetcher

    source = MessageSource.objects.select_related("credential").filter(pk=source_id).first()
    if source is None:
        logger.info("消息来源 #%s 已不存在，跳过同步", source_id)
        return
    fetcher = get_fetcher(source.source_type)
    count = fetcher.fetch_new_messages(source, window_days=window_days)
    logger.info("同步完成: source=%s, 新消息=%d, window_days=%s", source.display_name, count, window_days)


def _is_source_due(*, poll_interval_minutes: int, last_sync_at: datetime | None, now: datetime) -> bool:
    """判断某个来源本轮是否该同步。

    - ``poll_interval_minutes <= 0``：不按周期自动轮询（手动上传 / 客户链接这类
      无「新邮件」概念的来源沿用此约定），一律跳过。
    - 从未同步过（``last_sync_at`` 为空）：立即同步，避免新建来源要等一整个周期。
    - 其余情况：距上次同步已满 poll_interval_minutes 才同步。
    """
    if poll_interval_minutes <= 0:
        return False
    if last_sync_at is None:
        return True
    return now - last_sync_at >= timedelta(minutes=poll_interval_minutes)


def sync_all_sources(*_args: object) -> None:
    """按各来源自己的轮询周期，为本轮到点的来源提交独立同步任务。

    不加 ``pragma: no cover``：只依赖 ORM 查询、缓存锁与 ``submit_task``，
    三者都可替身，测试能真跑整条派发逻辑（含抢锁与超时选择）。
    """
    # 抢锁防重叠：上一轮调度未过期时跳过本轮，避免 Playwright 收件箱任务堆积
    if not cache.add(_SYNC_LOCK_KEY, "1", timeout=_SYNC_LOCK_TTL_SECONDS):
        logger.info("上一轮消息同步调度仍在锁周期内，跳过本轮: key=%s", _SYNC_LOCK_KEY)
        return

    from apps.message_hub.models import MessageSource, SourceType

    rows = list(
        MessageSource.objects.filter(is_enabled=True).values_list(
            "id", "source_type", "poll_interval_minutes", "last_sync_at"
        )
    )
    if not rows:
        return

    now = timezone.now()
    due = [
        (source_id, source_type)
        for source_id, source_type, poll_interval, last_sync_at in rows
        if _is_source_due(poll_interval_minutes=poll_interval, last_sync_at=last_sync_at, now=now)
    ]
    if not due:
        logger.debug("本轮无来源到点: 共 %d 个启用来源", len(rows))
        return

    from apps.core.tasking import submit_task

    court_types = {SourceType.COURT_INBOX, SourceType.COURT_SCHEDULE}
    for source_id, source_type in due:
        # 一张网收件箱/庭审日程内部为分钟级 Playwright 流程，覆盖全局 600s 默认超时
        timeout = _COURT_FETCH_TIMEOUT_SECONDS if source_type in court_types else None
        submit_task(
            "apps.message_hub.tasks.sync_source_by_id",
            source_id,
            group="message_hub",
            timeout=timeout,
        )
    logger.info("已为 %d/%d 个到点来源提交同步任务", len(due), len(rows))


def _register_schedule() -> None:  # pragma: no cover
    """注册/校正调度心跳任务（每分钟）。

    历史实现只在记录不存在时创建，导致把间隔从 30 分钟调小后旧记录不跟随更新
    （改了源码却不生效）。这里显式比对 func 与 minutes，任一不符即就地校正。
    """
    try:
        from apps.core.tasking import ScheduleQueryService

        schedule_svc = ScheduleQueryService()
        existing = schedule_svc.get_schedule_by_name(TASK_NAME)
        if existing is None:
            schedule_svc.create_interval_schedule(
                func=TASK_FUNC,
                name=TASK_NAME,
                minutes=_SCHEDULE_HEARTBEAT_MINUTES,
            )
            logger.info("已注册定时任务: %s（%d 分钟）", TASK_NAME, _SCHEDULE_HEARTBEAT_MINUTES)
            return

        updates: list[str] = []
        if existing.func != TASK_FUNC:
            existing.func = TASK_FUNC
            updates.append("func")
        if getattr(existing, "minutes", None) != _SCHEDULE_HEARTBEAT_MINUTES:
            existing.minutes = _SCHEDULE_HEARTBEAT_MINUTES
            updates.append("minutes")
        if updates:
            existing.save(update_fields=updates)
            logger.info("已校正定时任务: %s（更新 %s）", TASK_NAME, ", ".join(updates))
    except Exception:
        logger.debug("定时任务注册跳过（未就绪）")
