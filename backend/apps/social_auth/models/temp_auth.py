"""临时授权码 — SPA OAuth 回调的安全中转机制。"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

TEMP_AUTH_EXPIRE_MINUTES = 5


class TempAuth(models.Model):
    """临时授权码，5 分钟过期，用完即删。"""

    token = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        verbose_name="用户",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "临时授权码"
        verbose_name_plural = "临时授权码"

    def __str__(self) -> str:
        return str(self.token)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.created_at + timezone.timedelta(minutes=TEMP_AUTH_EXPIRE_MINUTES)
