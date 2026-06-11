"""文档解析工具 Model（Admin 入口，不建表）"""

from django.db import models


class DocumentParsingTool(models.Model):
    """文档解析工具（仅用于 Django Admin 入口，不创建数据库表）"""

    class Meta:
        managed = False
        app_label = "document_parsing"
        verbose_name = "文档解析"
        verbose_name_plural = "文档解析"
