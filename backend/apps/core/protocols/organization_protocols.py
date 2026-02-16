"""
组织相关 Protocol 接口定义

包含:IOrganizationService, ILawyerService, ILawFirmService
"""

from typing import Any, Protocol

from apps.core.dtos import AccountCredentialDTO, LawFirmDTO, LawyerDTO


class IOrganizationService(Protocol):
    """
    组织服务接口

    定义组织(律所、团队)相关的公共方法
    """

    def get_law_firm(self, law_firm_id: int) -> dict[str, Any] | None:
        """
        获取律所信息

        Args:
            law_firm_id: 律所 ID

        Returns:
            律所信息字典,不存在时返回 None
        """
        ...

    def get_team(self, team_id: int) -> dict[str, Any] | None:
        """
        获取团队信息

        Args:
            team_id: 团队 ID

        Returns:
            团队信息字典,不存在时返回 None
        """
        ...

    def get_lawyers_in_organization(self, organization_id: int) -> list[LawyerDTO]:
        """
        获取组织内的所有律师

        Args:
            organization_id: 组织 ID

        Returns:
            律师 DTO 列表
        """
        ...

    def get_all_credentials_internal(self) -> list[AccountCredentialDTO]:
        """
        内部方法:获取所有账号凭证

        Returns:
            所有账号凭证的 DTO 列表
        """
        ...

    def get_credential_internal(self, credential_id: int) -> AccountCredentialDTO:
        """
        内部方法:获取账号凭证(无权限检查)

        Args:
            credential_id: 凭证 ID

        Returns:
            账号凭证 DTO

        Raises:
            NotFoundError: 凭证不存在
        """
        ...

    def get_lawyer_by_id_internal(self, lawyer_id: int) -> LawyerDTO | None:
        """
        内部方法:根据 ID 获取律师信息

        Args:
            lawyer_id: 律师 ID

        Returns:
            LawyerDTO,不存在返回 None
        """
        ...

    def get_default_lawyer_id_internal(self) -> int | None: ...


class ILawyerService(Protocol):
    """
    律师服务接口

    定义律师服务的公共方法,供其他模块使用
    """

    def get_lawyer(self, lawyer_id: int) -> LawyerDTO | None:
        """
        获取律师信息

        Args:
            lawyer_id: 律师 ID

        Returns:
            律师 DTO,不存在时返回 None
        """
        ...

    def get_lawyers_by_ids(self, lawyer_ids: list[int]) -> list[LawyerDTO]:
        """
        批量获取律师信息

        Args:
            lawyer_ids: 律师 ID 列表

        Returns:
            律师 DTO 列表
        """
        ...

    def get_team_members(self, team_id: int) -> list[LawyerDTO]:
        """
        获取团队成员

        Args:
            team_id: 团队 ID

        Returns:
            团队成员律师 DTO 列表
        """
        ...

    def validate_lawyer_active(self, lawyer_id: int) -> bool:
        """
        验证律师是否有效(is_active=True)

        Args:
            lawyer_id: 律师 ID

        Returns:
            律师是否有效
        """
        ...

    def check_lawyer_permission(self, lawyer_id: int, permission: str) -> bool:
        """
        检查律师是否有指定权限

        Args:
            lawyer_id: 律师 ID
            permission: 权限名称

        Returns:
            是否有权限
        """
        ...

    def get_admin_lawyer_internal(self) -> LawyerDTO | None:
        """
        内部方法:获取管理员律师

        Returns:
            管理员律师 DTO,不存在时返回 None
        """
        ...

    def get_all_lawyer_names_internal(self) -> list[str]:
        """
        内部方法:获取所有律师姓名

        Returns:
            所有律师的姓名列表
        """
        ...


class ILawFirmService(Protocol):
    """
    律所服务接口

    定义律所服务的公共方法,供其他模块使用
    """

    def get_lawfirm(self, lawfirm_id: int) -> LawFirmDTO | None:
        """
        获取律所信息

        Args:
            lawfirm_id: 律所 ID

        Returns:
            律所 DTO,不存在时返回 None
        """
        ...

    def get_lawfirms_by_ids(self, lawfirm_ids: list[int]) -> list[LawFirmDTO]:
        """
        批量获取律所信息

        Args:
            lawfirm_ids: 律所 ID 列表

        Returns:
            律所 DTO 列表
        """
        ...
