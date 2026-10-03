"""异步解析任务的创建与提交服务。

承载 parsing_api 下沉的调度逻辑：先建 DocumentParsingTask 记录（约定的
task_name ``document_parsing_{id}``，document_parsing_hook 才能把成功/失败
状态回写），再提交后台任务。service 内部自管 async 适配（sync_to_async），
API 层直接 await 调用即可。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async

from apps.core.tasking import submit_task
from apps.document_parsing.models import DocumentParsingTask

logger = logging.getLogger(__name__)

# 与 admin upload_view 同款模式：hook 通过 task_name 关联解析记录
PARSE_TASK_TARGET = "apps.document_parsing.tasks.execute_parse_document"
PARSE_TASK_HOOK = "apps.document_parsing.tasks.document_parsing_hook"
PARSE_TASK_TIMEOUT_SECONDS = 600


class DocumentParsingTaskDispatchService:
    """异步文档解析任务的记录创建与后台提交。"""

    async def submit_parse_task(
        self,
        *,
        file_name: str,
        file_path: Path,
        file_size: int,
        backend: str,
        extract_tables: bool,
        extract_images: bool,
        return_markdown: bool,
        created_by: Any | None,
    ) -> str:
        """创建 DocumentParsingTask 记录并提交后台解析任务，返回 task_id。

        created_by 记录归属人（审计 P1 修复），records 列表/详情按其过滤。
        """
        parsing_task = await sync_to_async(DocumentParsingTask.objects.create, thread_sensitive=False)(
            file_name=file_name,
            file_path=str(file_path),
            file_size=file_size,
            status=DocumentParsingTask.Status.PROCESSING,
            created_by=created_by,
        )
        task_id = await sync_to_async(submit_task, thread_sensitive=False)(
            PARSE_TASK_TARGET,
            str(file_path),
            Path(file_name).suffix.lstrip("."),
            backend,
            extract_tables,
            extract_images,
            return_markdown,
            task_name=f"document_parsing_{parsing_task.id}",
            hook=PARSE_TASK_HOOK,
            timeout=PARSE_TASK_TIMEOUT_SECONDS,
        )
        return task_id
