"""
合同相关 Protocol 接口定义

包含:IContractService, IContractPaymentService
"""

from typing import Any, Protocol

from apps.core.dtos import ContractDTO, LawyerDTO, PartyRoleDTO, SupplementaryAgreementDTO
from apps.core.security.access_context import AccessContext


class IContractService(Protocol):
    """
    合同服务接口

    定义合同服务的公共方法,供其他模块使用
    """

    def get_contract(self, contract_id: int) -> ContractDTO | None:
        """
        获取合同信息

        Args:
            contract_id: 合同 ID

        Returns:
            合同 DTO,不存在时返回 None
        """
        ...

    def get_contract_stages(self, contract_id: int) -> list[str]:
        """
        获取合同的代理阶段

        Args:
            contract_id: 合同 ID

        Returns:
            代理阶段列表

        Raises:
            NotFoundError: 合同不存在
        """
        ...

    def validate_contract_active(self, contract_id: int) -> bool:
        """
        验证合同是否有效(状态为 active)

        Args:
            contract_id: 合同 ID

        Returns:
            合同是否有效
        """
        ...

    def get_contracts_by_ids(self, contract_ids: list[int]) -> list[ContractDTO]:
        """
        批量获取合同信息

        Args:
            contract_ids: 合同 ID 列表

        Returns:
            合同 DTO 列表
        """
        ...

    def get_contract_assigned_lawyer_id(self, contract_id: int) -> int | None:
        """
        获取合同的主办律师 ID(使用 primary_lawyer)

        Args:
            contract_id: 合同 ID

        Returns:
            主办律师 ID,合同不存在或无主办律师时返回 None
        """
        ...

    def get_contract_lawyers(self, contract_id: int) -> list[LawyerDTO]:
        """
        获取合同的所有律师

        Args:
            contract_id: 合同 ID

        Returns:
            律师 DTO 列表,按 is_primary 降序、order 升序排列

        Raises:
            NotFoundError: 合同不存在
        """
        ...

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        """
        获取合同及其补充协议的所有当事人

        聚合 ContractParty 和 SupplementaryAgreementParty 中的所有 Client,
        按 client_id 去重,返回包含来源标识的当事人列表.

        Args:
            contract_id: 合同 ID

        Returns:
            当事人列表,每个元素包含:
            - id: Client ID
            - name: Client 名称
            - source: 来源 ("contract" 或 "supplementary")

        Raises:
            NotFoundError: 合同不存在
        """
        ...

    def get_contract_with_details_internal(self, contract_id: int) -> dict[str, Any] | None:
        """
        内部方法:获取合同详细信息(包含当事人、律师等关联数据)

        Args:
            contract_id: 合同 ID

        Returns:
            合同详细信息字典,包含:
            - 基本信息
            - contract_parties: 当事人列表
            - assignments: 律师指派列表
        """
        ...

    def ensure_contract_access_ctx(self, contract_id: int, ctx: AccessContext) -> None: ...

    def ensure_contract_access_ctx_internal(self, contract_id: int, ctx: AccessContext) -> None: ...

    def get_party_roles_by_contract_internal(self, contract_id: int) -> list[PartyRoleDTO]:
        """
        内部方法:获取合同的所有当事人角色

        Args:
            contract_id: 合同 ID

        Returns:
            PartyRoleDTO 列表
        """
        ...

    def get_fee_mode_display_internal(self, fee_mode: str) -> str:
        """
        内部方法:获取收费模式显示名称

        Args:
            fee_mode: 收费模式代码

        Returns:
            显示名称
        """
        ...

    def get_opposing_parties_internal(self, contract_id: int) -> list[PartyRoleDTO]:
        """
        内部方法:获取对方当事人列表

        Args:
            contract_id: 合同 ID

        Returns:
            对方当事人 PartyRoleDTO 列表
        """
        ...

    def get_principals_internal(self, contract_id: int) -> list[PartyRoleDTO]:
        """
        内部方法:获取委托人列表

        Args:
            contract_id: 合同 ID

        Returns:
            委托人 PartyRoleDTO 列表
        """
        ...

    def get_supplementary_agreements_internal(self, contract_id: int) -> list[SupplementaryAgreementDTO]:
        """
        内部方法:获取合同的补充协议列表

        Args:
            contract_id: 合同 ID

        Returns:
            SupplementaryAgreementDTO 列表
        """
        ...

    def get_contract_model_internal(self, contract_id: int) -> Any | None:
        """
        内部方法:获取合同 Model 对象(用于外键赋值或占位符服务)

        Args:
            contract_id: 合同 ID

        Returns:
            Contract Model 对象,不存在时返回 None
        """
        ...

    def get_supplementary_agreement_model_internal(self, contract_id: int, agreement_id: int) -> Any | None:
        """
        内部方法:获取补充协议 Model 对象(用于占位符服务)

        Args:
            contract_id: 合同 ID
            agreement_id: 补充协议 ID

        Returns:
            SupplementaryAgreement Model 对象,不存在时返回 None
        """
        ...


