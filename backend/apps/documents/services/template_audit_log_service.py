"""
模板审计日志服务

封装审计日志的 ORM 操作，供 Signal 层委托调用。
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class TemplateAuditLogService:
    """模板审计日志 Service，封装 ORM 写入和查询操作。"""

    def create_audit_log(
        self,
        content_type: str,
        object_id: int,
        object_repr: str,
        action: str,
        changes: dict[str, Any],
    ) -> None:
        """创建一条审计日志记录。"""
        from apps.documents.models import TemplateAuditLog

        try:
            TemplateAuditLog.objects.create(
                content_type=content_type,
                object_id=object_id,
                object_repr=object_repr[:500],
                action=action,
                changes=changes or {},
            )
            logger.debug(
                "审计日志已记录: %s #%s - %s",
                content_type,
                object_id,
                action,
            )
        except Exception:
            logger.error(
                _("创建审计日志失败: content_type=%s, object_id=%s"),
                content_type,
                object_id,
                exc_info=True,
            )

    def get_instance_by_pk(self, model_class: type[Any], pk: int) -> Any | None:
        """通过主键获取模型实例，不存在时返回 None。"""
        try:
            return model_class.objects.get(pk=pk)  # type: ignore[attr-defined]
        except model_class.DoesNotExist:  # type: ignore[attr-defined]
            return None
