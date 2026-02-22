"""Business logic services."""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.organization.dtos import LawyerListFiltersDTO
from apps.organization.models import Lawyer
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy


class LawyerQueryService:
    def __init__(self, access_policy: OrganizationAccessPolicy) -> None:
        self.access_policy = access_policy

    def get_lawyer_queryset(self) -> QuerySet[Lawyer, Lawyer]:
        return Lawyer.objects.select_related("law_firm").prefetch_related("lawyer_teams", "biz_teams")

    def get_lawyer(self, lawyer_id: int, user: Lawyer) -> Lawyer:
        lawyer = self.get_lawyer_queryset().filter(id=lawyer_id).first()
        if not lawyer:
            raise NotFoundError(message=_("律师不存在"), code="LAWYER_NOT_FOUND")

        if not self.access_policy.can_read_lawyer(user=user, lawyer=lawyer):
            raise PermissionDenied(message=_("无权限访问该律师信息"), code="PERMISSION_DENIED")

        return lawyer

    def list_lawyers(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: LawyerListFiltersDTO | None = None,
        user: Lawyer | None = None,
    ) -> QuerySet[Lawyer, Lawyer]:
        queryset = self.get_lawyer_queryset()

        if user and not user.is_superuser:
            user_law_firm_id: int | None = user.law_firm_id
            if user_law_firm_id is not None:
                queryset = queryset.filter(law_firm_id=user_law_firm_id)
            else:
                return queryset.none()

        if filters and filters.search:
            queryset = queryset.filter(
                Q(username__icontains=filters.search) | Q(real_name__icontains=filters.search)
            )

        if filters and filters.law_firm_id is not None:
            queryset = queryset.filter(law_firm_id=filters.law_firm_id)

        queryset = queryset.order_by("-id")

        start = (page - 1) * page_size
        end = start + page_size

        return queryset[start:end]

    def get_lawyers_by_ids(self, lawyer_ids: list[int]) -> list[Lawyer]:
        return list(self.get_lawyer_queryset().filter(id__in=lawyer_ids))

    def get_team_members(self, team_id: int) -> list[Lawyer]:
        return list(self.get_lawyer_queryset().filter(lawyer_teams__id=team_id).distinct())

    def get_team_member_ids(self, user: Lawyer) -> set[int]:
        member_ids = set(
            Lawyer.objects.filter(lawyer_teams__in=user.lawyer_teams.all())
            .values_list("id", flat=True)
            .distinct()
        )
        if not member_ids:
            member_ids.add(user.pk)
        return member_ids
