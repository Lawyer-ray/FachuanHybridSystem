"""启动 Temporal Worker（Django 管理命令）

用法:
  python manage.py start_temporal_worker
  python manage.py start_temporal_worker --temporal-address localhost:7233
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Callable, Sequence
from typing import Any

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


async def _cleanup_db_connections() -> None:
    """Periodically close stale DB connections while the worker is idle."""
    from django.db import close_old_connections

    while True:
        await asyncio.sleep(300)  # every 5 minutes
        close_old_connections()


class Command(BaseCommand):
    help = "启动 Temporal Worker 进程"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--temporal-address",
            default="localhost:7233",
            help="Temporal Server 地址 (默认: localhost:7233)",
        )
        parser.add_argument(
            "--task-queue",
            default="fachuan-workflow",
            help="Task Queue 名称 (默认: fachuan-workflow)",
        )
        parser.add_argument(
            "--max-activities",
            type=int,
            default=5,
            help="最大并发 Activity 数 (默认: 5)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        with self._temporal_sandbox_logging():
            asyncio.run(self._run(options))

    @contextlib.contextmanager
    def _temporal_sandbox_logging(self) -> Any:
        """在 worker 运行期间禁用 Django 自定义 logging filter。

        filter 会在 Temporal sandbox 里触发受限导入，需要临时旁路。

        注意：只在 worker 自己的 logger 实例上摘除 filter，并且**绝不改动
        RequestContextFilter 类本身**——类级 monkeypatch 是进程全局且不可逆的，
        会污染同一进程内其它代码对该 filter 的使用（例如测试进程）。退出时
        恢复原有 filters，保证不留副作用。
        """
        root = logging.getLogger()
        saved: list[Any] = list(root.filters)
        blocklist = self._get_request_context_filter_types()
        if blocklist:
            root.filters = [f for f in saved if not isinstance(f, blocklist)]
        try:
            yield
        finally:
            root.filters = saved

    @staticmethod
    def _get_request_context_filter_types() -> tuple[type, ...]:
        """从已加载模块中取 RequestContextFilter 类型；取不到则返回空元组。"""
        import sys

        logging_mod = sys.modules.get("apps.core.infrastructure.logging")
        if not logging_mod:
            return ()
        cls = getattr(logging_mod, "RequestContextFilter", None)
        return (cls,) if isinstance(cls, type) else ()

    async def _run(self, options: dict[str, Any]) -> None:
        from temporalio.client import Client
        from temporalio.worker import Worker
        from temporalio.worker._workflow_instance import UnsandboxedWorkflowRunner

        from apps.workflow.temporal.activities import (
            _HAS_COURT_FILING,
            analyze_single_evidence,
            apply_arrangement,
            build_litigation_context,
            collect_case_facts,
            download_litigation_document,
            execute_mcp_tool,
            fetch_template_schema,
            generate_complaint,
            generate_complaint_simple,
            generic_code_exec,
            generic_delay,
            generic_http_request,
            generic_llm_call,
            list_case_materials,
            record_step,
            review_complaint_quality,
            suggest_arrangement,
            summarize_evidence,
            update_run_status,
        )
        from apps.workflow.temporal.workflows import DynamicWorkflow, SalesContractDisputeWorkflow

        temporal_addr = options["temporal_address"]
        task_queue = options["task_queue"]

        client = await Client.connect(temporal_addr)
        self.stdout.write(f"已连接 Temporal Server: {temporal_addr}")

        # 使用 UnsandboxedWorkflowRunner 避免 Django 模块导入被 sandbox 拦截
        activities_list: list[Callable[..., Any]] = [
            record_step,
            update_run_status,
            collect_case_facts,
            list_case_materials,
            analyze_single_evidence,
            summarize_evidence,
            suggest_arrangement,
            apply_arrangement,
            build_litigation_context,
            generate_complaint,
            generate_complaint_simple,
            review_complaint_quality,
            download_litigation_document,
            fetch_template_schema,
            generic_delay,
            generic_llm_call,
            generic_http_request,
            generic_code_exec,
            execute_mcp_tool,
        ]

        w = Worker(
            client,
            task_queue=task_queue,
            workflows=[
                SalesContractDisputeWorkflow,
                DynamicWorkflow,
            ],
            activities=activities_list,
            max_concurrent_activities=options["max_activities"],
            workflow_runner=UnsandboxedWorkflowRunner(),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Temporal Worker 启动 (task_queue={task_queue}, max_activities={options['max_activities']})"
            )
        )

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(w.shutdown()))

        cleanup_task = asyncio.create_task(_cleanup_db_connections())
        try:
            await w.run()
        finally:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
