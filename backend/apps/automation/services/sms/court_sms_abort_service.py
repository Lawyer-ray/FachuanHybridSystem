"""法院短信任务终止清理服务"""

from __future__ import annotations

import logging
from typing import Any

from apps.automation.models import CourtSMS, ScraperTask
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.automation")

_RUN_TASK_FUNC = "apps.core.tasking.entries.run_task"

# 以 sms_id 为入参的短信 worker（submit_task 包装后 target 存于 args[0]、sms_id 存于 args[1]）
_SMS_WORKER_FUNCS = frozenset(
    {
        "apps.automation.workers.court_sms_tasks.process_sms",
        "apps.automation.workers.court_sms_tasks.process_sms_from_matching",
        "apps.automation.workers.court_sms_tasks.process_sms_from_renaming",
        "apps.automation.workers.court_sms_tasks.retry_download_task",
    }
)
# 以 scraper_task_id 为入参的 worker（execute_scraper_task / 状态变更后续处理）
_TASK_ID_WORKER_FUNCS = frozenset(
    {
        "apps.automation.tasks.execute_scraper_task",
        "apps.automation.workers.court_sms_tasks.handle_scraper_task_status_change",
    }
)


class CourtSmsAbortService:
    """彻底终止一条法院短信处理任务。

    供前端弹窗「停止并删除」调用：先清掉 Django-Q 里属于该短信的重试调度
    （Schedule）与排队/退避重试任务（broker 队列条目），再删除短信记录与
    归属的下载任务（ScraperTask 级联删除 CourtDocument，post_delete 信号
    会清理下载原件；已归档到案件日志的复制件不受影响）。

    正在执行中的 worker 无法强杀，但相关入口对记录不存在都会安全返回
    （process_sms 抛 NotFoundError、execute_scraper_task 记日志后跳过），
    记录删除后残留运行也不会再写回状态。
    """

    def abort_and_delete(self, sms_id: int) -> dict[str, Any]:
        sms = CourtSMS.objects.filter(id=sms_id).first()
        if sms is None:
            raise NotFoundError(f"短信记录不存在: ID={sms_id}")
        scraper_task = sms.scraper_task

        removed_schedules = self._remove_retry_schedules(sms_id, scraper_task)
        removed_queued, queue_error = self._remove_queued_tasks(sms_id, scraper_task)

        sms.delete()

        scraper_task_deleted = False
        if scraper_task is not None:
            # 只删除由本短信创建的下载任务（config 带回溯标识），
            # 理论上挂在 SMS 下的都来自 _create_download_task，防御外部共享任务
            if (scraper_task.config or {}).get("court_sms_id") == sms_id:
                scraper_task.delete()
                scraper_task_deleted = True
            else:
                logger.warning("ScraperTask %s 非短信 %s 创建，仅随短信删除解除关联", scraper_task.id, sms_id)

        logger.info(
            "终止并删除短信任务: SMS ID=%s, 清理调度=%s, 清理队列=%s, 删除下载任务=%s, 队列清理异常=%s",
            sms_id,
            removed_schedules,
            removed_queued,
            scraper_task_deleted,
            queue_error,
        )
        return {
            "id": sms_id,
            "removed_schedules": removed_schedules,
            "removed_queued_tasks": removed_queued,
            "queue_error": queue_error,
            "scraper_task_deleted": scraper_task_deleted,
        }

    def _remove_retry_schedules(self, sms_id: int, scraper_task: ScraperTask | None) -> int:
        """删除短信级下载重试调度（court_sms_retry_download_{id}）与爬虫任务级
        指数退避调度（retry_task_{task_id}_{n}）。"""
        from django_q.models import Schedule

        qs = Schedule.objects.filter(
            func__in=_SMS_WORKER_FUNCS,
            args=str(sms_id),
        )
        qs = qs | Schedule.objects.filter(name=f"court_sms_retry_download_{sms_id}")
        if scraper_task is not None:
            task_key = str(scraper_task.id)
            qs = qs | Schedule.objects.filter(func__in=_TASK_ID_WORKER_FUNCS, args=task_key)
            qs = qs | Schedule.objects.filter(name__startswith=f"retry_task_{task_key}_")
        deleted, _ = qs.delete()
        return int(deleted)

    def _remove_queued_tasks(self, sms_id: int, scraper_task: ScraperTask | None) -> tuple[int, str | None]:
        """从 broker 队列移除该短信的排队/重试任务，返回 (移除数量, 异常信息)。

        Redis 与 ORM 两种 broker 都处理；队列清理是尽力而为，失败不阻断
        记录删除（返回异常信息供前端提示）。
        """
        sms_key = str(sms_id)
        task_keys = {str(scraper_task.id)} if scraper_task is not None else set()
        removed = 0
        error: str | None = None
        try:
            from django_q.brokers import get_broker

            broker = get_broker()
            if type(broker).__name__ == "Redis":
                removed = self._remove_redis_entries(broker, sms_key, task_keys)
            else:
                removed = self._remove_orm_entries(sms_key, task_keys)
        except Exception as exc:  # pragma: no cover - Redis 不可达等运行环境问题
            logger.warning("清理短信 %s 的队列任务失败（忽略，不阻断删除）: %s", sms_id, exc)
            error = str(exc)
        return removed, error

    def _remove_redis_entries(self, broker: Any, sms_key: str, task_keys: set[str]) -> int:
        # broker.connection 是实例属性（redis 客户端），不是方法
        conn = broker.connection
        list_key = broker.list_key
        removed = 0
        for raw in conn.lrange(list_key, 0, -1):
            raw_str = raw.decode() if isinstance(raw, bytes) else str(raw)
            if self._queue_entry_matches(raw_str, sms_key, task_keys):
                conn.lrem(list_key, 1, raw)
                removed += 1
        return removed

    def _remove_orm_entries(self, sms_key: str, task_keys: set[str]) -> int:
        from django_q.models import OrmQ

        removed = 0
        for entry in list(OrmQ.objects.all()):
            if self._queue_entry_matches(entry.payload, sms_key, task_keys):
                entry.delete()
                removed += 1
        return removed

    @classmethod
    def _queue_entry_matches(cls, payload: str, sms_key: str, task_keys: set[str]) -> bool:
        """解析 SignedPackage 队列条目，判断是否属于该短信/其下载任务。

        submit_task 统一包一层 run_task：payload 的 func 是 run_task、
        args 是 [target, [业务参数], kwargs, ctx]，因此先剥壳再匹配。
        """
        from django_q.signing import SignedPackage

        try:
            data = SignedPackage.loads(payload)
        except Exception:
            return False
        if not isinstance(data, dict):
            return False

        func = str(data.get("func") or "")
        args = data.get("args") or []
        if func == _RUN_TASK_FUNC and isinstance(args, (list, tuple)) and len(args) >= 2:
            func = str(args[0])
            args = args[1]
        if not isinstance(args, (list, tuple)):
            args = [args]
        arg_keys = {str(a) for a in args}

        if func in _SMS_WORKER_FUNCS:
            return sms_key in arg_keys
        if func in _TASK_ID_WORKER_FUNCS:
            return bool(arg_keys & task_keys)
        return False
