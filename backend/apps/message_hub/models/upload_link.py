"""ClientUploadLink — 客户材料上传链接。

律师生成的一次性收取链接：token 即凭证（高熵随机、库存哈希、可过期可撤销），
外部客户在公开单页（/u/{token}）免登录上传，文件汇入收件箱材料预处理流水线。
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models


class UploadLinkStatus(models.TextChoices):
    ACTIVE = "active", "生效中"
    REVOKED = "revoked", "已作废"


class ClientUploadLink(models.Model):
    """客户材料上传链接（一对一发给客户，token 即访问凭证）。"""

    title = models.CharField(max_length=200, verbose_name="链接标题")
    note = models.TextField(blank=True, default="", verbose_name="给客户的说明")
    client_name = models.CharField(max_length=100, blank=True, default="", verbose_name="客户称呼")
    # token 明文只在创建/轮换响应中出现一次；库存 SHA-256，防拖库后撞出链接
    token_hash = models.CharField(max_length=64, unique=True, verbose_name="token SHA-256")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_upload_links",
        verbose_name="创建律师",
    )
    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_upload_links",
        verbose_name="绑定项目（委托合同）",
    )

    expires_at = models.DateTimeField(verbose_name="过期时间")
    status = models.CharField(
        max_length=16,
        choices=UploadLinkStatus.choices,
        default=UploadLinkStatus.ACTIVE,
        verbose_name="状态",
    )

    # 配额：防链接泄露后被无节制滥用（单批校验仍走 manual_upload 同一套白名单/上限）
    quota_total_bytes = models.BigIntegerField(default=2 * 1024 * 1024 * 1024, verbose_name="总字节配额")
    quota_max_packs = models.PositiveIntegerField(default=100, verbose_name="最大材料包数")
    used_bytes = models.BigIntegerField(default=0, verbose_name="已用字节")
    pack_count = models.PositiveIntegerField(default=0, verbose_name="已收材料包数")
    last_uploaded_at = models.DateTimeField(null=True, blank=True, verbose_name="最近上传时间")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "客户上传链接"
        verbose_name_plural = "客户上传链接"
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_status_display()}] {self.title}"
