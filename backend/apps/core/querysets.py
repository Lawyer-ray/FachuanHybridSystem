"""
QuerySet 预加载管理器

为核心 Model 提供带预加载配置的查询集工厂方法，
消除各 Service 中重复的 select_related/prefetch_related 定义。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db.models import QuerySet


class CaseQuerySetManager:
    """案件查询集管理器"""

    SELECT_RELATED: tuple[str, ...] = ("contract",)
    PREFETCH_RELATED: tuple[str, ...] = (
        "parties__client",
        "assignments__lawyer",
        "assignments__lawyer__law_firm",
        "logs__attachments",
        "case_numbers",
        "supervising_authorities",
        "contract__supplementary_agreements__parties__client",
    )

    @classmethod
    def with_standard_prefetch(cls) -> QuerySet[Any, Any]:
        """返回带标准预加载的查询集"""
        from apps.cases.models import Case

        return Case.objects.select_related(*cls.SELECT_RELATED).prefetch_related(*cls.PREFETCH_RELATED)

    @classmethod
    def with_extra_prefetch(cls, *extra: str) -> QuerySet[Any, Any]:
        """返回带额外预加载的查询集"""
        return cls.with_standard_prefetch().prefetch_related(*extra)


class ContractQuerySetManager:
    """合同查询集管理器"""

    PREFETCH_RELATED: tuple[str, ...] = (
        "cases",
        "contract_parties__client",
        "payments",
        "reminders",
        "assignments__lawyer",
        "assignments__lawyer__law_firm",
    )

    @classmethod
    def with_standard_prefetch(cls) -> QuerySet[Any, Any]:
        """返回带标准预加载的查询集"""
        from apps.contracts.models import Contract

        return Contract.objects.prefetch_related(*cls.PREFETCH_RELATED)

    @classmethod
    def with_extra_prefetch(cls, *extra: str) -> QuerySet[Any, Any]:
        """返回带额外预加载的查询集"""
        return cls.with_standard_prefetch().prefetch_related(*extra)
