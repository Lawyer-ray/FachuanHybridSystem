"""Business logic services."""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import CaseSearchResultDTO, ICaseSearchService


class CaseSearchServiceAdapter(ICaseSearchService):
    """
    案件搜索服务适配器

    实现跨模块接口,封装案件搜索逻辑.
    """

    def search_cases(self, query: str, limit: int = 20) -> list[CaseSearchResultDTO]:
        """
        搜索案件

        支持按案件名称、案号、当事人搜索.

            query: 搜索关键词(案件名称、案号、当事人)
            limit: 返回结果数量限制,默认20

            匹配的案件搜索结果 DTO 列表
        """
        from django.db.models import Q

        from apps.cases.models import Case, CaseNumber, CaseParty

        # 限制返回数量
        limit = min(limit, 20)

        if not query or not query.strip():
            # 无搜索词时返回最近的案件
            cases = (
                Case.objects.select_related()
                .prefetch_related("case_numbers", "parties__client")
                .order_by("-id")[:limit]
            )
        else:
            search_term = query.strip()

            # 构建搜索条件:案件名称、案号、当事人
            # 1. 按案件名称搜索
            name_query = Q(name__icontains=search_term)

            # 2. 按案号搜索
            case_ids_by_number = CaseNumber.objects.filter(number__icontains=search_term).values_list(
                "case_id", flat=True
            )

            # 3. 按当事人搜索
            case_ids_by_party = CaseParty.objects.filter(client__name__icontains=search_term).values_list(
                "case_id", flat=True
            )

            # 合并查询
            cases = (
                Case.objects.filter(name_query | Q(id__in=case_ids_by_number) | Q(id__in=case_ids_by_party))
                .select_related()
                .prefetch_related("case_numbers", "parties__client")
                .distinct()
                .order_by("-id")[:limit]
            )

        # 构建响应
        results: list[Any] = []
        for case in cases:
            case_numbers = [cn.number for cn in case.case_numbers.all()]
            parties = [p.client.name for p in case.parties.all() if p.client]

            results.append(
                CaseSearchResultDTO(
                    id=case.id,
                    name=case.name,
                    case_numbers=case_numbers,
                    parties=parties,
                    created_at=case.start_date.isoformat() if case.start_date else None,
                )
            )

        return results