class IContractAssignmentQueryService(Protocol):
    def list_lawyer_ids_by_contract_internal(self, contract_id: int) -> list[int]: ...


class IContractPaymentService(Protocol):
    """
    合同收款服务接口

    定义合同收款管理的核心方法
    """

    def list_payments(
        self,
        contract_id: int | None = None,
        invoice_status: str | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        获取收款列表

        Args:
            contract_id: 合同 ID(可选)
            invoice_status: 开票状态筛选(可选)
            start_date: 开始日期筛选(可选)
            end_date: 结束日期筛选(可选)
            user: 当前用户
            perm_open_access: 是否开放访问权限

        Returns:
            收款记录查询集
        """
        ...

    def get_payment(
        self,
        payment_id: int,
        user: Any | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        获取单个收款记录

        Args:
            payment_id: 收款 ID
            user: 当前用户
            perm_open_access: 是否开放访问权限

        Returns:
            收款对象

        Raises:
            NotFoundError: 收款不存在
        """
        ...

    def create_payment(
        self,
        contract_id: int,
        amount: Any,
        received_at: Any | None = None,
        invoice_status: str | None = None,
        invoiced_amount: Any | None = None,
        note: str | None = None,
        user: Any | None = None,
        confirm: bool = False,
    ) -> Any:
        """
        创建收款记录

        Args:
            contract_id: 合同 ID
            amount: 收款金额
            received_at: 收款日期
            invoice_status: 开票状态
            invoiced_amount: 已开票金额
            note: 备注
            user: 当前用户
            confirm: 是否二次确认

        Returns:
            创建的收款对象

        Raises:
            PermissionDenied: 无管理员权限
            ValidationException: 数据验证失败
            NotFoundError: 合同不存在
        """
        ...

    def update_payment(
        self,
        payment_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        confirm: bool = False,
    ) -> Any:
        """
        更新收款记录

        Args:
            payment_id: 收款 ID
            data: 更新数据
            user: 当前用户
            confirm: 是否二次确认

        Returns:
            更新后的收款对象

        Raises:
            PermissionDenied: 无管理员权限
            ValidationException: 数据验证失败
            NotFoundError: 收款不存在
        """
        ...

    def delete_payment(
        self,
        payment_id: int,
        user: Any | None = None,
        confirm: bool = False,
    ) -> dict[str, bool]:
        """
        删除收款记录

        Args:
            payment_id: 收款 ID
            user: 当前用户
            confirm: 是否二次确认

        Returns:
            {"success": True}

        Raises:
            PermissionDenied: 无管理员权限
            ValidationException: 未二次确认
            NotFoundError: 收款不存在
        """
        ...


class IContractFolderBindingService(Protocol):
    def save_file_to_bound_folder(
        self,
        contract_id: int,
        file_content: bytes,
        file_name: str,
        subdir_key: str = "contract_documents",
    ) -> str | None: ...

    def extract_zip_to_bound_folder(self, contract_id: int, zip_content: bytes) -> str | None: ...
