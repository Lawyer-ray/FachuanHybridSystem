"""
客户相关 Protocol 接口定义

包含:IClientService
"""

from typing import Protocol

from apps.core.dtos import ClientDTO, ClientIdentityDocDTO, PropertyClueDTO


class IClientService(Protocol):
    """
    客户服务接口

    定义客户服务的公共方法,供其他模块使用
    """

    def get_client(self, client_id: int) -> ClientDTO | None:
        """
        获取客户信息

        Args:
            client_id: 客户 ID

        Returns:
            客户 DTO,不存在时返回 None
        """
        ...

    def get_client_internal(self, client_id: int) -> ClientDTO | None:
        """
        内部方法:获取客户信息(无权限检查)

        Args:
            client_id: 客户 ID

        Returns:
            客户 DTO,不存在时返回 None
        """
        ...

    def get_clients_by_ids(self, client_ids: list[int]) -> list[ClientDTO]:
        """
        批量获取客户信息

        Args:
            client_ids: 客户 ID 列表

        Returns:
            客户 DTO 列表
        """
        ...

    def validate_client_exists(self, client_id: int) -> bool:
        """
        验证客户是否存在

        Args:
            client_id: 客户 ID

        Returns:
            客户是否存在
        """
        ...

    def get_client_by_name(self, name: str) -> ClientDTO | None:
        """
        根据名称获取客户

        Args:
            name: 客户名称

        Returns:
            客户 DTO,不存在时返回 None
        """
        ...

    def get_all_clients_internal(self) -> list[ClientDTO]:
        """
        内部方法:获取所有客户

        Returns:
            所有客户的 DTO 列表
        """
        ...

    def search_clients_by_name_internal(self, name: str, exact_match: bool = False) -> list[ClientDTO]:
        """
        内部方法:根据名称搜索客户

        Args:
            name: 客户名称或名称片段
            exact_match: 是否精确匹配(默认 False,支持模糊匹配)

        Returns:
            匹配的客户 DTO 列表
        """
        ...

    def get_property_clues_by_client_internal(self, client_id: int) -> list[PropertyClueDTO]:
        """
        内部方法:获取客户的财产线索

        Args:
            client_id: 客户 ID

        Returns:
            PropertyClueDTO 列表
        """
        ...

    def is_natural_person_internal(self, client_id: int) -> bool:
        """
        内部方法:判断客户是否为自然人

        Args:
            client_id: 客户 ID

        Returns:
            True 表示自然人,False 表示法人
        """
        ...

    def get_identity_docs_by_client_internal(self, client_id: int) -> list[ClientIdentityDocDTO]:
        """
        内部方法:获取客户的身份证件列表

        Args:
            client_id: 客户 ID

        Returns:
            ClientIdentityDocDTO 列表
        """
        ...
