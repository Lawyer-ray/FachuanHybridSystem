"""通用、数据库、Redis、文件存储、日志、通知等配置数据"""

from typing import Any

__all__ = ["get_general_configs"]


def get_general_configs() -> list[dict[str, Any]]:
    """获取通用配置项"""
    return [
        # ============ 系统信息配置 ============
        {
            "key": "SITE_NAME",
            "category": "general",
            "description": "系统名称（显示在后台标题）",
            "value": "法律案件管理系统",
            "is_secret": False,
        },
        {
            "key": "SITE_HEADER",
            "category": "general",
            "description": "后台页面标题",
            "value": "案件管理后台",
            "is_secret": False,
        },
        {"key": "COMPANY_NAME", "category": "general", "description": "公司/律所名称", "value": "", "is_secret": False},
        {
            "key": "ADMIN_EMAIL",
            "category": "general",
            "description": "管理员邮箱（用于系统通知）",
            "value": "",
            "is_secret": False,
        },
        # ============ 文件存储配置 ============
        {
            "key": "FILE_STORAGE_BACKEND",
            "category": "general",
            "description": "文件存储后端（local/s3/oss）",
            "value": "local",
            "is_secret": False,
        },
        {
            "key": "FILE_UPLOAD_MAX_SIZE",
            "category": "general",
            "description": "文件上传最大大小（MB）",
            "value": "50",
            "is_secret": False,
        },
        {
            "key": "FILE_ALLOWED_EXTENSIONS",
            "category": "general",
            "description": "允许上传的文件扩展名（逗号分隔）",
            "value": "pdf,doc,docx,xls,xlsx,jpg,jpeg,png,zip",
            "is_secret": False,
        },
        # ============ 通知配置 ============
        {
            "key": "NOTIFICATION_PROVIDER",
            "category": "general",
            "description": "默认通知渠道（feishu/dingtalk/wechat_work）",
            "value": "feishu",
            "is_secret": False,
        },
        {
            "key": "NOTIFICATION_ENABLED",
            "category": "general",
            "description": "启用系统通知",
            "value": "True",
            "is_secret": False,
        },
        # ============ 数据库配置 ============
        {
            "key": "DATABASE_POOL_SIZE",
            "category": "general",
            "description": "数据库连接池大小",
            "value": "10",
            "is_secret": False,
        },
        # ============ Redis 配置 ============
        {
            "key": "CACHE_TTL_DEFAULT",
            "category": "general",
            "description": "默认缓存过期时间（秒）",
            "value": "300",
            "is_secret": False,
        },
    ]
