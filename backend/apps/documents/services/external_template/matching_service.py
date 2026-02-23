"""
法院/机构模板匹配与推荐服务

根据案件关联的法院或机构查询和推荐可用外部模板，
支持按法院（含上级法院回退）、机构名称、来源类型筛选，
按 TemplateCategory 分组展示。

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.3, 8.4, 13.5, 13.6
"""

from __future__ import annotations

import collections
import logging
from typing import Any

from django.db.models import Count, QuerySet

logger: logging.Logger = logging.getLogger(__name__)


class MatchingService:
    """法院/机构模板匹配与推荐"""

    # ------------------------------------------------------------------
    # 按案件匹配
    # ------------------------------------------------------------------

    def match_by_case(
        self, case_id: int, law_firm_id: int
    ) -> dict[str, list[Any]]:
        """
        根据案件关联法院查询可用模板。

        1. 获取案件的审理机构（SupervisingAuthority, authority_type=trial）
        2. 通过机构名称匹配 Court 记录
        3. 若有法院：调用 match_by_court
        4. 若无法院：返回空 dict

        Requirements: 7.1, 7.2
        """
        from apps.cases.models import Case

        try:
            case: Case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            logger.warning("案件不存在: case_id=%d", case_id)
            return {}

        # Case 没有直接的 court FK，通过 SupervisingAuthority 查找审理机构
        court_id: int | None = self._get_court_id_from_case(case)

        if court_id is not None:
            return self.match_by_court(court_id, law_firm_id)

        logger.info(
            "案件无关联法院: case_id=%d, 返回空结果",
            case_id,
        )
        return {}

    # ------------------------------------------------------------------
    # 按法院匹配
    # ------------------------------------------------------------------

    def match_by_court(
        self, court_id: int, law_firm_id: int
    ) -> dict[str, list[Any]]:
        """
        按法院查询模板，含上级法院回退。

        1. 查询 court_id + law_firm_id + is_active=True 的模板
        2. 若无结果，尝试 parent court
        3. 按 TemplateCategory 分组
        4. 每组内 is_confirmed=True 优先，然后按 -updated_at 排序

        Requirements: 7.1, 7.2, 7.4, 7.5
        """
        from apps.documents.models.external_template import ExternalTemplate

        templates: QuerySet[ExternalTemplate] = ExternalTemplate.objects.filter(
            court_id=court_id,
            law_firm_id=law_firm_id,
            is_active=True,
        ).order_by("-is_active")

        if not templates.exists():
            # 尝试上级法院
            from apps.core.models.court import Court

            try:
                court: Court = Court.objects.get(pk=court_id)
            except Court.DoesNotExist:
                logger.warning("法院不存在: court_id=%d", court_id)
                return {}

            if court.parent_id:
                logger.info(
                    "法院无模板，回退到上级法院: court_id=%d, parent_id=%d",
                    court_id,
                    court.parent_id,
                )
                return self.match_by_court(court.parent_id, law_firm_id)

            logger.info(
                "法院及上级法院均无模板: court_id=%d",
                court_id,
            )
            return {}

        return self._group_by_category(templates)

    # ------------------------------------------------------------------
    # 按机构名称匹配
    # ------------------------------------------------------------------

    def match_by_organization(
        self, organization_name: str, law_firm_id: int
    ) -> dict[str, list[Any]]:
        """
        按机构名称模糊匹配查询模板。

        Requirements: 7.3, 7.4
        """
        from apps.documents.models.external_template import ExternalTemplate

        templates: QuerySet[ExternalTemplate] = ExternalTemplate.objects.filter(
            organization_name__icontains=organization_name,
            law_firm_id=law_firm_id,
            is_active=True,
        )

        logger.info(
            "机构名称匹配: name=%s, law_firm_id=%d, count=%d",
            organization_name,
            law_firm_id,
            templates.count(),
        )
        return self._group_by_category(templates)

    # ------------------------------------------------------------------
    # 按来源类型匹配
    # ------------------------------------------------------------------

    def match_by_source_type(
        self, source_type: str, law_firm_id: int
    ) -> dict[str, list[Any]]:
        """
        按来源类型筛选模板。

        Requirements: 13.5, 13.6
        """
        from apps.documents.models.external_template import ExternalTemplate

        templates: QuerySet[ExternalTemplate] = ExternalTemplate.objects.filter(
            source_type=source_type,
            law_firm_id=law_firm_id,
            is_active=True,
        )

        logger.info(
            "来源类型匹配: source_type=%s, law_firm_id=%d, count=%d",
            source_type,
            law_firm_id,
            templates.count(),
        )
        return self._group_by_category(templates)

    # ------------------------------------------------------------------
    # 模板统计
    # ------------------------------------------------------------------

    def get_template_statistics(
        self, law_firm_id: int
    ) -> dict[str, Any]:
        """
        模板统计：
        - 按法院统计已有模板数量
        - 按 TemplateCategory 统计覆盖情况
        - 按确认状态统计（confirmed vs not）

        Requirements: 8.4, 13.6
        """
        from apps.documents.models.external_template import ExternalTemplate

        base_qs: QuerySet[ExternalTemplate] = ExternalTemplate.objects.filter(
            law_firm_id=law_firm_id,
            is_active=True,
        )

        # 按法院统计
        by_court: list[dict[str, Any]] = list(
            base_qs.filter(court__isnull=False)
            .values("court_id", "court__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # 按类别统计
        by_category: list[dict[str, Any]] = list(
            base_qs.values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # 按确认状态统计
        from apps.documents.models.choices import TemplateStatus

        total: int = base_qs.count()
        confirmed_count: int = base_qs.filter(
            status=TemplateStatus.CONFIRMED,
        ).count()
        unconfirmed_count: int = total - confirmed_count

        statistics: dict[str, Any] = {
            "total": total,
            "by_court": by_court,
            "by_category": by_category,
            "confirmed": confirmed_count,
            "unconfirmed": unconfirmed_count,
        }

        logger.info(
            "模板统计: law_firm_id=%d, total=%d, confirmed=%d",
            law_firm_id,
            total,
            confirmed_count,
        )
        return statistics

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _group_by_category(
        self, templates: QuerySet[Any]
    ) -> dict[str, list[Any]]:
        """
        按 TemplateCategory 分组，每组内 is_confirmed=True 优先，
        然后按 -updated_at 排序。
        """
        grouped: dict[str, list[Any]] = collections.defaultdict(list)
        for tpl in templates:
            grouped[tpl.category].append(tpl)

        # 每组内排序：status=confirmed 优先，然后按 updated_at 倒序
        for category in grouped:
            grouped[category] = sorted(
                grouped[category],
                key=lambda t: (
                    0 if t.status == "confirmed" else 1,
                    -t.updated_at.timestamp(),
                ),
            )

        return dict(grouped)

    def _get_court_id_from_case(self, case: Any) -> int | None:
        """
        从案件获取关联法院 ID。

        通过 SupervisingAuthority（authority_type=trial）的名称
        匹配 Court 记录。
        """
        from apps.cases.models.case import SupervisingAuthority
        from apps.core.models.court import Court

        authority: SupervisingAuthority | None = (
            SupervisingAuthority.objects.filter(
                case=case,
                authority_type="trial",
            ).first()
        )

        if authority is None or not authority.name:
            return None

        court: Court | None = Court.objects.filter(
            name=authority.name,
            is_active=True,
        ).first()

        if court is not None:
            logger.info(
                "案件关联法院: case_id=%d, court_id=%d, court_name=%s",
                case.id,
                court.id,
                court.name,
            )
            return court.id  # type: ignore[return-value]

        logger.info(
            "案件审理机构未匹配到法院: case_id=%d, authority_name=%s",
            case.id,
            authority.name,
        )
        return None
