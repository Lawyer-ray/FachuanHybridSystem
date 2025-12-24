"""
文书送达 Admin 模块
"""

from .document_delivery_schedule_admin import DocumentDeliveryScheduleAdmin
from .document_query_history_admin import DocumentQueryHistoryAdmin

__all__ = [
    'DocumentDeliveryScheduleAdmin',
    'DocumentQueryHistoryAdmin',
]