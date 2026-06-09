"""用户与社交平台的关联关系。"""

from __future__ import annotations

from django.db import models


class SocialAccount(models.Model):
    """一个用户可关联多个 Provider，一个 Provider 身份只对应一个用户。"""

    id: int
    user = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="social_accounts",
        verbose_name="用户",
    )
    provider = models.CharField(max_length=50, verbose_name="平台")
    provider_uid = models.CharField(max_length=255, verbose_name="平台用户ID")
    display_name = models.CharField(max_length=255, blank=True, default="", verbose_name="平台昵称")
    avatar_url = models.URLField(max_length=500, blank=True, default="", verbose_name="平台头像")
    raw_profile = models.JSONField(default=dict, verbose_name="原始数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "社交账号"
        verbose_name_plural = "社交账号"
        unique_together = [("provider", "provider_uid")]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_uid} → {self.user}"
