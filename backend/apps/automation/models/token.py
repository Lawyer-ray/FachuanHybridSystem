"""Token 管理相关模型"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from django_lifecycle import BEFORE_CREATE, BEFORE_UPDATE, LifecycleModel, hook

class CourtToken(models.Model):
    """人民法院在线服务网（一张网）/保全系统 Token 存储"""

    id: int
    site_name: models.CharField = models.CharField(
        max_length=128,
        verbose_name="站点标识",
        help_text="如:court_zxfw（人民法院在线服务网/一张网）, court_baoquan（保全系统）",
    )
    account: models.CharField = models.CharField(max_length=128, verbose_name="登录账号")
    token: models.TextField = models.TextField(
        verbose_name="认证Token", help_text="一张网/保全系统返回的 JWT Token 或其他认证令牌"
    )
    token_type: models.CharField = models.CharField(
        max_length=32, default="Bearer", verbose_name="Token类型", help_text="如:Bearer, JWT"
    )
    expires_at: models.DateTimeField = models.DateTimeField(verbose_name="过期时间")
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        app_label = "automation"
        verbose_name = "一张网Token管理"
        verbose_name_plural = "一张网Token管理"
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

        result: bool = self.expires_at <= timezone.now()
        return result

class TokenAcquisitionStatus(models.TextChoices):
    """一张网/保全系统 Token 获取状态"""

    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"
    TIMEOUT = "timeout", "超时"
    NETWORK_ERROR = "network_error", "网络错误"
    CAPTCHA_ERROR = "captcha_error", "验证码错误"
    CREDENTIAL_ERROR = "credential_error", "账号密码错误"

class TokenAcquisitionHistory(LifecycleModel):
    """一张网/保全系统 Token 获取历史记录"""

    id: int
    site_name: models.CharField = models.CharField(
        max_length=128,
        verbose_name="站点标识",
        help_text="如:court_zxfw（人民法院在线服务网/一张网）, court_baoquan（保全系统）",
    )
    account: models.CharField = models.CharField(max_length=128, verbose_name="使用账号")
    credential_id: models.IntegerField = models.IntegerField(
        null=True, blank=True, verbose_name="凭证ID", help_text="关联的AccountCredential ID"
    )
    status: models.CharField = models.CharField(
        max_length=32, choices=TokenAcquisitionStatus.choices, verbose_name="获取状态"
    )
    trigger_reason: models.CharField = models.CharField(
        max_length=256, verbose_name="触发原因", help_text="如:token_expired, no_token, manual_trigger"
    )
    attempt_count: models.IntegerField = models.IntegerField(default=1, verbose_name="尝试次数")
    total_duration: models.FloatField = models.FloatField(null=True, blank=True, verbose_name="总耗时(秒)")
    login_duration: models.FloatField = models.FloatField(null=True, blank=True, verbose_name="登录耗时(秒)")
    captcha_attempts: models.IntegerField = models.IntegerField(default=0, verbose_name="验证码尝试次数")
    network_retries: models.IntegerField = models.IntegerField(default=0, verbose_name="网络重试次数")
    token_preview: models.CharField = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="Token预览", help_text="Token 前50个字符"
    )
    token_fingerprint: models.CharField = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name="Token指纹",
        help_text="Token的SHA256指纹(用于排查重复/归因,不可反推Token)",
    )
    token_redacted: models.CharField = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        verbose_name="Token脱敏摘要",
        help_text="脱敏后的Token摘要(仅用于人工排查)",
    )
    error_message: models.TextField = models.TextField(null=True, blank=True, verbose_name="错误信息")
    error_details: models.JSONField = models.JSONField(
        null=True, blank=True, verbose_name="详细错误信息", help_text="包含完整的错误堆栈和上下文"
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")

    class Meta:
        app_label = "automation"
        verbose_name = "一张网/保全Token获取历史"
        verbose_name_plural = "一张网/保全Token获取历史"
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

    @hook(BEFORE_CREATE)
    @hook(BEFORE_UPDATE)
    def on_save_scrub_sensitive_fields(self) -> None:
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

    def get_success_rate_display(self) -> str:
        """获取成功率显示"""
        if self.status == TokenAcquisitionStatus.SUCCESS:
            return "100%"
        return "0%"
