"""启动 Temporal Worker（Django 管理命令）

用法:
  python manage.py start_temporal_worker
  python manage.py start_temporal_worker --temporal-address localhost:7233
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


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
        self._setup_logging()
        asyncio.run(self._run(options))

    def _setup_logging(self) -> None:
        """禁用 Django 自定义 logging filter（会触发 Temporal sandbox 受限导入）

        使用 getattr 安全访问，避免触发额外导入。
        """
        import sys

        # 直接从已加载的模块中获取 RequestContextFilter
        logging_mod = sys.modules.get("apps.core.infrastructure.logging")
        if logging_mod:
            cls = getattr(logging_mod, "RequestContextFilter", None)
            if cls:
                cls.filter = lambda self, record: True

    async def _run(self, options: dict[str, Any]) -> None:
        from temporalio.client import Client
        from temporalio.worker import Worker
        from temporalio.worker._workflow_instance import UnsandboxedWorkflowRunner

        from apps.workflow.temporal.activities import (
            analyze_single_evidence,
            apply_arrangement,
            build_litigation_context,
            collect_case_facts,
            download_litigation_document,
            execute_court_filing,
            generate_complaint,
            generate_complaint_simple,
            list_case_materials,
            record_step,
            review_complaint_quality,
            suggest_arrangement,
            summarize_evidence,
            update_run_status,
        )
        from apps.workflow.temporal.workflows import SalesContractDisputeWorkflow

        temporal_addr = options["temporal_address"]
        task_queue = options["task_queue"]

        client = await Client.connect(temporal_addr)
        self.stdout.write(f"已连接 Temporal Server: {temporal_addr}")

        # 使用 UnsandboxedWorkflowRunner 避免 Django 模块导入被 sandbox 拦截
        w = Worker(
            client,
            task_queue=task_queue,
            workflows=[
                SalesContractDisputeWorkflow,
            ],
            activities=[
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
                execute_court_filing,
                download_litigation_document,
            ],
            max_concurrent_activities=options["max_activities"],
            workflow_runner=UnsandboxedWorkflowRunner(),
        )

        self.stdout.write(self.style.SUCCESS(
            f"Temporal Worker 启动 (task_queue={task_queue}, max_activities={options['max_activities']})"
        ))

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(w.shutdown()))

        await w.run()
