"""Module for credential."""

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .lawyer import Lawyer


class AccountCredential(models.Model):
    """账号凭证模型，存储律师在外部系统的登录凭证。"""

    id: int
    lawyer_id: int  # 外键ID字段
    lawyer = models.ForeignKey(Lawyer, on_delete=models.CASCADE, related_name="credentials", verbose_name=_("律师"))
    site_name = models.CharField(max_length=255, verbose_name=_("网站名称"))
    url = models.URLField(blank=True, verbose_name=_("URL"))
    account = models.CharField(max_length=255, verbose_name=_("账号"))
    password = models.CharField(max_length=255, verbose_name=_("密码"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    # 登录统计字段
    last_login_success_at = models.DateTimeField(null=True, blank=True, verbose_name=_("最后成功登录时间"))
    login_success_count = models.PositiveIntegerField(default=0, verbose_name=_("成功登录次数"))
    login_failure_count = models.PositiveIntegerField(default=0, verbose_name=_("失败登录次数"))
    is_preferred = models.BooleanField(default=False, verbose_name=_("是否优先使用"))

    class Meta:
        verbose_name = _("账号密码")
        verbose_name_plural = _("账号密码")
        ordering: ClassVar = ["-last_login_success_at", "-login_success_count", "login_failure_count"]
        indexes: ClassVar = [
            models.Index(fields=["site_name", "-last_login_success_at"]),
            models.Index(fields=["site_name", "is_preferred"]),
        ]

    def __str__(self) -> str:
        return f"{self.site_name} - {self.account}"

    @property
    def success_rate(self) -> float:
        """计算登录成功率"""
        total_attempts = self.login_success_count + self.login_failure_count
        if total_attempts == 0:
            return 0.0
        return self.login_success_count / total_attempts
