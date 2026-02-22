"""
LawyerService 门面类
统一封装 LawyerMutationService / LawyerQueryService / LawyerUploadService，
对外保持与旧 LawyerService 完全一致的 API 签名。
"""

from __future__ import annotations

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from ninja.files import UploadedFile

from apps.core.exceptions import AuthenticationError
from apps.organization.dtos import LawyerCreateDTO, LawyerListFiltersDTO, LawyerUpdateDTO
from apps.organization.models import Lawyer
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy

from .mutation import LawyerMutationService
from .query import LawyerQueryService
from .upload import LawyerUploadService


class LawyerService:
    """
    律师服务门面

    将拆分后的 Mutation / Query / Upload 三个子服务统一为一个入口，
    保持与旧 LawyerService 完全兼容的公开方法签名。
    """

    def __init__(self) -> None:
        policy = OrganizationAccessPolicy()
        upload_svc = LawyerUploadService()
        self._mutation = LawyerMutationService(access_policy=policy, upload_service=upload_svc)
        self._query = LawyerQueryService(access_policy=policy)

    # ---- Query 代理 ----

    def get_lawyer_queryset(self) -> QuerySet[Lawyer, Lawyer]:
        return self._query.get_lawyer_queryset()

    def get_lawyer(self, lawyer_id: int, user: Lawyer | None) -> Lawyer:
        if user is None:
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")
        return self._query.get_lawyer(lawyer_id, user)

    def list_lawyers(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: LawyerListFiltersDTO | None = None,
        user: Lawyer | None = None,
    ) -> QuerySet[Lawyer, Lawyer]:
        return self._query.list_lawyers(page=page, page_size=page_size, filters=filters, user=user)

    def get_lawyers_by_ids(self, lawyer_ids: list[int]) -> list[Lawyer]:
        return self._query.get_lawyers_by_ids(lawyer_ids)

    def get_team_members(self, team_id: int) -> list[Lawyer]:
        return self._query.get_team_members(team_id)

    def get_team_member_ids(self, user: Lawyer) -> set[int]:
        return self._query.get_team_member_ids(user)

    # ---- Mutation 代理 ----

    def create_lawyer(
        self, data: LawyerCreateDTO, user: Lawyer | None, license_pdf: UploadedFile | None = None
    ) -> Lawyer:
        if user is None:
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")
        return self._mutation.create_lawyer(data=data, user=user, license_pdf=license_pdf)

    def update_lawyer(
        self,
        lawyer_id: int,
        data: LawyerUpdateDTO,
        user: Lawyer | None,
        license_pdf: UploadedFile | None = None,
    ) -> Lawyer:
        lawyer = self.get_lawyer(lawyer_id, user)
        # get_lawyer 对 user=None 抛 AuthenticationError，此处 user 必不为 None
        if user is None:  # pragma: no cover
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")
        return self._mutation.update_lawyer(lawyer=lawyer, data=data, user=user, license_pdf=license_pdf)

    def delete_lawyer(self, lawyer_id: int, user: Lawyer | None) -> None:
        lawyer = self.get_lawyer(lawyer_id, user)
        # get_lawyer 对 user=None 抛 AuthenticationError，此处 user 必不为 None
        if user is None:  # pragma: no cover
            raise AuthenticationError(message=_("请先登录"), code="AUTHENTICATION_REQUIRED")
        self._mutation.delete_lawyer(lawyer=lawyer, user=user)

    # ---- 内部方法 ----

    def _get_lawyer_internal(self, lawyer_id: int) -> Lawyer | None:
        """内部方法：获取律师（无权限检查），供 ServiceAdapter 调用。"""
        return self.get_lawyer_queryset().filter(id=lawyer_id).first()
