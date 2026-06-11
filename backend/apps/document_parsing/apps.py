from django.apps import AppConfig


class DocumentParsingConfig(AppConfig):
    """文档解析服务配置"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.document_parsing"
    verbose_name = "文档解析服务"
    verbose_name_plural = "文档解析服务"

    def ready(self) -> None:
        """应用启动时初始化"""
        pass
