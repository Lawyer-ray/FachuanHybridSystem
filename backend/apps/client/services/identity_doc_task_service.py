"""证件识别异步任务的提交与轮询服务（安全修复）。

此前 clientidentitydoc_api 的 submit 端点直接返回 Django-Q 原始 task_id、
轮询端点按 Q id 直查队列，无归属校验——持 Q id 者可读他人证件 OCR 结果
（PII）。本服务把两端点收拢为「业务记录 id 对外、Q id 内部关联」模式
（参照 legal_solution.SolutionTask.q_task_id 与 document_parsing 同款修复）：

- submit：建 ClientIdentityDocParseTask 记录 → 提交队列 → 回写 q_task_id →
  返回 ``{"task_id": str(记录id), "status": "pending"}``（响应形状不变，值换令牌）；
- 轮询：记录 id 优先解析 + q_task_id 兼容反查，均做归属校验
  （本人 / is_admin / is_superuser，与仓库 2026Q4 审计口径一致），
  无权或不存在一律 NotFoundError（404），不泄露任务是否存在；
  查询中顺带把队列终态 lazy 回写记录 status。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.client.models import ClientIdentityDocParseTask
from apps.client.services.wiring import get_task_service_port
from apps.core.exceptions import NotFoundError
from apps.core.security.admin_access import is_admin_user
from apps.core.services.storage_service import save_uploaded_file
from apps.core.tasking import TaskQueryService

logger = logging.getLogger("apps.client")

RECOGNIZE_TASK_TARGET = "apps.client.tasks.execute_identity_doc_recognition"
_RECOGNIZE_UPLOAD_REL_DIR = "client_docs/recognize"


class IdentityDocTaskService:
    """证件识别异步任务的提交与归属校验轮询。"""

    def submit_recognize_task(
        self,
        *,
        uploaded_file: Any,
        doc_type: str,
        user: Any | None,
    ) -> dict[str, Any]:
        """保存上传文件、建记录并提交识别任务，返回记录 id 令牌。

        doc_type 缺省回退 id_card（execute_identity_doc_recognition 的
        doc_type 为必填参数，缺省会令任务 100% TypeError）。
        """
        normalized_doc_type = (doc_type or "").strip() or "id_card"
        rel_path, _saved_name = save_uploaded_file(uploaded_file, rel_dir=_RECOGNIZE_UPLOAD_REL_DIR)

        record = ClientIdentityDocParseTask.objects.create(
            doc_type=normalized_doc_type,
            status=ClientIdentityDocParseTask.Status.PENDING,
            created_by=user,
        )
        q_task_id = get_task_service_port().submit_task(
            RECOGNIZE_TASK_TARGET,
            rel_path,
            normalized_doc_type,
        )
        record_id = record.id
        ClientIdentityDocParseTask.objects.filter(pk=record_id).update(q_task_id=q_task_id)
        logger.info(
            "证件识别任务已提交",
            extra={
                "task_id": str(record_id),
                "q_task_id": q_task_id,
                "file_path": rel_path,
                "doc_type": normalized_doc_type,
            },
        )
        return {"task_id": str(record_id), "status": "pending"}

    def get_task_status(self, task_id: str, *, user: Any | None) -> dict[str, Any]:
        """归属校验后查询队列状态，响应形状与原直查 Q 端点一致。

        task_id 为客户端令牌（新契约记录 id / 存量 Q id），响应中的
        task_id 字段回显该令牌，其余字段来自队列任务。
        """
        record = self._resolve_record(task_id, user=user)
        info = TaskQueryService().get_task_status(record.q_task_id or task_id)
        info["task_id"] = task_id
        self._sync_record_status(record, q_status=info["status"])
        return info

    def _resolve_record(self, task_id: str, *, user: Any | None) -> ClientIdentityDocParseTask:
        if is_admin_user(user):
            qs = ClientIdentityDocParseTask.objects.all()
        else:
            qs = ClientIdentityDocParseTask.objects.filter(created_by=user)
        # 1) 新契约：task_id 即记录 id
        if task_id.isdigit():
            record = qs.filter(pk=int(task_id)).first()
            if record is not None:
                return record
        # 2) 兼容：客户端持本修复部署后任务的 Q id
        record = qs.filter(q_task_id=task_id).first()
        if record is not None:
            return record
        logger.warning("证件识别任务状态查询被拒（不存在或无权）: task_id=%s", task_id)
        raise NotFoundError(
            message=f"证件识别任务不存在或无权访问: task_id={task_id}",
            code="IDENTITY_DOC_TASK_NOT_FOUND",
        )

    def _sync_record_status(self, record: ClientIdentityDocParseTask, *, q_status: str) -> None:
        """把队列终态 lazy 回写记录 status（仅有人轮询时更新，避免引入 hook）。"""
        status_map = {
            "success": ClientIdentityDocParseTask.Status.SUCCESS,
            "failure": ClientIdentityDocParseTask.Status.FAILED,
        }
        mapped = status_map.get(q_status)
        if mapped is not None and record.status != mapped:
            ClientIdentityDocParseTask.objects.filter(pk=record.pk).update(status=mapped)
