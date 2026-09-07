"""Initial state for CloudStorageAccount (moved from apps.core).

state-only：模型历史实际由 core/migrations 0007/0009/0010 建立并已在数据库执行。
本 migration 仅同步 Django 状态至新 app label，不做任何数据库操作；
表名已钉死为 core_cloudstorageaccount，零数据搬迁。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="CloudStorageAccount",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(help_text="如：坚果云、123云盘", max_length=100, verbose_name="存储名称")),
                        ("storage_type", models.CharField(choices=[("local", "本地文件系统"), ("webdav", "WebDAV"), ("onedrive", "OneDrive"), ("s3", "S3 兼容存储"), ("google_drive", "Google Drive"), ("dropbox", "Dropbox")], default="local", max_length=20, verbose_name="存储类型")),
                        ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                        ("webdav_url", models.URLField(blank=True, default="https://dav.jianguoyun.com/dav/", verbose_name="WebDAV 地址")),
                        ("webdav_username", models.CharField(blank=True, default="", max_length=255, verbose_name="WebDAV 用户名")),
                        ("webdav_password", models.CharField(blank=True, default="", max_length=512, verbose_name="WebDAV 应用密码（加密存储）")),
                        ("webdav_root_path", models.CharField(blank=True, default="/", max_length=500, verbose_name="WebDAV 根路径")),
                        ("onedrive_client_id", models.CharField(blank=True, default="", max_length=255, verbose_name="Azure AD Client ID")),
                        ("onedrive_tenant_id", models.CharField(blank=True, default="consumers", max_length=255, verbose_name="Azure AD Tenant ID")),
                        ("onedrive_root_path", models.CharField(blank=True, default="/", max_length=500, verbose_name="OneDrive 根路径")),
                        ("onedrive_access_token", models.TextField(blank=True, default="", verbose_name="OneDrive Access Token（加密）")),
                        ("onedrive_refresh_token", models.TextField(blank=True, default="", verbose_name="OneDrive Refresh Token（加密）")),
                        ("onedrive_token_expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Token 过期时间")),
                        ("onedrive_pending_device_code", models.TextField(blank=True, default="", help_text="授权流程中临时存储，进程重启后可恢复轮询", verbose_name="OneDrive 待轮询 Device Code")),
                        ("onedrive_pending_expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Device Code 过期时间")),
                        ("s3_access_key_id", models.CharField(blank=True, default="", max_length=255, verbose_name="Access Key ID")),
                        ("s3_secret_access_key", models.CharField(blank=True, default="", max_length=512, verbose_name="Secret Access Key（加密存储）")),
                        ("s3_bucket_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Bucket 名称")),
                        ("s3_endpoint_url", models.URLField(blank=True, default="", help_text="留空使用 AWS 默认；S3 兼容服务填对应地址", verbose_name="Endpoint URL")),
                        ("s3_region", models.CharField(blank=True, default="us-east-1", max_length=50, verbose_name="Region")),
                        ("s3_root_path", models.CharField(blank=True, default="/", max_length=1000, verbose_name="S3 根路径")),
                        ("gdrive_service_account_json", models.TextField(blank=True, default="", verbose_name="Service Account JSON（加密存储）")),
                        ("gdrive_root_folder_id", models.CharField(blank=True, default="root", max_length=255, verbose_name="根文件夹 ID")),
                        ("gdrive_root_path", models.CharField(blank=True, default="/", max_length=1000, verbose_name="Google Drive 根路径")),
                        ("dropbox_app_key", models.CharField(blank=True, default="", max_length=255, verbose_name="App Key")),
                        ("dropbox_app_secret", models.CharField(blank=True, default="", max_length=512, verbose_name="App Secret（加密存储）")),
                        ("dropbox_access_token", models.TextField(blank=True, default="", verbose_name="Access Token（加密）")),
                        ("dropbox_refresh_token", models.TextField(blank=True, default="", verbose_name="Refresh Token（加密）")),
                        ("dropbox_token_expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Dropbox Token 过期时间")),
                        ("dropbox_root_path", models.CharField(blank=True, default="/", max_length=1000, verbose_name="Dropbox 根路径")),
                        ("dropbox_pending_device_code", models.TextField(blank=True, default="", verbose_name="Dropbox 待轮询 Device Code")),
                        ("dropbox_pending_expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Dropbox Device Code 过期时间")),
                        ("local_root_path", models.CharField(blank=True, default="/", max_length=1000, verbose_name="本地根路径")),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                    ],
                    options={
                        "verbose_name": "云存储账号",
                        "verbose_name_plural": "云存储账号",
                        "db_table": "core_cloudstorageaccount",
                        "ordering": ["-created_at"],
                        "indexes": [
                            models.Index(fields=["storage_type"], name="core_clouds_storage_fe624d_idx"),
                            models.Index(fields=["is_active"], name="core_clouds_is_acti_2cfd68_idx"),
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
