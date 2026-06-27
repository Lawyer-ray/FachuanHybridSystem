from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.db import close_old_connections

from apps.legal_research.services.task.case_download_service import CaseDownloadService
from apps.legal_research.services.task.executor import LegalResearchExecutor

# 注意: ThreadPoolExecutor max_workers=1 保证同一时刻只有一个线程
# 操作 ORM。如果将来增加 max_workers，必须确保每个线程独立调用
# close_old_connections() 防止连接泄漏。当前 Django 默认连接池大小
# 为 1 (每个线程一个连接)，max_workers>1 时需要配置 CONN_MAX_AGE 和
# pgbouncer/pgpool 等外部连接池。


def execute_legal_research_task(task_id: str) -> dict[str, Any]:  # pragma: no cover
    # Playwright 同步API内部会维护事件循环，执行过程中同步 ORM 读写
    # 可能触发 Django 的 async 上下文保护。任务是后台同步执行流程，
    # 这里显式放开该限制，避免误判失败。
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    executor = LegalResearchExecutor()
    # 隔离到独立线程，避免上游异步上下文导致 ORM 抛出
    # "You cannot call this from an async context"。
    # max_workers=1 与 Django 默认连接池大小匹配，避免连接耗尽。
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="legal-research-executor") as pool:
        future = pool.submit(executor.run, task_id=task_id)
        try:
            return future.result()
        finally:
            close_old_connections()


def execute_case_download_task(task_id: int) -> dict[str, Any]:  # pragma: no cover
    """执行案例下载任务"""
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    service = CaseDownloadService()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="case-download-executor") as pool:
        future = pool.submit(service.execute_task, task_id=task_id)
        try:
            return future.result()
        finally:
            close_old_connections()
