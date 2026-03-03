"""
模板匹配与推荐服务

根据案件关联的机构名称查询和推荐可用外部模板，
支持按机构名称（含上级法院回退）筛选。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Count, QuerySet

logger: logging.Logger = logging.getLogger(__name__)


class MatchingService:
    """模板匹配与推荐"""

    def match_by_case(self, case_id: int, law_firm_id: int) -> list[Any]:
        """根据案件审理机构名称查询可用模板。"""
        from apps.cases.models import Case

        try:
            case: Case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            logger.warning("案件不存在: case_id=%d", case_id)
            return []

        source_name: str | None = self._get_source_name_from_case(case)
        if source_name:
            return self.match_by_source_name(source_name, law_firm_id)

        logger.info("案件无关联机构: case_id=%d", case_id)
        return []

    def match_by_source_name(self, source_name: str, law_firm_id: int) -> list[Any]:
        """
        按来源机构名称查询模板。
        精确匹配优先，无结果时尝试上级法院回退。
        """
        from apps.documents.models.external_template import ExternalTemplate

        templates: QuerySet[ExternalTemplate] = ExternalTemplate.objects.filter(
            source_name=source_name,
            law_firm_id=law_firm_id,
            is_active=True,
        ).order_by("-updated_at")

        if not templates.exists():
            from apps.core.models.court import Court

            court: Court | None = Court.objects.filter(name=source_name, is_active=True).first()
            if court and court.parent_id:
                parent: Court | None = Court.objects.filter(pk=court.parent_id).first()
                if parent:
                    logger.info("机构无模板，回退上级法院: %s -> %s", source_name, parent.name)
                    return self.match_by_source_name(parent.name, law_firm_id)

            logger.info("机构无模板: source_name=%s", source_name)
            return []

        return list(templates)

    def get_template_statistics(self, law_firm_id: int) -> dict[str, Any]:
        """模板统计"""
        from apps.documents.models.choices import TemplateStatus
        from apps.documents.models.external_template import ExternalTemplate

        base_qs: QuerySet[ExternalTemplate] = ExternalTemplate.objects.filter(
            law_firm_id=law_firm_id,
            is_active=True,
        )

        by_source: list[dict[str, Any]] = list(
            base_qs.exclude(source_name="").values("source_name").annotate(count=Count("id")).order_by("-count")
        )

        total: int = base_qs.count()
        confirmed_count: int = base_qs.filter(status=TemplateStatus.CONFIRMED).count()

        return {
            "total": total,
            "by_source": by_source,
            "confirmed": confirmed_count,
            "unconfirmed": total - confirmed_count,
        }

    def _get_source_name_from_case(self, case: Any) -> str | None:
        """从案件获取审理机构名称。"""
        from apps.cases.models.case import SupervisingAuthority

        authority: SupervisingAuthority | None = SupervisingAuthority.objects.filter(
            case=case,
            authority_type="trial",
        ).first()

        if authority and authority.name:
            return authority.name
        return None
