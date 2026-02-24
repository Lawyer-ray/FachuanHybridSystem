"""通用、数据库、Redis、文件存储、日志、通知等配置数据"""

from typing import Any

__all__ = ["get_general_configs"]


def get_general_configs() -> list[dict[str, Any]]:
    """获取通用配置项"""
    return [
        # ============ 公司信息配置（可选） ============
        {"key": "COMPANY_NAME", "category": "general", "description": "公司/律所名称", "value": "", "is_secret": False},
        {
            "key": "ADMIN_EMAIL",
            "category": "general",
            "description": "管理员邮箱（用于系统通知）",
            "value": "",
            "is_secret": False,
        },
    ]
