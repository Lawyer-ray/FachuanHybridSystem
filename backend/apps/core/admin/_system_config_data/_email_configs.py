"""邮件服务配置"""

from typing import Any


def get_email_configs() -> list[dict[str, Any]]:
    """获取邮件服务配置项"""
    return [
        {
            "key": "EMAIL_HOST",
            "category": "email",
            "description": "SMTP 服务器地址（如 smtp.qq.com, smtp.gmail.com）",
            "value": "",
        },
        {
            "key": "EMAIL_PORT",
            "category": "email",
            "description": "SMTP 端口（通常为 465 或 587）",
            "value": "465",
        },
        {
            "key": "EMAIL_USE_SSL",
            "category": "email",
            "description": "是否使用 SSL 加密（与 TLS 二选一）",
            "value": "true",
        },
        {
            "key": "EMAIL_USE_TLS",
            "category": "email",
            "description": "是否使用 TLS 加密（与 SSL 二选一）",
            "value": "false",
        },
        {
            "key": "EMAIL_HOST_USER",
            "category": "email",
            "description": "发件人邮箱地址",
            "value": "",
        },
        {
            "key": "EMAIL_HOST_PASSWORD",
            "category": "email",
            "description": "邮箱密码或授权码",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "EMAIL_FROM_NAME",
            "category": "email",
            "description": "发件人显示名称",
            "value": "法穿AI系统",
        },
        {
            "key": "EMAIL_SUBJECT_PREFIX",
            "category": "email",
            "description": "邮件主题前缀",
            "value": "[法穿AI]",
        },
    ]
