"""客户回款服务工厂函数。

本模块是 `ClientPaymentImageService` / `ClientPaymentRecordService` 的唯一装配入口，
admin 层的 `get_client_payment_*_service()` 只路由到这里，不再裸构造 Service。
"""

from __future__ import annotations

from .client_payment_image_service import ClientPaymentImageService
from .client_payment_service import ClientPaymentRecordService


def build_client_payment_image_service() -> ClientPaymentImageService:
    """构建回款凭证图片服务实例（无状态，可安全缓存）。"""
    return ClientPaymentImageService()


def build_client_payment_record_service() -> ClientPaymentRecordService:
    """构建回款记录服务实例，显式注入图片服务（与 `__init__` 内部兜底同类同参）。"""
    return ClientPaymentRecordService(image_service=build_client_payment_image_service())
