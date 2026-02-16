"""
对话历史模型

本模块定义对话历史数据模型,用于存储用户与系统的对话记录.
"""

from typing import ClassVar

from django.db import models


class ConversationHistory(models.Model):
    """对话历史模型

    存储用户与系统的对话记录,支持多种角色(系统、用户、助手).
    可关联到 AI 文书生成会话.
    """

    id: int
    litigation_session_id: int  # 外键ID字段
    session_id = models.CharField(max_length=100, verbose_name="会话ID")
    user_id = models.CharField(blank=True, max_length=100, verbose_name="用户ID")
    role = models.CharField(
        choices=[("system", "系统"), ("user", "用户"), ("assistant", "助手")],
        max_length=20,
        verbose_name="角色",
    )
    content = models.TextField(verbose_name="消息内容")
    metadata = models.JSONField(blank=True, default=dict, verbose_name="元数据")

    # AI 文书生成扩展字段
    litigation_session = models.ForeignKey(
        "litigation_ai.LitigationSession",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="conversation_histories",
        verbose_name="AI文书生成会话",
        help_text="关联到 AI 文书生成会话(如果适用)",
    )
    step = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="对话步骤",
        help_text="document_type/litigation_goal/evidence_selection/generation",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name: str = "对话历史"
        verbose_name_plural: str = "对话历史"
        db_table: str = "core_conversation_history"
        ordering: ClassVar = ["session_id", "created_at"]
        indexes: ClassVar = [
            models.Index(fields=["session_id", "created_at"], name="core_conver_session_f8b2e5_idx"),
            models.Index(fields=["user_id", "created_at"], name="core_conver_user_id_8a9c4d_idx"),
            models.Index(fields=["litigation_session", "created_at"]),
            models.Index(fields=["step"]),
        ]

    def __str__(self) -> None:
        return f"{self.session_id} - {self.role} - {self.created_at}"
