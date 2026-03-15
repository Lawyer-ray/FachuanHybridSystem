"""
组织服务适配器
实现IOrganizationService接口，提供跨模块调用的统一入口
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.exceptions import NotFoundError
from apps.core.interfaces import AccountCredentialDTO, IOrganizationService, LawFirmDTO, TeamDTO
from apps.organization.dtos import LawyerListFiltersDTO
from apps.organization.services.dto_assemblers import LawyerDtoAssembler
from apps.organization.services.lawfirm_service import LawFirmService
from apps.organization.services.lawyer.facade import LawyerService
from apps.organization.services.team_service import TeamService

from .account_credential_service import AccountCredentialService

if TYPE_CHECKING:
    from apps.core.dto.organization import LawyerDTO

_assembler = LawyerDtoAssembler()


class OrganizationServiceAdapter(IOrganizationService):
    def __init__(self, account_credential_service: AccountCredentialService | None = None) -> None:
        self._account_credential_service = account_credential_service
        self._lawfirm_service: LawFirmService | None = None
        self._team_service: TeamService | None = None
        self._lawyer_service: LawyerService | None = None

    @property
    def account_credential_service(self) -> AccountCredentialService:
        if self._account_credential_service is None:
            self._account_credential_service = AccountCredentialService()
        return self._account_credential_service

    @property
    def lawfirm_service(self) -> LawFirmService:
        if self._lawfirm_service is None:
            self._lawfirm_service = LawFirmService()
        return self._lawfirm_service

    @property
    def team_service(self) -> TeamService:
        if self._team_service is None:
            self._team_service = TeamService()
        return self._team_service

    @property
    def lawyer_service(self) -> LawyerService:
        if self._lawyer_service is None:
            self._lawyer_service = LawyerService()
        return self._lawyer_service

    def get_law_firm(self, law_firm_id: int) -> LawFirmDTO | None:
        lawfirm = self.lawfirm_service.get_lawfirm_by_id(law_firm_id)
        if lawfirm is None:
            return None
        return LawFirmDTO.from_model(lawfirm)

    def get_team(self, team_id: int) -> TeamDTO | None:
        try:
            team = self.team_service.get_team(team_id)
        except NotFoundError:
            return None
        return TeamDTO.from_model(team)

    def get_lawyers_in_organization(self, organization_id: int) -> list[LawyerDTO]:
        lawyers = self.lawyer_service.list_lawyers(filters=LawyerListFiltersDTO(law_firm_id=organization_id))
        return [_assembler.to_dto(lawyer) for lawyer in lawyers]

    def get_all_credentials_internal(self) -> list[AccountCredentialDTO]:
        credentials = self.account_credential_service._get_base_queryset()
        return [AccountCredentialDTO.from_model(credential) for credential in credentials]

    def get_credential_internal(self, credential_id: int) -> AccountCredentialDTO:
        credential = self.account_credential_service.get_credential_by_id(credential_id)
        return AccountCredentialDTO.from_model(credential)

    def get_credentials_by_site_internal(self, site_name: str) -> list[AccountCredentialDTO]:
        credentials = self.account_credential_service.get_credentials_by_site(site_name)
        return [AccountCredentialDTO.from_model(c) for c in credentials]

    def get_credential_by_account_internal(self, account: str, site_name: str) -> AccountCredentialDTO:
        credential = self.account_credential_service.get_credential_by_account(account, site_name)
        return AccountCredentialDTO.from_model(credential)

    def update_login_success_internal(self, credential_id: int) -> None:
        self.account_credential_service.update_login_success(credential_id)

    def update_login_failure_internal(self, credential_id: int) -> None:
        self.account_credential_service.update_login_failure(credential_id)

    def get_lawyer_by_id_internal(self, lawyer_id: int) -> LawyerDTO | None:
        lawyer = self.lawyer_service.get_lawyer_by_id(lawyer_id)
        if lawyer is None:
            return None
        return _assembler.to_dto(lawyer)

    def get_default_lawyer_id_internal(self) -> int | None:
        queryset = self.lawyer_service.get_lawyer_queryset()
        admin = queryset.filter(is_admin=True).order_by("id").first()
        if admin is not None:
            return int(admin.id)
        fallback = queryset.order_by("id").first()
        return int(fallback.id) if fallback is not None else None
