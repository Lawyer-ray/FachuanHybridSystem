"""Module for contract review mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from .automation_mixin import _ServiceLocatorStub

if TYPE_CHECKING:
    from apps.core.protocols import IReviewService


class ContractReviewServiceLocatorMixin(_ServiceLocatorStub):
    """合同审查服务定位器 Mixin"""

    @classmethod
    def get_review_service(cls) -> IReviewService:
        """获取合同审查服务"""
        from apps.contract_review.services.wiring import get_review_service

        return cls.get_or_create("review_service", get_review_service)
