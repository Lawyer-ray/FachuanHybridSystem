"""合同审查模块服务依赖注入配置"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.protocols import IReviewService


def get_review_service() -> IReviewService:
    """获取合同审查服务实例"""
    from apps.contract_review.services.review_service import ReviewService

    return ReviewService()
