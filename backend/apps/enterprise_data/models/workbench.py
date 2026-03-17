"""Admin 调试工作台占位模型。"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.security.scrub import scrub_for_storage, scrub_text


class McpWorkbench(models.Model):
    id: int
    name = models.CharField(max_length=64, default="MCP Workbench")

    class Meta:
        managed = False
        verbose_name = _("MCP 调试工作台")
        verbose_name_plural = _("MCP 调试工作台")


class McpWorkbenchExecution(models.Model):
    """MCP 调试执行历史。"""

    id: int
    provider = models.CharField(max_length=64, verbose_name=_("Provider"))
    tool_name = models.CharField(max_length=128, verbose_name=_("工具名称"))
    arguments = models.JSONField(default=dict, blank=True, verbose_name=_("请求参数"))
    response_data = models.JSONField(default=dict, blank=True, verbose_name=_("响应数据"))
    response_raw = models.JSONField(default=dict, blank=True, verbose_name=_("原始响应"))
    response_meta = models.JSONField(default=dict, blank=True, verbose_name=_("响应元信息"))
    success = models.BooleanField(default=False, verbose_name=_("是否成功"))
    error_code = models.CharField(max_length=64, blank=True, default="", verbose_name=_("错误码"))
    error_message = models.TextField(blank=True, default="", verbose_name=_("错误信息"))
    duration_ms = models.PositiveIntegerField(default=0, verbose_name=_("耗时(毫秒)"))
    requested_transport = models.CharField(max_length=32, blank=True, default="", verbose_name=_("请求协议"))
    actual_transport = models.CharField(max_length=32, blank=True, default="", verbose_name=_("实际协议"))
    operator_username = models.CharField(max_length=150, blank=True, default="", verbose_name=_("操作人"))
    replay_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replayed_records",
        verbose_name=_("重放来源"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("MCP 调试执行历史")
        verbose_name_plural = _("MCP 调试执行历史")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["provider", "tool_name", "-created_at"]),
            models.Index(fields=["success", "-created_at"]),
            models.Index(fields=["operator_username", "-created_at"]),
        ]

    def __str__(self) -> str:
        status = "success" if self.success else "failed"
        return f"{self.provider}:{self.tool_name}:{status}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.arguments = self._sanitize_json(self.arguments)
        self.response_data = self._sanitize_json(self.response_data)
        self.response_raw = self._sanitize_json(self.response_raw)
        self.response_meta = self._sanitize_json(self.response_meta)
        if self.error_message:
            self.error_message = scrub_text(self.error_message)
        super().save(*args, **kwargs)

    @staticmethod
    def _sanitize_json(value: Any) -> Any:
        scrubbed = scrub_for_storage(value)
        try:
            serialized = json.dumps(scrubbed, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return scrubbed
        if len(serialized) <= 50000:
            return scrubbed
        return {
            "_truncated": True,
            "preview": serialized[:12000],
            "original_length": len(serialized),
        }
