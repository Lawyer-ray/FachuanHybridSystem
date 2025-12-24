# -*- coding: utf-8 -*-
"""
Document Delivery Coordinator 模块

协调文书送达查询的主入口，负责选择查询策略（API 优先，Playwright 降级）。
"""
from .document_delivery_coordinator import DocumentDeliveryCoordinator

__all__ = ["DocumentDeliveryCoordinator"]
