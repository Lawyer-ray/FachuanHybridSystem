"""Admin registration for CloudStorageAccount."""

from __future__ import annotations

import logging
import threading
import time as _time
from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils.html import format_html

from .models import CloudStorageAccount

logger = logging.getLogger(__name__)

# In-memory store for pending device code auth: {account_id: {"user_code": ..., "verification_uri": ..., ...}}
_pending_auth: dict[int, dict[str, Any]] = {}


def _poll_device_code(account_id: int, device_code: str, interval: int, max_attempts: int) -> None:
    """Background thread: poll Microsoft token endpoint until user authorizes or timeout."""
    import httpx

    from apps.core.security.secret_codec import SecretCodec

    from .models import CloudStorageAccount
    from .onedrive_provider import TOKEN_URL_TEMPLATE

    try:
        account = CloudStorageAccount.objects.get(id=account_id)
    except CloudStorageAccount.DoesNotExist:
        _pending_auth.pop(account_id, None)
        return

    tenant_id = getattr(account, "onedrive_tenant_id", None) or "consumers"
    client_id = getattr(account, "onedrive_client_id", "")
    token_url = TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)

    for attempt in range(max_attempts):
        _time.sleep(interval)
        try:
            resp = httpx.post(
                token_url,
                data={
                    "client_id": client_id,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                },
                timeout=30,
            )
            data = resp.json()

            if "access_token" in data:
                from datetime import UTC, datetime, timedelta

                codec = SecretCodec()
                # 重新获取最新的 account 对象，确保使用最新数据
                account = CloudStorageAccount.objects.select_for_update().get(id=account_id)
                account.onedrive_access_token = codec.encrypt(data["access_token"])
                account.onedrive_refresh_token = codec.encrypt(data.get("refresh_token", ""))
                account.onedrive_token_expires_at = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600))
                account.save(
                    update_fields=[
                        "onedrive_access_token",
                        "onedrive_refresh_token",
                        "onedrive_token_expires_at",
                        "updated_at",
                    ]
                )
                logger.info(f"OneDrive authorization successful for account {account_id}")
                _pending_auth.pop(account_id, None)
                return

            error = data.get("error", "")
            if error in ("authorization_declined", "expired_token"):
                _pending_auth.pop(account_id, None)
                return
            if error == "slow_down":
                interval += 5

        except CloudStorageAccount.DoesNotExist:
            logger.warning(f"CloudStorageAccount {account_id} no longer exists during OneDrive auth")
            _pending_auth.pop(account_id, None)
            return
        except Exception as e:
            logger.error(f"Error during OneDrive device code poll (attempt {attempt}): {e}")
            # 不退出，继续尝试

    logger.warning(f"OneDrive authorization timeout for account {account_id}")
    _pending_auth.pop(account_id, None)


def _poll_dropbox_device_code(account_id: int, device_code: str, interval: int, max_attempts: int) -> None:
    """Background thread: poll Dropbox token endpoint until user authorizes or timeout."""
    import httpx

    from apps.core.security.secret_codec import SecretCodec

    from .dropbox_provider import TOKEN_URL
    from .models import CloudStorageAccount

    try:
        account = CloudStorageAccount.objects.get(id=account_id)
    except CloudStorageAccount.DoesNotExist:
        _pending_auth.pop(account_id, None)
        return

    app_key = account.dropbox_app_key
    app_secret = account.get_decrypted_dropbox_app_secret()

    for _ in range(max_attempts):
        _time.sleep(interval)
        try:
            resp = httpx.post(
                TOKEN_URL,
                data={
                    "client_id": app_key,
                    "client_secret": app_secret,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                },
                timeout=30,
            )
            data = resp.json()

            if "access_token" in data:
                from datetime import UTC, datetime, timedelta

                codec = SecretCodec()
                account.dropbox_access_token = codec.encrypt(data["access_token"])
                account.dropbox_refresh_token = codec.encrypt(data.get("refresh_token", ""))
                account.dropbox_token_expires_at = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 14400))
                account.save(
                    update_fields=[
                        "dropbox_access_token",
                        "dropbox_refresh_token",
                        "dropbox_token_expires_at",
                        "updated_at",
                    ]
                )
                _pending_auth.pop(account_id, None)
                return

            error = data.get("error", "")
            if error in ("access_denied", "expired_token"):
                _pending_auth.pop(account_id, None)
                return
            if error == "slow_down":
                interval += 5

        except Exception:
            pass

    _pending_auth.pop(account_id, None)


