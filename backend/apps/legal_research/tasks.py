from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from apps.legal_research.services.case_download_service import CaseDownloadService
from apps.legal_research.services.executor import LegalResearchExecutor


def execute_legal_research_task(task_id: str) -> dict[str, Any]:
    # Playwright 同步API内部会维护事件循环，执行过程中同步 ORM 读写
    # 可能触发 Django 的 async 上下文保护。任务是后台同步执行流程，
    # 这里显式放开该限制，避免误判失败。
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    executor = LegalResearchExecutor()
    # 隔离到独立线程，避免上游异步上下文导致 ORM 抛出
    # "You cannot call this from an async context"。
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="legal-research-executor") as pool:
        future = pool.submit(executor.run, task_id=task_id)
        return future.result()


def execute_case_download_task(task_id: int) -> dict[str, Any]:
    """执行案例下载任务"""
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    service = CaseDownloadService()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="case-download-executor") as pool:
        future = pool.submit(service.execute_task, task_id=task_id)
        return future.result()
