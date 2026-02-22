"""
LawyerServiceAdapter
实现 ILawyerService 跨模块接口，将 Lawyer Model 转换为 LawyerDTO。
"""

from __future__ import annotations

from typing import ClassVar

from apps.core.interfaces import ILawyerService, LawyerDTO
from apps.organization.models import Lawyer
from apps.organization.services.dto_assemblers import LawyerDtoAssembler

from .facade import LawyerService


class LawyerServiceAdapter(ILawyerService):
    """律师服务适配器，实现跨模块接口，将 Model 转换为 DTO。"""

    _assembler: ClassVar[LawyerDtoAssembler] = LawyerDtoAssembler()

    def __init__(self, service: LawyerService | None = None) -> None:
        self.service = service or LawyerService()

    def _to_dto(self, lawyer: Lawyer) -> LawyerDTO:
        return self._assembler.to_dto(lawyer)

    def get_lawyer(self, lawyer_id: int) -> LawyerDTO | None:
        lawyer = self.service._get_lawyer_internal(lawyer_id)
        if not lawyer:
            return None
        return self._to_dto(lawyer)

    def get_lawyers_by_ids(self, lawyer_ids: list[int]) -> list[LawyerDTO]:
        lawyers = self.service.get_lawyers_by_ids(lawyer_ids)
        return [self._to_dto(lawyer) for lawyer in lawyers]

    def get_team_members(self, team_id: int) -> list[LawyerDTO]:
        members = self.service.get_team_members(team_id)
        return [self._to_dto(m) for m in members]

    def get_admin_lawyer_internal(self) -> LawyerDTO | None:
        admin_lawyer = (
            self.service.get_lawyer_queryset().filter(is_admin=True).first()
        )
        if admin_lawyer:
            return self._to_dto(admin_lawyer)
        return None

    def get_all_lawyer_names_internal(self) -> list[str]:
        names = (
            self.service.get_lawyer_queryset()
            .filter(real_name__isnull=False)
            .exclude(real_name="")
            .values_list("real_name", flat=True)
        )
        return list(names)

    def get_lawyer_internal(self, lawyer_id: int) -> Lawyer | None:
        """内部方法：获取律师 Model 对象（无权限检查），供跨模块 ForeignKey 赋值使用。"""
        return self.service._get_lawyer_internal(lawyer_id)
