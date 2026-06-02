"""格式调整 Proxy Model

用于在 Django admin 中创建独立的格式调整菜单入口
"""

from django.db import models

from .review_task import ReviewTask


class FormatNormalize(ReviewTask):
    """格式调整（代理模型，不创建数据库表）"""

    class Meta:
        proxy = True
        verbose_name = "格式调整"
        verbose_name_plural = "格式调整"
        app_label = "contract_review"
        ordering = ["-created_at"]
