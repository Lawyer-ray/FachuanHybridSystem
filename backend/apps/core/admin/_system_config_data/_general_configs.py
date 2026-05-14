"""通用、数据库、Redis、文件存储、日志、通知等配置数据"""

from typing import Any

__all__ = ["get_general_configs"]


def get_general_configs() -> list[dict[str, Any]]:
    """获取通用配置项"""
    return [
        {
            "key": "CASE_LOG_ATTACHMENT_AUTO_SUBDIR",
            "category": "general",
            "description": "案件日志附件自动创建子目录（true=上传附件时自动在案件文件夹下创建「案件日志附件」子目录；false=直接存入案件文件夹根目录）",
            "value": "true",
            "is_secret": False,
        },
    ]
