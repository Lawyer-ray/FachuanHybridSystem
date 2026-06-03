"""Cloud storage account model — manages credentials for local / WebDAV / OneDrive."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.security.secret_codec import SecretCodec


class CloudStorageAccount(models.Model):
    """A configured cloud storage account (Nutstore WebDAV, OneDrive, or local)."""

    id: int

    class StorageType(models.TextChoices):
        LOCAL = "local", _("本地文件系统")
        WEBDAV = "webdav", _("坚果云 WebDAV")
        ONEDRIVE = "onedrive", _("OneDrive")

    name = models.CharField(max_length=100, verbose_name=_("存储名称"), help_text=_("如：坚果云-工作空间"))
    storage_type = models.CharField(
        max_length=20, choices=StorageType.choices, default=StorageType.LOCAL, verbose_name=_("存储类型")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("启用"))

    # ── WebDAV fields ──────────────────────────────────────────
    webdav_url = models.URLField(
        blank=True,
        default="https://dav.jianguoyun.com/dav/",
        verbose_name=_("WebDAV 地址"),
    )
    webdav_username = models.CharField(max_length=255, blank=True, default="", verbose_name=_("WebDAV 用户名"))
    webdav_password = models.CharField(
        max_length=512, blank=True, default="", verbose_name=_("WebDAV 应用密码（加密存储）")
    )
    webdav_root_path = models.CharField(
        max_length=500, blank=True, default="/", verbose_name=_("WebDAV 根路径")
    )

    # ── OneDrive fields ────────────────────────────────────────
    onedrive_client_id = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Azure AD Client ID"))
    onedrive_tenant_id = models.CharField(
        max_length=255, blank=True, default="consumers", verbose_name=_("Azure AD Tenant ID")
    )
    onedrive_root_path = models.CharField(
        max_length=500, blank=True, default="/", verbose_name=_("OneDrive 根路径")
    )
    onedrive_access_token = models.TextField(blank=True, default="", verbose_name=_("OneDrive Access Token（加密）"))
    onedrive_refresh_token = models.TextField(blank=True, default="", verbose_name=_("OneDrive Refresh Token（加密）"))
    onedrive_token_expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Token 过期时间"))

    # ── Local fields ───────────────────────────────────────────
    local_root_path = models.CharField(max_length=1000, blank=True, default="/", verbose_name=_("本地根路径"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("云存储账号")
        verbose_name_plural = _("云存储账号")
        ordering = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["storage_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_storage_type_display()})"

    # ── Decrypted field accessors ──────────────────────────────

    def get_decrypted_webdav_password(self) -> str:
        return SecretCodec().try_decrypt(self.webdav_password)

    def get_decrypted_onedrive_access_token(self) -> str:
        return SecretCodec().try_decrypt(self.onedrive_access_token)

    def get_decrypted_onedrive_refresh_token(self) -> str:
        return SecretCodec().try_decrypt(self.onedrive_refresh_token)

    # ── Encryption helpers for admin ───────────────────────────

    def encrypt_sensitive_fields(self) -> None:
        """Encrypt plaintext sensitive fields before save. Idempotent."""
        codec = SecretCodec()
        if self.webdav_password and not codec.is_encrypted(self.webdav_password):
            self.webdav_password = codec.encrypt(self.webdav_password)
        if self.onedrive_access_token and not codec.is_encrypted(self.onedrive_access_token):
            self.onedrive_access_token = codec.encrypt(self.onedrive_access_token)
        if self.onedrive_refresh_token and not codec.is_encrypted(self.onedrive_refresh_token):
            self.onedrive_refresh_token = codec.encrypt(self.onedrive_refresh_token)

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.encrypt_sensitive_fields()
        super().save(*args, **kwargs)
