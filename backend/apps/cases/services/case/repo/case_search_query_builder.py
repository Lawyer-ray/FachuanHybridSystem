"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.cases.models import Case, CaseNumber
from apps.cases.utils import normalize_case_number


class CaseSearchQueryBuilder:
    def build_case_id_query_by_case_number(self, case_number: str) -> list[Any]:
        """按案号**精确等值匹配**查找案件 ID 列表。

        该方法服务于「案号精确匹配」链路（法院短信/文书识别自动绑定案件），
        必须与 CaseNumber.number 精确相等才命中，禁止 icontains 子串匹配：
        否则 `(2025)粤0605民初123号` 会误命中 `民初1234号`，短信文书/CaseLog/
        群通知会落到错误案件。

        匹配方式：将输入案号归一化后生成少量规范变体（全角/半角括号、
        带号/不带号），用 number__in 精确比对，可命中索引。

        宽松搜索（搜索框模糊查询）请走 build_case_search_queryset，保持 icontains。
        """
        if not case_number:
            return []

        variants = self.build_exact_match_variants(case_number)
        if not variants:
            return []

        return list(CaseNumber.objects.filter(number__in=variants).values_list("case_id", flat=True))

    def build_exact_match_variants(self, case_number: str) -> list[str]:
        """生成案号的精确匹配变体（归一化后带号/不带号、全角/半角括号）。"""
        normalized = normalize_case_number(case_number, ensure_hao=True)
        if not normalized:
            return []

        candidates = {normalized, normalized.rstrip("号")}
        # 兼容库中以半角括号存储的案号
        half_width = normalized.replace("（", "(").replace("）", ")")
        candidates.add(half_width)
        candidates.add(half_width.rstrip("号"))

        return sorted({v for v in candidates if v})

    def build_case_search_queryset(
        self, qs: QuerySet[Case, Case], query: str, status: str | None = None, limit: int = 30
    ) -> QuerySet[Case, Case]:
        if not query or not query.strip():
            return qs.none()

        query = query.strip()

        conditions = Q(name__icontains=query) | Q(parties__client__name__icontains=query)

        normalized = normalize_case_number(query)
        if normalized:
            search_term = normalized.rstrip("号")
            conditions |= Q(case_numbers__number__icontains=search_term)

        qs = qs.filter(conditions).distinct()
        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-start_date", "-id")[:limit]
