"""
Automation模块标准化日志工具类

提供结构化日志记录方法，确保所有日志都符合规范格式。
"""

from ._logging_api_mixin import ApiLoggingMixin
from ._logging_document_mixin import DocumentLoggingMixin
from ._logging_token_mixin import TokenLoggingMixin


class AutomationLogger(TokenLoggingMixin, DocumentLoggingMixin, ApiLoggingMixin):
    """Automation模块标准化日志工具类"""
