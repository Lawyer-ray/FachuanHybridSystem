"""异步任务状态轮询服务（带归属校验）。

安全修复：轮询端点不再拿客户端传入的 task_id 直查 django_q Task（任何
持 Q id 者都能读到他人文档解析全文）。改为先解析出归属可见的
DocumentParsingTask 记录，再用记录的 q_task_id 内部查询队列状态：

1. task_id 为数字 → 按记录 id 直查（新契约：提交端点返回记录 id）；
2. 按 q_task_id 反查（本修复部署后提交、灰度期间仍持 Q id 的客户端）；
3. 存量兜底：Q id → Task.task_name（``document_parsing_{id}`` 约定）→ 记录 id
   （本修复部署前提交的任务，记录上 q_task_id 为空）。

三层解析均套 record_ownership_q 归属口径（与 /records 端点一致），
无权或不存在一律 NotFoundError（404），不泄露任务是否存在。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

from apps.core.exceptions import NotFoundError
from apps.core.tasking import TaskQueryService
from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.services.record_service import record_ownership_q

logger = logging.getLogger("apps.document_parsing")

_TASK_NAME_PREFIX = "document_parsing_"


class DocumentParsingTaskStatusService:
    """按归属过滤的异步任务状态查询。"""

    def get_task_status(self, task_id: str, *, user: Any | None) -> dict[str, Any]:
        """归属校验后查询队列状态，响应形状与原 TaskQueryService 一致。

        task_id 为客户端令牌（新契约记录 id / 存量 Q id），响应中的
        task_id 字段回显该令牌，其余字段来自队列任务。
        """
        record = self._resolve_record(task_id, user=user)
        info = TaskQueryService().get_task_status(record.q_task_id or task_id)
        info["task_id"] = task_id
        return info

    def _visible_records(self, user: Any | None) -> QuerySet[DocumentParsingTask]:
        """按 /records 同款归属口径过滤后的 queryset。"""
        qs: QuerySet[DocumentParsingTask] = DocumentParsingTask.objects.all()
        ownership = record_ownership_q(user)
        if ownership is not None:
            qs = qs.filter(ownership)
        return qs

    def _resolve_record(self, task_id: str, *, user: Any | None) -> DocumentParsingTask:
        qs = self._visible_records(user)
        # 1) 新契约：task_id 即记录 id
        if task_id.isdigit():
            record = qs.filter(pk=int(task_id)).first()
            if record is not None:
                return record
        # 2) 灰度兼容：客户端持本修复部署后任务的 Q id
        record = qs.filter(q_task_id=task_id).first()
        if record is not None:
            return record
        # 3) 存量兜底：部署前提交的任务（记录上无 q_task_id），经 task_name 约定反解
        record = self._resolve_via_task_name(task_id, qs=qs)
        if record is not None:
            return record
        logger.warning("解析任务状态查询被拒（不存在或无权）: task_id=%s", task_id)
        raise NotFoundError(message=f"解析任务不存在或无权访问: task_id={task_id}", code="PARSE_TASK_NOT_FOUND")

    def _resolve_via_task_name(self, task_id: str, *, qs: QuerySet[DocumentParsingTask]) -> DocumentParsingTask | None:
        """Q id → Task.task_name（document_parsing_{id}）→ 记录 id 反查。"""
        q_task = TaskQueryService().get_task_by_id(task_id)
        name = getattr(q_task, "name", "") or "" if q_task is not None else ""
        if not name.startswith(_TASK_NAME_PREFIX):
            return None
        record_id = name[len(_TASK_NAME_PREFIX) :]
        if not record_id.isdigit():
            return None
        return qs.filter(pk=int(record_id)).first()
