"""文档解析 API"""

from apps.document_parsing.api.parsing_api import router
from apps.document_parsing.api.webhook_api import router as webhook_router

__all__ = ["router", "webhook_router"]
