"""信息中转站定时任务。"""

from __future__ import annotations

import logging
import socket

from django.core.cache import cache

logger = logging.getLogger("apps.message_hub")

TASK_FUNC = "apps.message_hub.tasks.sync_all_sources"
TASK_NAME = "message_hub:sync_all_sources"

# 防重叠锁：TTL 略小于 30 分钟调度间隔（调度重叠/延迟时只允许一轮提交）
_SYNC_LOCK_KEY = "message_hub:sync_all_sources:lock"
_SYNC_LOCK_TTL_SECONDS = 25 * 60
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


def sync_source_by_id(source_id: int) -> None:  # pragma: no cover
    """同步单个消息来源，供 django-q async_task 调用。"""
    from apps.message_hub.models import MessageSource
    from apps.message_hub.services import get_fetcher

    source = MessageSource.objects.select_related("credential").filter(pk=source_id).first()
    if source is None:
        logger.info("消息来源 #%s 已不存在，跳过同步", source_id)
        return
    fetcher = get_fetcher(source.source_type)
    count = fetcher.fetch_new_messages(source)
    logger.info("同步完成: source=%s, 新消息=%d", source.display_name, count)


def sync_all_sources(*_args: object) -> None:  # pragma: no cover
    """为每个启用的消息来源提交独立的同步任务，避免串行阻塞。"""
    # 抢锁防重叠：上一轮调度未过期时跳过本轮，避免 Playwright 收件箱任务堆积
    if not cache.add(_SYNC_LOCK_KEY, "1", timeout=_SYNC_LOCK_TTL_SECONDS):
        logger.info("上一轮消息同步调度仍在锁周期内，跳过本轮: key=%s", _SYNC_LOCK_KEY)
        return

    from apps.message_hub.models import MessageSource, SourceType

    sources = list(MessageSource.objects.filter(is_enabled=True).values_list("id", "source_type"))
    if not sources:
        return

    from apps.core.tasking import submit_task

    court_types = {SourceType.COURT_INBOX, SourceType.COURT_SCHEDULE}
    for source_id, source_type in sources:
        # 一张网收件箱/庭审日程内部为分钟级 Playwright 流程，覆盖全局 600s 默认超时
        timeout = _COURT_FETCH_TIMEOUT_SECONDS if source_type in court_types else None
        submit_task(
            "apps.message_hub.tasks.sync_source_by_id",
            source_id,
            group="message_hub",
            timeout=timeout,
        )
    logger.info("已为 %d 个消息来源提交同步任务", len(sources))


def _register_schedule() -> None:
    """注册定时任务（每30分钟）。"""
    try:
        from apps.core.tasking import ScheduleQueryService

        schedule_svc = ScheduleQueryService()
        existing = schedule_svc.get_schedule_by_name(TASK_NAME)
        if existing is None:
            schedule_svc.create_interval_schedule(
                func=TASK_FUNC,
                name=TASK_NAME,
                minutes=30,
            )
            logger.info("已注册定时任务: %s", TASK_NAME)
        elif existing.func != TASK_FUNC:
            existing.func = TASK_FUNC
            existing.save(update_fields=["func"])
            logger.info("已更新定时任务 func 路径: %s → %s", existing.func, TASK_FUNC)
    except Exception:
        logger.debug("定时任务注册跳过（未就绪）")
