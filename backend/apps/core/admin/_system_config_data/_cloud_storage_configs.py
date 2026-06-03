"""坚果云 WebDAV 云存储配置"""

from typing import Any


def get_cloud_storage_configs() -> list[dict[str, Any]]:
    """获取坚果云 WebDAV 配置项（仅需用户名和应用密码）"""
    return [
        {
            "key": "NUTSTORE_WEBDAV_USERNAME",
            "category": "general",
            "description": "坚果云登录邮箱（用于 WebDAV 认证）",
            "value": "",
        },
        {
            "key": "NUTSTORE_WEBDAV_PASSWORD",
            "category": "general",
            "description": "坚果云应用密码（在坚果云网页端 → 账户信息 → 安全选项 → 第三方应用管理 → 添加应用密码 生成）",
            "value": "",
            "is_secret": True,
        },
    ]

