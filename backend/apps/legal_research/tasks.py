from __future__ import annotations

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
    # Weike 客户端是同步 Playwright：其 _impl/_sync_base 在每次 sync 调用返回
    # 用户代码前执行 asyncio._set_running_loop，open_session 之后执行器线程
    # 长期挂着"运行中循环"。执行器全部 ORM 段（task_lifecycle 既有摆渡 +
    # result_persistence._save_result / event_service）均经 _run_orm_safely
    # 摆渡到单 worker 线程执行，无需 allow_async_unsafe 放行。新增 ORM 调用
    # 必须同样走 _run_orm_safely（原子体搬线程时禁止嵌套其他摆渡，单 worker
    # 会死锁）。
    executor = LegalResearchExecutor()
    # 隔离到独立线程：既隔离上游异步上下文，也让 close_old_connections
    # 的清理边界与执行线程对齐。
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="legal-research-executor") as pool:
        future = pool.submit(executor.run, task_id=task_id)
        try:
            return future.result()
        finally:
            close_old_connections()


def execute_case_download_task(task_id: int) -> dict[str, Any]:  # pragma: no cover
    """执行案例下载任务"""
    # 同 execute_legal_research_task：open_session 后本线程带运行中循环，
    # CaseDownloadService 循环内的 ORM 写（进度/结果落库）已全部接入
    # _run_orm_safely 摆渡，无需 allow_async_unsafe 放行。
    service = CaseDownloadService()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="case-download-executor") as pool:
        future = pool.submit(service.execute_task, task_id=task_id)
        try:
            return future.result()
        finally:
            close_old_connections()
