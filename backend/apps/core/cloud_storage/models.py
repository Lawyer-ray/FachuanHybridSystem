"""Cloud storage account model — manages credentials for local / WebDAV / OneDrive / S3 / Google Drive / Dropbox."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.security.secret_codec import SecretCodec


class CloudStorageAccount(models.Model):
    """A configured cloud storage account."""

    id: int

    class StorageType(models.TextChoices):
        LOCAL = "local", _("本地文件系统")
        WEBDAV = "webdav", _("WebDAV")
        ONEDRIVE = "onedrive", _("OneDrive")
        S3 = "s3", _("S3 兼容存储")
        GOOGLE_DRIVE = "google_drive", _("Google Drive")
        DROPBOX = "dropbox", _("Dropbox")

    name = models.CharField(max_length=100, verbose_name=_("存储名称"), help_text=_("如：坚果云、123云盘"))
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
    webdav_root_path = models.CharField(max_length=500, blank=True, default="/", verbose_name=_("WebDAV 根路径"))

    # ── OneDrive fields ────────────────────────────────────────
    onedrive_client_id = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Azure AD Client ID"))
    onedrive_tenant_id = models.CharField(
        max_length=255, blank=True, default="consumers", verbose_name=_("Azure AD Tenant ID")
    )
    onedrive_root_path = models.CharField(max_length=500, blank=True, default="/", verbose_name=_("OneDrive 根路径"))
    onedrive_access_token = models.TextField(blank=True, default="", verbose_name=_("OneDrive Access Token（加密）"))
    onedrive_refresh_token = models.TextField(blank=True, default="", verbose_name=_("OneDrive Refresh Token（加密）"))
    onedrive_token_expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Token 过期时间"))

    # ── S3 fields ───────────────────────────────────────────────
    s3_access_key_id = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Access Key ID"))
    s3_secret_access_key = models.CharField(
        max_length=512, blank=True, default="", verbose_name=_("Secret Access Key（加密存储）")
    )
    s3_bucket_name = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Bucket 名称"))
    s3_endpoint_url = models.URLField(
        blank=True, default="", verbose_name=_("Endpoint URL"), help_text=_("留空使用 AWS 默认；S3 兼容服务填对应地址")
    )
    s3_region = models.CharField(max_length=50, blank=True, default="us-east-1", verbose_name=_("Region"))
    s3_root_path = models.CharField(max_length=1000, blank=True, default="/", verbose_name=_("S3 根路径"))

    # ── Google Drive fields ──────────────────────────────────────
    gdrive_service_account_json = models.TextField(
        blank=True, default="", verbose_name=_("Service Account JSON（加密存储）")
    )
    gdrive_root_folder_id = models.CharField(max_length=255, blank=True, default="root", verbose_name=_("根文件夹 ID"))
    gdrive_root_path = models.CharField(max_length=1000, blank=True, default="/", verbose_name=_("Google Drive 根路径"))

    # ── Dropbox fields ──────────────────────────────────────────
    dropbox_app_key = models.CharField(max_length=255, blank=True, default="", verbose_name=_("App Key"))
    dropbox_app_secret = models.CharField(
        max_length=512, blank=True, default="", verbose_name=_("App Secret（加密存储）")
    )
    dropbox_access_token = models.TextField(blank=True, default="", verbose_name=_("Access Token（加密）"))
    dropbox_refresh_token = models.TextField(blank=True, default="", verbose_name=_("Refresh Token（加密）"))
    dropbox_token_expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Dropbox Token 过期时间"))
    dropbox_root_path = models.CharField(max_length=1000, blank=True, default="/", verbose_name=_("Dropbox 根路径"))

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

    def get_decrypted_s3_secret_access_key(self) -> str:
        return SecretCodec().try_decrypt(self.s3_secret_access_key)

    def get_decrypted_gdrive_service_account_json(self) -> str:
        return SecretCodec().try_decrypt(self.gdrive_service_account_json)

    def get_decrypted_dropbox_app_secret(self) -> str:
        return SecretCodec().try_decrypt(self.dropbox_app_secret)

    def get_decrypted_dropbox_access_token(self) -> str:
        return SecretCodec().try_decrypt(self.dropbox_access_token)

    def get_decrypted_dropbox_refresh_token(self) -> str:
        return SecretCodec().try_decrypt(self.dropbox_refresh_token)

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
        if self.s3_secret_access_key and not codec.is_encrypted(self.s3_secret_access_key):
            self.s3_secret_access_key = codec.encrypt(self.s3_secret_access_key)
        if self.gdrive_service_account_json and not codec.is_encrypted(self.gdrive_service_account_json):
            self.gdrive_service_account_json = codec.encrypt(self.gdrive_service_account_json)
        if self.dropbox_app_secret and not codec.is_encrypted(self.dropbox_app_secret):
            self.dropbox_app_secret = codec.encrypt(self.dropbox_app_secret)
        if self.dropbox_access_token and not codec.is_encrypted(self.dropbox_access_token):
            self.dropbox_access_token = codec.encrypt(self.dropbox_access_token)
        if self.dropbox_refresh_token and not codec.is_encrypted(self.dropbox_refresh_token):
            self.dropbox_refresh_token = codec.encrypt(self.dropbox_refresh_token)

    STORAGE_TYPE_NAMES: ClassVar = {
        "local": "本地文件系统",
        "webdav": "WebDAV",
        "onedrive": "OneDrive",
        "s3": "S3 兼容存储",
        "google_drive": "Google Drive",
        "dropbox": "Dropbox",
    }

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self.name:
            self.name = self.STORAGE_TYPE_NAMES.get(self.storage_type, self.get_storage_type_display())
        self.encrypt_sensitive_fields()
        super().save(*args, **kwargs)
