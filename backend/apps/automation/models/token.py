"""Token 管理相关模型"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.model_fields.encrypted import EncryptedTextField


class CourtToken(models.Model):
    """法院系统 Token 存储"""

    id: int
    site_name = models.CharField(max_length=128, verbose_name=_("网站名称"), help_text=_("如:court_zxfw"))
    account = models.CharField(max_length=128, verbose_name=_("账号"))
    token = EncryptedTextField(verbose_name=_("Token"), help_text=_("JWT Token 或其他认证令牌"))
    token_type = models.CharField(
        max_length=32, default="Bearer", verbose_name=_("Token 类型"), help_text=_("如:Bearer, JWT")
    )
    expires_at = models.DateTimeField(verbose_name=_("过期时间"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("Token管理")
        verbose_name_plural = _("Token管理")
        unique_together: ClassVar = [["site_name", "account"]]
        indexes: ClassVar = [
            models.Index(fields=["site_name", "account"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.site_name} - {self.account}"

    def is_expired(self) -> bool:
        """判断是否过期"""
        from django.utils import timezone

        return self.expires_at <= timezone.now()


class TokenAcquisitionStatus(models.TextChoices):
    """Token获取状态"""

    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")
    TIMEOUT = "timeout", _("超时")
    NETWORK_ERROR = "network_error", _("网络错误")
    CAPTCHA_ERROR = "captcha_error", _("验证码错误")
    CREDENTIAL_ERROR = "credential_error", _("账号密码错误")


class TokenAcquisitionHistory(models.Model):
    """Token获取历史记录"""

    id: int
    site_name = models.CharField(max_length=128, verbose_name=_("网站名称"), help_text=_("如:court_zxfw"))
    account = models.CharField(max_length=128, verbose_name=_("使用账号"))
    credential_id = models.IntegerField(
        null=True, blank=True, verbose_name=_("凭证ID"), help_text=_("关联的AccountCredential ID")
    )
    status = models.CharField(max_length=32, choices=TokenAcquisitionStatus.choices, verbose_name=_("获取状态"))
    trigger_reason = models.CharField(
        max_length=256, verbose_name=_("触发原因"), help_text=_("如:token_expired, no_token, manual_trigger")
    )
    attempt_count = models.IntegerField(default=1, verbose_name=_("尝试次数"))
    total_duration = models.FloatField(null=True, blank=True, verbose_name=_("总耗时(秒)"))
    login_duration = models.FloatField(null=True, blank=True, verbose_name=_("登录耗时(秒)"))
    captcha_attempts = models.IntegerField(default=0, verbose_name=_("验证码尝试次数"))
    network_retries = models.IntegerField(default=0, verbose_name=_("网络重试次数"))
    token_preview = models.CharField(
        max_length=50, null=True, blank=True, verbose_name=_("Token预览"), help_text=_("Token的前50个字符")
    )
    token_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name=_("Token指纹"),
        help_text=_("Token的SHA256指纹(用于排查重复/归因,不可反推Token)"),
    )
    token_redacted = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        verbose_name=_("Token脱敏摘要"),
        help_text=_("脱敏后的Token摘要(仅用于人工排查)"),
    )
    error_message = models.TextField(null=True, blank=True, verbose_name=_("错误信息"))
    error_details = models.JSONField(
        null=True, blank=True, verbose_name=_("详细错误信息"), help_text=_("包含完整的错误堆栈和上下文")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("Token获取历史")
        verbose_name_plural = _("Token获取历史")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["site_name", "-created_at"]),
            models.Index(fields=["account", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.site_name} - {self.account} - {self.get_status_display()}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """保存前对敏感字段进行脱敏处理"""
        from apps.core.security.scrub import fingerprint_sha256, mask_secret, scrub_obj, scrub_text

        if self.token_preview:
            raw = self.token_preview
            self.token_fingerprint = fingerprint_sha256(raw)
            self.token_redacted = mask_secret(raw)
            self.token_preview = None

        if self.error_message:
            self.error_message = scrub_text(self.error_message)

        if self.error_details:
            self.error_details = scrub_obj(self.error_details)

        super().save(*args, **kwargs)

    def get_success_rate_display(self) -> str:
        """获取成功率显示"""
        if self.status == TokenAcquisitionStatus.SUCCESS:
            return "100%"
        return "0%"
