from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.db import close_old_connections

from apps.core.infrastructure.async_context import allow_async_unsafe
from apps.legal_research.services.task.case_download_service import CaseDownloadService
from apps.legal_research.services.task.executor import LegalResearchExecutor

# 注意: ThreadPoolExecutor max_workers=1 保证同一时刻只有一个线程
# 操作 ORM。如果将来增加 max_workers，必须确保每个线程独立调用
# close_old_connections() 防止连接泄漏。当前 Django 默认连接池大小
# 为 1 (每个线程一个连接)，max_workers>1 时需要配置 CONN_MAX_AGE 和
# pgbouncer/pgpool 等外部连接池。


def execute_legal_research_task(task_id: str) -> dict[str, Any]:  # pragma: no cover
    # 【保留作用域化放行的原因】Weike 客户端是同步 Playwright：playwright 的
    # _impl/_sync_base 在每次 sync 调用返回用户代码前执行 asyncio._set_running_loop，
    # open_session 之后执行器线程长期挂着"运行中循环"，同线程任何直接 sync ORM
    # 都会抛 SynchronousOnlyOperation。环境变量是进程级的，在提交线程设置即可
    # 覆盖 worker 线程的整个执行窗口（本函数阻塞在 future.result，窗口恰好重合）。
    #
    # ORM 段与 Playwright/HTTP 段在 LegalResearchExecutor.run（650 行主循环 + 9 个
    # executor_components mixin）内深度交错，无法分段 aget/aupdate 化：
    # - 已循环安全的段：task_lifecycle 的 ORM（_save_task_safely/_acquire_task/
    #   _is_cancel_requested）经 _run_orm_safely 在检测到运行循环时摆渡到单 worker 线程；
    # - 仍直连 sync ORM 的段：executor_components/result_persistence.py 的 _save_result
    #   （get_or_create + result.save，@transaction.atomic）在候选循环内每命中一篇调用
    #   一次，与 Playwright 检索/下载逐条交错，是本放行的硬依赖。
    #
    # 去掉本放行的改造清单：① _save_result 整体接入 _run_orm_safely（注意
    # transaction.atomic 需随 callable 一起搬线程，且禁止与其他 ORM 摆渡嵌套——
    # _ORM_FALLBACK_EXECUTOR 单 worker 会死锁）；② 或将 Weike 客户端 +
    # LegalResearchExecutor 全链改 async Playwright（约 2800 行 mixin + 650 行主循环
    # 重写）。两者均为整体改造，见 apps/legal_research/services/capability/service.py
    # 的 _execute_with_timeout——它跑的是同一执行器，清偿时须一并处理。
    with allow_async_unsafe():
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
    # 同 execute_legal_research_task 的保留原因：同步 Playwright 的 _set_running_loop
    # 使执行线程带上运行中循环。CaseDownloadService.execute_task 的 ORM 段
    # （task.save 进度更新、CaseDownloadResult.objects.create 结果落库）与 Playwright
    # 段（open_session/search_cases/fetch_case_detail/download_pdf）在逐案循环内交错
    # （每 5 案一次进度落库 + 每案 1-2 次结果落库），且未接入 _run_orm_safely 摆渡，
    # 去掉放行会在首个进度落库处抛 SynchronousOnlyOperation。改造需把逐案循环与
    # Weike 客户端一起 async 化（同 execute_legal_research_task 注释的改造清单②），
    # 属整体改造，暂保留作用域化。
    with allow_async_unsafe():
        service = CaseDownloadService()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="case-download-executor") as pool:
            future = pool.submit(service.execute_task, task_id=task_id)
            try:
                return future.result()
            finally:
                close_old_connections()
