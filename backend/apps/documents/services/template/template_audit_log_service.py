"""模板审计日志服务（G12，2026-11-23 二轮审计）。

**为什么现在才补**：`apps/documents/signals.py` 从建好起就
`from .services.template.template_audit_log_service import TemplateAuditLogService`，
但**这个模块一直不存在** —— `except ImportError` 把异常降级成 `logger.debug` 后返回
`None`，于是 `TemplateAuditLog` 表建好了、枚举建好了、signal 也接了，**一条记录都写不进去**，
而且没有任何日志能看出这件事（`debug` 默认不输出）。

本模块只做一件事：把 signal 侧传来的内容落成一条 `TemplateAuditLog`。
最小实现优先——审计链的价值在于「有痕迹」，不在于功能多。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.documents.models.audit_log import TemplateAuditLog

logger = logging.getLogger("apps.documents")


class TemplateAuditLogService:
    """模板变更审计写入服务。"""

    def create_audit_log(
        self,
        content_type: str,
        object_id: int,
        object_repr: str,
        action: str,
        changes: dict[str, Any] | None = None,
        *,
        user: Any = None,
        ip_address: str | None = None,
        user_agent: str = "",
    ) -> TemplateAuditLog:
        """写一条审计日志。

        Args:
            content_type: `AuditContentType` 的值（folder_template / document_template / ...）
            object_id: 被操作对象主键
            object_repr: 对象描述（截断到 500）
            action: `TemplateAuditAction` 的值（created / updated / deleted ...）
            changes: 字段级变更 `{"field": {"old": ..., "new": ...}}`
            user: 操作人（可空；signal 路径拿不到 request 时为空）
        """
        log = TemplateAuditLog.objects.create(
            content_type=content_type,
            object_id=int(object_id),
            object_repr=str(object_repr)[:500],
            action=action,
            changes=changes or {},
            user=user if getattr(user, "pk", None) else None,
            ip_address=ip_address,
            user_agent=str(user_agent or "")[:500],
        )
        logger.info("模板审计已写入: content_type=%s object=%s action=%s", content_type, object_id, action)
        return log


__all__ = ["TemplateAuditLogService"]
