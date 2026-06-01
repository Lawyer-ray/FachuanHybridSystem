from __future__ import annotations

from typing import ClassVar

from django.db import models


class LegalResearchTaskEvent(models.Model):
    class Stage(models.TextChoices):
        SEARCH = "search", "检索"
        DETAIL = "detail", "详情"

    class Source(models.TextChoices):
        API = "api", "API"
        DOM = "dom", "DOM"
        SYSTEM = "system", "系统"

    task = models.ForeignKey(
        "legal_research.LegalResearchTask",
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="任务",
    )
    stage = models.CharField(max_length=32, choices=Stage.choices, db_index=True, verbose_name="阶段")
    source = models.CharField(max_length=16, choices=Source.choices, db_index=True, verbose_name="来源")
    interface_name = models.CharField(max_length=64, verbose_name="接口名")
    method = models.CharField(max_length=12, blank=True, verbose_name="请求方法")
    url = models.TextField(blank=True, verbose_name="请求URL")
    status_code = models.IntegerField(null=True, blank=True, verbose_name="状态码")
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="耗时(ms)")
    success = models.BooleanField(default=True, verbose_name="是否成功")
    error_code = models.CharField(max_length=64, blank=True, verbose_name="错误码")
    error_message = models.CharField(max_length=255, blank=True, verbose_name="错误消息")
    request_summary = models.JSONField(default=dict, blank=True, verbose_name="请求摘要")
    response_summary = models.JSONField(default=dict, blank=True, verbose_name="返回摘要")
    event_metadata = models.JSONField(default=dict, blank=True, verbose_name="扩展元数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "案例检索事件"
        verbose_name_plural = "案例检索事件"
        ordering: ClassVar = ["created_at", "id"]
        indexes: ClassVar = [
            models.Index(fields=["task", "stage", "created_at"]),
            models.Index(fields=["task", "source", "created_at"]),
            models.Index(fields=["task", "interface_name", "created_at"]),
        ]

    def __str__(self) -> str:
        status = "ok" if self.success else "fail"
        return f"{self.task_id} | {self.stage}/{self.source} | {self.interface_name} | {status}"
