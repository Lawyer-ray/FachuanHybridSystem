"""信息中转站定时任务。"""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.message_hub")

TASK_FUNC = "apps.message_hub.tasks.sync_all_sources"
TASK_NAME = "message_hub:sync_all_sources"


def sync_source_by_id(source_id: int) -> None:
    """同步单个消息来源，供 django-q async_task 调用。"""
    import os
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    from apps.message_hub.models import MessageSource
    from apps.message_hub.services import get_fetcher

    source = MessageSource.objects.select_related("credential").get(pk=source_id)
    fetcher = get_fetcher(source.source_type)
    count = fetcher.fetch_new_messages(source)
    logger.info("同步完成: source=%s, 新消息=%d", source.display_name, count)


def sync_all_sources() -> None:
    """轮询所有启用的消息来源，拉取新消息。由 django-q2 定时调用。"""
    import os
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    from apps.message_hub.models import MessageSource
    from apps.message_hub.services import get_fetcher

    sources = MessageSource.objects.filter(is_enabled=True).select_related("credential")
    for source in sources:
        try:
            fetcher = get_fetcher(source.source_type)
            count = fetcher.fetch_new_messages(source)
            logger.info("同步完成: source=%s, 新消息=%d", source.display_name, count)
        except NotImplementedError:
            logger.info("来源 %s 尚未实现，跳过", source.display_name)
        except Exception:
            logger.exception("同步失败: source=%s", source.display_name)


def _register_schedule() -> None:
    """注册 django-q2 定时任务（每30分钟）。"""
    try:
        from django_q.models import Schedule

        if not Schedule.objects.filter(name=TASK_NAME).exists():
            from django_q.tasks import schedule
            schedule(
                TASK_FUNC,
                schedule_type=Schedule.MINUTES,
                minutes=30,
                name=TASK_NAME,
                repeats=-1,
            )
            logger.info("已注册定时任务: %s", TASK_NAME)
    except Exception:
        logger.debug("定时任务注册跳过（django-q 未就绪）")


_register_schedule()
