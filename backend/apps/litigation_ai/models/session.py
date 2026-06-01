"""Module for session."""

import uuid
from typing import Any, ClassVar

from django.db import models

from .choices import DocumentType, SessionStatus, SessionType


class LitigationSession(models.Model):
    case_id: int  # 外键ID字段
    user_id: int  # 外键ID字段
    session_id = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="会话ID",
        help_text="唯一标识一次文书生成会话",
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="litigation_sessions",
        verbose_name="关联案件",
    )
    user = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="litigation_sessions",
        verbose_name="创建人",
    )
    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.DOC_GEN,
        verbose_name="会话类型",
        help_text="文书生成或模拟庭审",
    )
    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
        blank=True,
        verbose_name="文书类型",
        help_text="起诉状、答辩状、反诉状等",
    )
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE,
        verbose_name="会话状态",
    )
    metadata = models.JSONField(
        default=dict,
        verbose_name="会话元数据",
        help_text="存储诉讼目标、证据清单ID、token消耗等信息",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "documents_litigationsession"
        verbose_name = "AI文书生成会话"
        verbose_name_plural = "AI文书生成会话"
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["session_id"]),
            models.Index(fields=["case", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["document_type"]),
            models.Index(fields=["session_type"]),
        ]

    @property
    def session_id_short(self) -> str:
        return str(self.session_id)[:8]

    @property
    def litigation_goal(self) -> str:
        return str((self.metadata or {}).get("litigation_goal", ""))

    @property
    def evidence_list_ids(self) -> list[Any]:
        result = (self.metadata or {}).get("evidence_list_ids", [])
        return list(result) if isinstance(result, list) else []

    @property
    def total_tokens(self) -> int:
        result = (self.metadata or {}).get("total_tokens", 0)
        return int(result) if isinstance(result, int) else 0

    @property
    def model_name(self) -> str:
        return str((self.metadata or {}).get("model", ""))
