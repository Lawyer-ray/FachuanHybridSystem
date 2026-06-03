"""云存储配置（坚果云 WebDAV + OneDrive）"""

from typing import Any


def get_cloud_storage_configs() -> list[dict[str, Any]]:
    """获取云存储配置项"""
    return [
        # ── 坚果云 WebDAV ─────────────────────────────────────
        {
            "key": "NUTSTORE_WEBDAV_USERNAME",
            "category": "cloud_storage",
            "description": "坚果云登录邮箱（用于 WebDAV 认证）",
            "value": "",
        },
        {
            "key": "NUTSTORE_WEBDAV_PASSWORD",
            "category": "cloud_storage",
            "description": "坚果云应用密码（在坚果云网页端 → 账户信息 → 安全选项 → 第三方应用管理 → 添加应用密码 生成）",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "NUTSTORE_WEBDAV_ROOT_PATH",
            "category": "cloud_storage",
            "description": "坚果云 WebDAV 根路径（默认为 / ，可指定子目录如 /我的坚果云/工作文件）",
            "value": "/",
        },
        # ── OneDrive ──────────────────────────────────────────
        {
            "key": "ONEDRIVE_CLIENT_ID",
            "category": "cloud_storage",
            "description": "Azure AD 应用程序(client) ID（在 Azure Portal → 应用注册 中获取）",
            "value": "",
        },
        {
            "key": "ONEDRIVE_TENANT_ID",
            "category": "cloud_storage",
            "description": "Azure AD 目录(tenant) ID（个人账号用 consumers，企业账号填实际 tenant ID）",
            "value": "consumers",
        },
        {
            "key": "ONEDRIVE_ROOT_PATH",
            "category": "cloud_storage",
            "description": "OneDrive 根路径（默认为 / ，可指定子目录如 /工作文件）",
            "value": "/",
        },
    ]
