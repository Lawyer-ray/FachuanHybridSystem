"""Module for credential."""

from typing import ClassVar

from django.db import models

from apps.core.security.secret_codec import SecretCodec

from .lawyer import Lawyer

_codec = SecretCodec()


class AccountCredential(models.Model):
    """账号凭证模型，存储律师在外部系统的登录凭证。"""

    id: int
    lawyer_id: int  # 外键ID字段
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name="credentials", verbose_name="律师")
    site_name = models.CharField(max_length=255, verbose_name="网站名称")
    url = models.URLField(blank=True, verbose_name="URL")
    account = models.CharField(max_length=255, verbose_name="账号")
    _password = models.CharField(max_length=512, verbose_name="密码", db_column="password")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    # 登录统计字段
    last_login_success_at = models.DateTimeField(null=True, blank=True, verbose_name="最后成功登录时间")
    login_success_count = models.PositiveIntegerField(default=0, verbose_name="成功登录次数")
    login_failure_count = models.PositiveIntegerField(default=0, verbose_name="失败登录次数")

    class Meta:
        verbose_name = "账号密码"
        verbose_name_plural = "账号密码"
        ordering: ClassVar = ["-last_login_success_at", "-login_success_count", "login_failure_count"]
        indexes: ClassVar = [
            models.Index(fields=["site_name", "-last_login_success_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.site_name} - {self.account}"

    @property
    def password(self) -> str:
        """解密并返回密码明文。"""
        raw = self._password or ""
        if _codec.is_encrypted(raw):
            return _codec.try_decrypt(raw)
        # 兼容旧的明文数据：返回原值（生产环境会解密失败时 raise）
        return raw

    @password.setter
    def password(self, value: str) -> None:
        """写入时自动加密。"""
        if value and not _codec.is_encrypted(value):
            self._password = _codec.encrypt(value)
        else:
            self._password = value

    @property
    def success_rate(self) -> float:
        """计算登录成功率"""
        total_attempts = self.login_success_count + self.login_failure_count
        if total_attempts == 0:
            return 0.0
        return self.login_success_count / total_attempts
