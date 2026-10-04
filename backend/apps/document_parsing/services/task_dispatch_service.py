"""异步解析任务的创建与提交服务。

承载 parsing_api 下沉的调度逻辑：先建 DocumentParsingTask 记录（约定的
task_name ``document_parsing_{id}``，document_parsing_hook 才能把成功/失败
状态回写），再提交后台任务。service 内部自管 async 适配（sync_to_async），
API 层直接 await 调用即可。

安全修复：对外返回的 task_id 是 DocumentParsingTask 记录 id（字符串形式），
Django-Q 原始 id 仅回写记录的 q_task_id 供轮询端点内部反查，不再暴露给客户端。
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
EXTRACT_TEXT_TASK_TARGET = "apps.document_parsing.tasks.execute_extract_text"
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
        """创建 DocumentParsingTask 记录并提交后台解析任务，返回记录 id。

        created_by 记录归属人（审计 P1 修复），records 列表/详情按其过滤。
        返回值为记录 id（字符串），Q 任务 id 回写 q_task_id 供轮询端点内部反查。
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
        await sync_to_async(self._record_q_task_id, thread_sensitive=False)(parsing_task.id, task_id)
        return str(parsing_task.id)

    async def submit_extract_text_task(
        self,
        *,
        file_name: str,
        file_path: Path,
        file_size: int,
        backend: str,
        max_length: int | None,
        created_by: Any | None,
    ) -> str:
        """创建 DocumentParsingTask 记录并提交后台文本提取任务，返回记录 id。

        与 submit_parse_task 同模式（安全修复前 extract-text 异步路径不建
        记录、直接返回 Q id）：记录让轮询端点可做归属校验，hook 复用
        ``document_parsing_{id}`` 约定回写状态（extract 结果的 method 键
        由 hook 兼容映射到 backend_used）。
        """
        parsing_task = await sync_to_async(DocumentParsingTask.objects.create, thread_sensitive=False)(
            file_name=file_name,
            file_path=str(file_path),
            file_size=file_size,
            status=DocumentParsingTask.Status.PROCESSING,
            created_by=created_by,
        )
        task_id = await sync_to_async(submit_task, thread_sensitive=False)(
            EXTRACT_TEXT_TASK_TARGET,
            str(file_path),
            backend,
            max_length,
            task_name=f"document_parsing_{parsing_task.id}",
            hook=PARSE_TASK_HOOK,
            timeout=PARSE_TASK_TIMEOUT_SECONDS,
        )
        await sync_to_async(self._record_q_task_id, thread_sensitive=False)(parsing_task.id, task_id)
        return str(parsing_task.id)

    def _record_q_task_id(self, record_id: int, q_task_id: str) -> None:
        """把 Django-Q 任务 id 回写到解析记录（update 避免整行覆盖并发回写）。"""
        updated = DocumentParsingTask.objects.filter(pk=record_id).update(q_task_id=q_task_id)
        if not updated:
            logger.warning("解析记录不存在，q_task_id 未回写: record_id=%s", record_id)