@admin.register(CloudStorageAccount)
class CloudStorageAccountAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "storage_type",
        "is_active",
        "onedrive_status",
        "dropbox_status",
        "created_at",
    ]
    list_filter = ["storage_type", "is_active"]
    search_fields = ["name"]

    FIELDSETS = [
        ("基本信息", {"fields": ["storage_type", "is_active"]}),
        (
            "WebDAV 设置",
            {
                "fields": ["webdav_url", "webdav_username", "webdav_password", "webdav_root_path"],
                "classes": ["collapse", "webdav-section"],
            },
        ),
        (
            "OneDrive",
            {
                "fields": [
                    "onedrive_client_id",
                    "onedrive_tenant_id",
                    "onedrive_root_path",
                ],
                "classes": ["collapse", "onedrive-section"],
            },
        ),
        (
            "S3 兼容存储",
            {
                "fields": [
                    "s3_access_key_id",
                    "s3_secret_access_key",
                    "s3_bucket_name",
                    "s3_endpoint_url",
                    "s3_region",
                    "s3_root_path",
                ],
                "classes": ["collapse", "s3-section"],
            },
        ),
        (
            "Google Drive",
            {
                "fields": [
                    "gdrive_service_account_json",
                    "gdrive_root_folder_id",
                    "gdrive_root_path",
                ],
                "classes": ["collapse", "gdrive-section"],
            },
        ),
        (
            "Dropbox",
            {
                "fields": [
                    "dropbox_app_key",
                    "dropbox_app_secret",
                    "dropbox_root_path",
                ],
                "classes": ["collapse", "dropbox-section"],
            },
        ),
        (
            "本地文件系统",
            {
                "fields": ["local_root_path"],
                "classes": ["collapse", "local-section"],
            },
        ),
    ]

    fieldsets = FIELDSETS  # type: ignore[assignment]
    change_form_template = "admin/cloud_storage/change_form.html"

    class Media:
        js = ("admin/js/cloud_storage_admin.js",)

    def get_readonly_fields(self, request, obj=None):  # type: ignore[no-untyped-def]
        readonly = []
        if obj and obj.pk:
            readonly.append("storage_type")
        if obj and obj.storage_type == "onedrive":
            readonly.extend(["onedrive_token_expires_at", "onedrive_access_token", "onedrive_refresh_token"])
        if obj and obj.storage_type == "dropbox":
            readonly.extend(["dropbox_token_expires_at", "dropbox_access_token", "dropbox_refresh_token"])
        return readonly

    def get_urls(self):  # type: ignore[no-untyped-def]
        from django.urls import path

        custom_urls = [
            path(
                "<int:object_id>/onedrive-start/",
                self.admin_site.admin_view(self._start_auth_view),
                name="core_cloudstorageaccount_onedrive_start",
            ),
            path(
                "<int:object_id>/dropbox-start/",
                self.admin_site.admin_view(self._start_dropbox_auth_view),
                name="core_cloudstorageaccount_dropbox_start",
            ),
        ]
        return custom_urls + super().get_urls()

    def _start_auth_view(self, request: HttpRequest, object_id: int):  # type: ignore[no-untyped-def]
        """POST endpoint: start OneDrive device code flow and redirect back to change form."""
        from .onedrive_provider import OAuthTokenManager

        if request.method != "POST":
            return redirect("admin:core_cloudstorageaccount_change", object_id)

        try:
            account = self.model.objects.get(pk=object_id)
        except self.model.DoesNotExist:
            messages.error(request, "账号不存在")
            return redirect("admin:core_cloudstorageaccount_changelist")

        try:
            result = OAuthTokenManager.start_device_code_flow(account)

            _pending_auth[object_id] = {
                "user_code": result["user_code"],
                "verification_uri": result["verification_uri"],
            }

            thread = threading.Thread(
                target=_poll_device_code,
                args=(object_id, result["device_code"], result.get("interval", 5), 180),
                daemon=True,
            )
            thread.start()

            messages.success(
                request,
                format_html(
                    "设备码已生成！请在浏览器打开下方链接，输入设备码完成授权，授权后刷新此页面：<br><br>"
                    '验证地址：<a href="{url}" target="_blank">{url}</a><br>'
                    '设备码：<b style="font-size:18px; background:#f0f0f0; padding:4px 12px; border-radius:4px;">{code}</b>',
                    url=result["verification_uri"],
                    code=result["user_code"],
                ),
            )
        except Exception as e:
            messages.error(request, f"启动授权失败：{e}")

        return redirect("admin:core_cloudstorageaccount_change", object_id)

    def _start_dropbox_auth_view(self, request: HttpRequest, object_id: int):  # type: ignore[no-untyped-def]
        """POST endpoint: start Dropbox device code flow and redirect back to change form."""
        if request.method != "POST":
            return redirect("admin:core_cloudstorageaccount_change", object_id)

        try:
            account = self.model.objects.get(pk=object_id)
        except self.model.DoesNotExist:
            messages.error(request, "账号不存在")
            return redirect("admin:core_cloudstorageaccount_changelist")

        try:
            from .dropbox_provider import DropboxOAuthTokenManager

            result = DropboxOAuthTokenManager.start_device_code_flow(account)

            _pending_auth[object_id] = {
                "user_code": result["user_code"],
                "verification_uri": result["verification_uri"],
            }

            thread = threading.Thread(
                target=_poll_dropbox_device_code,
                args=(object_id, result["device_code"], result.get("interval", 5), 180),
                daemon=True,
            )
            thread.start()

            messages.success(
                request,
                format_html(
                    "设备码已生成！请在浏览器打开下方链接，输入设备码完成授权，授权后刷新此页面：<br><br>"
                    '验证地址：<a href="{url}" target="_blank">{url}</a><br>'
                    '设备码：<b style="font-size:18px; background:#f0f0f0; padding:4px 12px; border-radius:4px;">{code}</b>',
                    url=result["verification_uri"],
                    code=result["user_code"],
                ),
            )
        except Exception as e:
            messages.error(request, f"启动授权失败：{e}")

        return redirect("admin:core_cloudstorageaccount_change", object_id)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):  # type: ignore[no-untyped-def]
        extra_context = extra_context or {}

        if object_id:
            try:
                obj = self.model.objects.get(pk=object_id)
                is_onedrive = obj.storage_type == "onedrive"
                is_dropbox = obj.storage_type == "dropbox"

                extra_context["show_onedrive_auth"] = is_onedrive
                extra_context["onedrive_account_id"] = object_id
                extra_context["onedrive_pending"] = is_onedrive and object_id in _pending_auth
                extra_context["onedrive_authorized"] = is_onedrive and bool(obj.onedrive_refresh_token)
                if is_onedrive and object_id in _pending_auth:
                    pending = _pending_auth[object_id]
                    extra_context["onedrive_device_code"] = pending.get("user_code", "")
                    extra_context["onedrive_verification_uri"] = pending.get("verification_uri", "")

                extra_context["show_dropbox_auth"] = is_dropbox
                extra_context["dropbox_account_id"] = object_id
                extra_context["dropbox_pending"] = is_dropbox and object_id in _pending_auth
                extra_context["dropbox_authorized"] = is_dropbox and bool(obj.dropbox_refresh_token)
                if is_dropbox and object_id in _pending_auth:
                    pending = _pending_auth[object_id]
                    extra_context["dropbox_device_code"] = pending.get("user_code", "")
                    extra_context["dropbox_verification_uri"] = pending.get("verification_uri", "")
            except Exception:
                pass

        return super().changeform_view(request, object_id, form_url, extra_context)

    def onedrive_status(self, obj):  # type: ignore[no-untyped-def]
        if obj.storage_type != "onedrive":
            return "-"
        if obj.onedrive_refresh_token:
            return format_html('<span style="color:green">{}</span>', "已授权")
        return format_html('<span style="color:red">{}</span>', "未授权")

    onedrive_status.short_description = "OneDrive 状态"  # type: ignore[attr-defined]

    def dropbox_status(self, obj):  # type: ignore[no-untyped-def]
        if obj.storage_type != "dropbox":
            return "-"
        if obj.dropbox_refresh_token:
            return format_html('<span style="color:green">{}</span>', "已授权")
        return format_html('<span style="color:red">{}</span>', "未授权")

    dropbox_status.short_description = "Dropbox 状态"  # type: ignore[attr-defined]
