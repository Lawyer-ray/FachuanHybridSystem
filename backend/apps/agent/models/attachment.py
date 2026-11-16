"""Agent 对话附件模型 —— 用户拖拽/选择上传给 AI 助手的文件。

## 设计要点

- **文件内容不进模型上下文**：MCP 工具 ``read_agent_attachment``
  在服务端读文件、走 /document-parsing 提取**文本**后返回——
  base64/大文件只在服务端流转，模型只看到正文。
- **归属随会话**：挂在 session 上（删会话级联清理记录与物理文件），
  归属校验仍以 user 为准——传别人的 attachment_id 读不到任何内容。
- **存储走全局规范**：`save_uploaded_file`（清洗/校验/限额）+
  ``DatedUUIDPath(MediaEntity.AGENT_ATTACHMENTS)`` 工厂路径，
  CharField 存路径属「工具模块附件」特例，post_delete 连带清理物理文件。
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .session import AgentSession

logger = logging.getLogger(__name__)


class AgentAttachment(models.Model):
    """对话附件。"""

    attachment_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="附件标识",
    )
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_attachments",
        null=True,
        blank=True,
        verbose_name="上传人",
    )
    filename = models.CharField(max_length=255, verbose_name="原始文件名")
    storage_path = models.CharField(max_length=500, verbose_name="存储路径")
    mime = models.CharField(max_length=100, blank=True, default="", verbose_name="MIME 类型")
    size = models.IntegerField(default=0, verbose_name="大小（字节）")
    #: 引用型附件（拖拽绑定文件夹文件进来）指向绑定文件夹内的原文件：
    #: **storage_path 留空**（post_delete 物理清理只认 storage_path，绝不触碰
    #: 业务归档原文件），读取走 folder_refs 服务（ACL + 逃逸校验在解析层）。
    #: ref_owner_kind 决定 ref_owner 指向合同还是案件（存量行没有该字段值
    #: 时按 contract 处理）；合同绑定与案件绑定是两套独立的文件夹。
    ref_owner_kind = models.CharField(
        max_length=16,
        blank=True,
        default="contract",
        verbose_name="引用归属类型",
        choices=[("contract", "合同"), ("case", "案件")],
    )
    ref_contract_id = models.BigIntegerField(null=True, blank=True, verbose_name="引用归属 id（合同或案件）")
    ref_subpath = models.CharField(max_length=500, blank=True, default="", verbose_name="引用子路径")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    class Meta:
        verbose_name = "Agent 附件"
        verbose_name_plural = "Agent 附件"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="agent_attach_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.filename} ({self.size}B)"


@receiver(post_delete, sender=AgentAttachment)
def _delete_agent_attachment_file(sender: type[AgentAttachment], instance: AgentAttachment, **kwargs: object) -> None:
    """删除附件记录时连带清理物理文件（media 规范：CharField 路径特例必须配 post_delete）。"""
    if instance.storage_path:
        try:
            default_storage.delete(instance.storage_path)
        except Exception:
            # 物理文件清理失败不影响记录删除；孤儿文件可由定期巡检收拾
            logger.warning("agent 附件物理文件删除失败: %s", instance.storage_path, exc_info=True)
