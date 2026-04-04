"""
案件相关 Protocol 接口定义

包含:ICaseService, ICaseSearchService, ICaseNumberService, ICaseLogService
"""

from typing import Any, Protocol

from apps.core.dto import CaseDTO, CasePartyDTO, CaseSearchResultDTO, CaseTemplateBindingDTO


class ICaseService(Protocol):
    """
    案件服务接口

    定义案件服务的公共方法,供其他模块使用
    """

    def get_case(self, case_id: int) -> CaseDTO | None:
        """
        获取案件信息

        Args:
            case_id: 案件 ID

        Returns:
            案件 DTO,不存在时返回 None
        """
        ...

    def get_cases_by_contract(self, contract_id: int) -> list[CaseDTO]:
        """
        获取合同关联的案件

        Args:
            contract_id: 合同 ID

        Returns:
            案件 DTO 列表
        """
        ...

    def check_case_access(self, case_id: int, user_id: int) -> bool:
        """
        检查用户是否有权限访问案件

        Args:
            case_id: 案件 ID
            user_id: 用户 ID

        Returns:
            是否有权限访问
        """
        ...

    def get_cases_by_ids(self, case_ids: list[int]) -> list[CaseDTO]:
        """
        批量获取案件信息

        Args:
            case_ids: 案件 ID 列表

        Returns:
            案件 DTO 列表
        """
        ...

    def validate_case_active(self, case_id: int) -> bool:
        """
        验证案件是否有效(状态为 active)

        Args:
            case_id: 案件 ID

        Returns:
            案件是否有效
        """
        ...

    def get_case_current_stage(self, case_id: int) -> str | None:
        """
        获取案件的当前阶段

        Args:
            case_id: 案件 ID

        Returns:
            当前阶段,案件不存在时返回 None
        """
        ...

    def create_case(self, data: dict[str, Any]) -> CaseDTO:
        """
        创建案件

        Args:
            data: 案件数据字典,包含:
                - name: 案件名称(必填)
                - contract_id: 合同 ID(可选)
                - is_archived: 是否已建档(可选,默认 False)
                - case_type: 案件类型(可选)
                - target_amount: 涉案金额(可选)
                - cause_of_action: 案由(可选)
                - current_stage: 当前阶段(可选)

        Returns:
            创建的案件 DTO
        """
        ...

    def create_case_assignment(self, case_id: int, lawyer_id: int) -> bool:
        """
        创建案件指派

        Args:
            case_id: 案件 ID
            lawyer_id: 律师 ID

        Returns:
            是否创建成功
        """
        ...

    def create_case_party(self, case_id: int, client_id: int, legal_status: str | None = None) -> bool:
        """
        创建案件当事人

        Args:
            case_id: 案件 ID
            client_id: 客户 ID
            legal_status: 诉讼地位(可选)

        Returns:
            是否创建成功
        """
        ...

    def get_user_extra_case_access(self, user_id: int) -> list[int]:
        """
        获取用户的额外案件访问授权

        Args:
            user_id: 用户 ID

        Returns:
            用户有额外访问权限的案件 ID 列表
        """
        ...

    def get_case_by_id_internal(self, case_id: int) -> CaseDTO | None:
        """
        内部方法:获取案件信息(无权限检查)

        Args:
            case_id: 案件 ID

        Returns:
            案件 DTO,不存在时返回 None
        """
        ...

    def search_cases_by_party_internal(self, party_names: list[str], status: str | None = None) -> list[CaseDTO]:
        """
        内部方法:根据当事人名称搜索案件

        Args:
            party_names: 当事人名称列表
            status: 案件状态筛选(可选)

        Returns:
            匹配的案件 DTO 列表
        """
        ...

    def get_case_numbers_by_case_internal(self, case_id: int) -> list[str]:
        """
        内部方法:获取案件的所有案号

        Args:
            case_id: 案件 ID

        Returns:
            案号字符串列表
        """
        ...

    def get_case_party_names_internal(self, case_id: int) -> list[str]:
        """
        内部方法:获取案件的所有当事人名称

        Args:
            case_id: 案件 ID

        Returns:
            当事人名称列表
        """
        ...

    def search_cases_by_case_number_internal(self, case_number: str) -> list[CaseDTO]:
        """
        内部方法:根据案号搜索案件

        Args:
            case_number: 案号字符串

        Returns:
            匹配的案件 DTO 列表
        """
        ...

    def create_case_log_internal(self, case_id: int, content: str, user_id: int | None = None) -> int:
        """
        内部方法:创建案件日志,返回日志ID

        Args:
            case_id: 案件 ID
            content: 日志内容
            user_id: 用户 ID(可选)

        Returns:
            创建的日志 ID

        Raises:
            NotFoundError: 案件不存在
        """
        ...

    def add_case_log_attachment_internal(self, case_log_id: int, file_path: str, file_name: str) -> bool:
        """
        内部方法:添加案件日志附件

        Args:
            case_log_id: 案件日志 ID
            file_path: 文件路径
            file_name: 文件名称

        Returns:
            是否添加成功

        Raises:
            NotFoundError: 案件日志不存在
        """
        ...

    def add_case_number_internal(self, case_id: int, case_number: str, user_id: int | None = None) -> bool:
        """
        内部方法:为案件添加案号(如果不存在)

        Args:
            case_id: 案件 ID
            case_number: 案号字符串
            user_id: 操作用户 ID(可选)

        Returns:
            是否添加成功(已存在也返回 True)
        """
        ...

    def update_case_log_reminder_internal(self, case_log_id: int, reminder_time: Any, reminder_type: str) -> bool:
        """
        内部方法:更新案件日志的提醒时间和类型

        Args:
            case_log_id: 案件日志 ID
            reminder_time: 提醒时间(datetime)
            reminder_type: 提醒类型(CaseLogReminderType 枚举值)

        Returns:
            是否更新成功
        """
        ...

    def get_case_model_internal(self, case_id: int) -> Any | None:
        """
        内部方法:获取案件 Model 对象(用于外键赋值)

        Args:
            case_id: 案件 ID

        Returns:
            Case Model 对象,不存在时返回 None
        """
        ...

    def get_case_log_model_internal(self, case_log_id: int) -> Any | None:
        """
        内部方法:获取案件日志 Model 对象(用于外键赋值)

        Args:
            case_log_id: 案件日志 ID

        Returns:
            CaseLog Model 对象,不存在时返回 None
        """
        ...

    def get_case_with_details_internal(self, case_id: int) -> dict[str, Any] | None:
        """
        内部方法:获取案件详细信息(包含当事人、案号等关联数据)

        Args:
            case_id: 案件 ID

        Returns:
            案件详细信息字典
        """
        ...

    def unbind_cases_from_contract_internal(self, contract_id: int) -> int:
        """
        内部方法:解绑合同下的所有案件

        Args:
            contract_id: 合同 ID

        Returns:
            解绑的案件数量
        """
        ...

    def count_cases_by_contract(self, contract_id: int) -> int:
        """
        内部方法:统计合同下的案件数（删除合同时用于日志记录）

        Args:
            contract_id: 合同 ID

        Returns:
            案件数量
        """
        ...

    def get_primary_lawyer_names_by_case_ids_internal(self, case_ids: list[int]) -> dict[int, str | None]:
        """
        内部方法:批量获取案件主办律师姓名(取案件指派列表的第一个律师)
        """
        ...

    def get_case_parties_by_legal_status_internal(self, case_id: int, legal_status: str) -> list[str]:
        """
        内部方法:根据诉讼地位获取当事人名称列表

        Args:
            case_id: 案件 ID
            legal_status: 诉讼地位 (plaintiff/defendant 等)

        Returns:
            当事人名称列表
        """
        ...

    def get_case_template_binding_internal(self, case_id: int) -> CaseTemplateBindingDTO | None:
        """
        内部方法:获取案件的模板绑定信息

        Args:
            case_id: 案件 ID

        Returns:
            CaseTemplateBindingDTO,不存在返回 None
        """
        ...

    def get_case_parties_internal(self, case_id: int, legal_status: str | None = None) -> list[CasePartyDTO]:
        """
        内部方法:获取案件当事人列表

        Args:
            case_id: 案件 ID
            legal_status: 法律地位筛选(可选)

        Returns:
            CasePartyDTO 列表
        """
        ...

    def get_case_template_bindings_by_name_internal(
        self, case_id: int, template_name: str
    ) -> list[CaseTemplateBindingDTO]:
        """
        内部方法:根据模板名称获取案件模板绑定列表

        Args:
            case_id: 案件 ID
            template_name: 模板名称

        Returns:
            CaseTemplateBindingDTO 列表
        """
        ...

    def get_case_internal(self, case_id: int) -> CaseDTO | None:
        """
        内部方法:获取案件信息(无权限检查)

        Args:
            case_id: 案件 ID

        Returns:
            案件 DTO,不存在时返回 None
        """
        ...

    def search_cases_for_binding_internal(self, search_term: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """
        内部方法:搜索可绑定的案件(用于文书识别等跨模块场景)

        支持按案件名称、案号、当事人搜索,返回包含案号和当事人的完整信息.

        Args:
            search_term: 搜索关键词
            limit: 返回数量限制

        Returns:
            案件信息字典列表,每个元素包含:
            - id: 案件 ID
            - name: 案件名称
            - case_numbers: 案号列表
            - parties: 当事人名称列表
            - created_at: 创建时间 ISO 格式字符串
        """
        ...


class ICaseSearchService(Protocol):
    """
    案件搜索服务接口

    定义案件搜索的核心方法,供跨模块调用.
    用于 API 层搜索案件,避免直接导入 Model 和使用 Q() 查询.

    Requirements: 1.1, 2.1
    """

    def search_cases(self, query: str, limit: int = 20) -> list[CaseSearchResultDTO]:
        """
        搜索案件

        支持按案件名称、案号、当事人搜索.

        Args:
            query: 搜索关键词(案件名称、案号、当事人)
            limit: 返回结果数量限制,默认20

        Returns:
            匹配的案件搜索结果 DTO 列表
        """
        ...


class ICaseNumberService(Protocol):
    """
    案号服务接口

    定义案号管理的核心方法,供跨模块调用
    """

    def list_numbers_internal(self, case_id: int) -> list[Any]:
        """
        内部方法:获取案件的所有案号

        Args:
            case_id: 案件 ID

        Returns:
            案号对象列表
        """
        ...

    def create_number_internal(self, case_id: int, number: str, remarks: str | None = None) -> Any:
        """
        内部方法:创建案号

        Args:
            case_id: 案件 ID
            number: 案号
            remarks: 备注(可选)

        Returns:
            创建的案号对象
        """
        ...

    def format_case_number(self, number: str) -> str:
        """
        格式化案号:统一括号、删除空格

        在保存前调用此方法，确保案号格式统一。

        Args:
            number: 原始案号

        Returns:
            格式化后的案号
        """
        ...

    def normalize_case_number(self, number: str) -> str:
        """
        规范化案号:统一括号、删除空格

        .. deprecated::
            使用 :meth:`format_case_number` 代替

        Args:
            number: 原始案号

        Returns:
            规范化后的案号
        """
        ...


class ICaseFilingNumberService(Protocol):
    def generate_case_filing_number_internal(self, case_id: int, case_type: str, created_year: int) -> str: ...


class ICaseLogService(Protocol):
    """
    案件日志服务接口

    定义案件日志管理的核心方法
    """

    def list_logs(
        self,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        获取日志列表

        Args:
            case_id: 案件 ID(可选,用于过滤)
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            日志查询集
        """
        ...

    def get_log(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        获取单个日志

        Args:
            log_id: 日志 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            日志对象

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限访问
        """
        ...

    def create_log(
        self,
        case_id: int,
        content: str,
        user: Any | None = None,
        reminder_type: str | None = None,
        reminder_time: Any | None = None,
    ) -> Any:
        """
        创建案件日志

        Args:
            case_id: 案件 ID
            content: 日志内容
            user: 当前用户
            reminder_type: 提醒类型
            reminder_time: 提醒时间

        Returns:
            创建的日志对象

        Raises:
            NotFoundError: 案件不存在
        """
        ...

    def update_log(
        self,
        log_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        更新案件日志

        Args:
            log_id: 日志 ID
            data: 更新数据字典
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            更新后的日志对象

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限修改
        """
        ...

    def delete_log(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """
        删除案件日志

        Args:
            log_id: 日志 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限删除
        """
        ...

    def upload_attachments(
        self,
        log_id: int,
        files: list[Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, int]:
        """
        上传日志附件

        Args:
            log_id: 日志 ID
            files: 上传的文件列表
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            {"count": 上传数量}

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限上传
            ValidationException: 文件验证失败
        """
        ...


class ILitigationFeeCalculatorService(Protocol):
    def calculate_all_fees(
        self,
        target_amount: Any | None = None,
        preservation_amount: Any | None = None,
        case_type: str | None = None,
        cause_of_action: str | None = None,
        cause_of_action_id: int | None = None,
    ) -> dict[str, Any]: ...
