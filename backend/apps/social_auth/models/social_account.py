"""用户与社交平台的关联关系。"""

from __future__ import annotations

from typing import ClassVar

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
        # 一个平台身份只能属于一位律师：否则同一个飞书号会解析出两个律师
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["provider", "provider_uid"], name="uniq_social_account_provider_uid"),
            # 一位律师在每个平台只能绑一个账号。换绑 = 先解绑再绑，
            # 避免后台出现「这个律师怎么有两个飞书」而无法判断该用哪个登录。
            models.UniqueConstraint(fields=["user", "provider"], name="uniq_social_account_user_provider"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_uid} → {self.user}"
