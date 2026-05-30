"""智能填充 - proxy model 用于 Admin 注册"""

from apps.documents.models.document_template import DocumentTemplate


class SmartFillProxy(DocumentTemplate):
    """智能填充 - proxy model 用于 Admin 注册"""

    class Meta:
        proxy = True
        app_label = "documents"
        verbose_name = "智能填充"
        verbose_name_plural = "智能填充"
