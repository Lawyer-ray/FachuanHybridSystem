"""Business logic services."""

from __future__ import annotations


"""
证据文件存储

自定义存储类,保留中文文件名中的特殊字符(如括号)
"""

import os
import re

from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class EvidenceFileStorage(FileSystemStorage):
    """
    证据文件存储类

    保留中文文件名中的特殊字符(如括号),
    只移除真正危险的字符.
    """

    def get_valid_name(self, name: str) -> str:
        """
        重写文件名验证方法,保留中文括号等字符

        只移除以下危险字符:
        - 路径分隔符: / \
        - 空字符: \x00
        - 控制字符
        """
        # 获取文件名(不含路径)
        basename = os.path.basename(name)

        # 只移除真正危险的字符
        # 保留中文括号()、英文括号()、空格等
        dangerous_chars = r'[/\\:\*\?"<>\|\x00-\x1f]'
        clean_name = re.sub(dangerous_chars, "", basename)

        # 如果清理后为空,使用默认名称
        if not clean_name:
            clean_name = "unnamed"

        return clean_name


# 创建存储实例
evidence_file_storage = EvidenceFileStorage()
