# mypy: disable-error-code=var-annotated
from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.filesystem.upload_paths import DatedUUIDPath


class WeChatAccount(models.Model):
    """公众号账号配置"""

    id: int
    name = models.CharField("账号名称", max_length=100)
    mp_url = models.URLField("公众号后台地址", default="https://mp.weixin.qq.com")
    is_active = models.BooleanField("是否启用", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wechat_accounts",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "公众号账号"
        verbose_name_plural = "公众号账号"
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class PublishTaskStatus(models.TextChoices):
    PENDING = "pending", _("待处理")
    LOGGING_IN = "logging_in", _("登录中")
    EDITING = "editing", _("编辑中")
    PUBLISHING = "publishing", _("发布中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class PublishTask(models.Model):
    """公众号文章发布任务"""

    id: int
    account = models.ForeignKey(
        WeChatAccount,
        on_delete=models.CASCADE,
        related_name="publish_tasks",
        verbose_name="公众号账号",
    )
    title = models.CharField("文章标题", max_length=64)
    content_md = models.TextField("Markdown 内容")
    content_html = models.TextField("HTML 内容", blank=True, default="")
    cover_image = models.ImageField(
        upload_to=DatedUUIDPath("wechat_mp/covers"),
        blank=True,
        null=True,
        verbose_name="封面图",
    )
    status = models.CharField(
        max_length=20,
        choices=PublishTaskStatus.choices,
        default=PublishTaskStatus.PENDING,
        verbose_name="任务状态",
    )
    save_as_draft = models.BooleanField("保存为草稿", default=True)
    result_data = models.JSONField("结果数据", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default="")
    queue_task_id = models.CharField("队列任务ID", max_length=64, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wechat_publish_tasks",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(blank=True, null=True, verbose_name="完成时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "发布任务"
        verbose_name_plural = "发布任务"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["account", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.status} - {self.title}"
