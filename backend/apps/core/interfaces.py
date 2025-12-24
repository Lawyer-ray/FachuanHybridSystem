"""
跨模块接口定义
通过接口解耦模块间的直接依赖
"""
from typing import Protocol, Optional, List, Any, Dict
from dataclasses import dataclass


# ============================================================
# 数据传输对象 (DTO)
# 用于跨模块传递数据，避免直接依赖其他模块的 Model
# ============================================================

@dataclass
class LoginAttemptResult:
    """
    登录尝试结果DTO
    
    用于记录单次登录尝试的详细信息
    """
    success: bool
    token: Optional[str]
    account: str
    error_message: Optional[str]
    attempt_duration: float
    retry_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "success": self.success,
            "token": self.token,
            "account": self.account,
            "error_message": self.error_message,
            "attempt_duration": self.attempt_duration,
            "retry_count": self.retry_count
        }


@dataclass
class TokenAcquisitionResult:
    """
    Token获取结果DTO
    
    用于记录完整的Token获取流程结果
    """
    success: bool
    token: Optional[str]
    acquisition_method: str  # "existing", "auto_login"
    total_duration: float
    login_attempts: List[LoginAttemptResult]
    error_details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "success": self.success,
            "token": self.token,
            "acquisition_method": self.acquisition_method,
            "total_duration": self.total_duration,
            "login_attempts": [attempt.to_dict() for attempt in self.login_attempts],
            "error_details": self.error_details
        }


@dataclass
class AccountCredentialDTO:
    """
    账号凭证数据传输对象
    
    用于跨模块传递账号凭证数据，避免直接传递 Model 对象
    """
    id: int
    lawyer_id: int
    site_name: str
    url: Optional[str]
    account: str
    password: str
    last_login_success_at: Optional[str] = None
    login_success_count: int = 0
    login_failure_count: int = 0
    is_preferred: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # 律师信息（用于模板显示）
    lawyer: Optional[Any] = None

    @classmethod
    def from_model(cls, credential) -> "AccountCredentialDTO":
        """
        从 AccountCredential Model 转换为 DTO

        Args:
            credential: AccountCredential Model 实例

        Returns:
            AccountCredentialDTO 实例
        """
        return cls(
            id=credential.id,
            lawyer_id=credential.lawyer_id,
            site_name=credential.site_name,
            url=credential.url if hasattr(credential, 'url') else None,
            account=credential.account,
            password=credential.password,
            last_login_success_at=str(credential.last_login_success_at) if hasattr(credential, 'last_login_success_at') and credential.last_login_success_at else None,
            login_success_count=credential.login_success_count if hasattr(credential, 'login_success_count') else 0,
            login_failure_count=credential.login_failure_count if hasattr(credential, 'login_failure_count') else 0,
            is_preferred=credential.is_preferred if hasattr(credential, 'is_preferred') else False,
            created_at=str(credential.created_at) if hasattr(credential, 'created_at') and credential.created_at else None,
            updated_at=str(credential.updated_at) if hasattr(credential, 'updated_at') and credential.updated_at else None,
            lawyer=credential.lawyer if hasattr(credential, 'lawyer') else None,
        )

@dataclass
class LawyerDTO:
    """
    律师数据传输对象

    用于跨模块传递律师数据，避免直接传递 Model 对象
    """
    id: int
    username: str
    real_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False
    is_active: bool = True
    law_firm_id: Optional[int] = None
    law_firm_name: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None

    @classmethod
    def from_model(cls, lawyer) -> "LawyerDTO":
        """
        从 Lawyer Model 转换为 DTO

        Args:
            lawyer: Lawyer Model 实例

        Returns:
            LawyerDTO 实例
        """
        return cls(
            id=lawyer.id,
            username=lawyer.username if hasattr(lawyer, 'username') else str(lawyer.id),
            real_name=lawyer.real_name if hasattr(lawyer, 'real_name') else None,
            phone=lawyer.phone if hasattr(lawyer, 'phone') else None,
            email=lawyer.email if hasattr(lawyer, 'email') else None,
            is_admin=lawyer.is_admin if hasattr(lawyer, 'is_admin') else False,
            is_active=lawyer.is_active if hasattr(lawyer, 'is_active') else True,
            law_firm_id=lawyer.law_firm_id if hasattr(lawyer, 'law_firm_id') else None,
            law_firm_name=lawyer.law_firm.name if hasattr(lawyer, 'law_firm') and lawyer.law_firm else None,
            team_id=lawyer.team_id if hasattr(lawyer, 'team_id') else None,
            team_name=lawyer.team.name if hasattr(lawyer, 'team') and lawyer.team else None,
        )


@dataclass
class LawFirmDTO:
    """
    律所数据传输对象

    用于跨模块传递律所数据，避免直接传递 Model 对象
    """
    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    social_credit_code: Optional[str] = None

    @classmethod
    def from_model(cls, lawfirm) -> "LawFirmDTO":
        """
        从 LawFirm Model 转换为 DTO

        Args:
            lawfirm: LawFirm Model 实例

        Returns:
            LawFirmDTO 实例
        """
        return cls(
            id=lawfirm.id,
            name=lawfirm.name,
            address=lawfirm.address if hasattr(lawfirm, 'address') else None,
            phone=lawfirm.phone if hasattr(lawfirm, 'phone') else None,
            social_credit_code=lawfirm.social_credit_code if hasattr(lawfirm, 'social_credit_code') else None,
        )


@dataclass
class ClientDTO:
    """
    客户数据传输对象

    用于跨模块传递客户数据，避免直接传递 Model 对象
    """
    id: int
    name: str
    client_type: str
    phone: Optional[str] = None
    id_number: Optional[str] = None
    address: Optional[str] = None
    is_our_client: bool = False

    @classmethod
    def from_model(cls, client) -> "ClientDTO":
        """
        从 Client Model 转换为 DTO

        Args:
            client: Client Model 实例

        Returns:
            ClientDTO 实例
        """
        return cls(
            id=client.id,
            name=client.name,
            client_type=client.client_type if hasattr(client, 'client_type') else "individual",
            phone=client.phone if hasattr(client, 'phone') else None,
            id_number=client.id_number if hasattr(client, 'id_number') else None,
            address=client.address if hasattr(client, 'address') else None,
            is_our_client=client.is_our_client if hasattr(client, 'is_our_client') else False,
        )


@dataclass
class ContractDTO:
    """
    合同数据传输对象

    用于跨模块传递合同数据，避免直接传递 Model 对象
    """
    id: int
    name: str
    case_type: str
    status: str
    representation_stages: List[str]
    primary_lawyer_id: Optional[int] = None
    primary_lawyer_name: Optional[str] = None
    fee_mode: Optional[str] = None
    fixed_amount: Optional[Any] = None  # Decimal
    risk_rate: Optional[Any] = None  # Decimal
    is_archived: bool = False
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    @classmethod
    def from_model(cls, contract) -> "ContractDTO":
        """
        从 Contract Model 转换为 DTO

        Args:
            contract: Contract Model 实例

        Returns:
            ContractDTO 实例
        """
        # 获取主办律师（使用 primary_lawyer 属性）
        primary_lawyer = contract.primary_lawyer if hasattr(contract, 'primary_lawyer') else None
        
        return cls(
            id=contract.id,
            name=contract.name,
            case_type=contract.case_type,
            status=contract.status,
            representation_stages=contract.representation_stages or [],
            primary_lawyer_id=primary_lawyer.id if primary_lawyer else None,
            primary_lawyer_name=primary_lawyer.real_name if primary_lawyer and hasattr(primary_lawyer, 'real_name') else None,
            fee_mode=contract.fee_mode if hasattr(contract, 'fee_mode') else None,
            fixed_amount=contract.fixed_amount if hasattr(contract, 'fixed_amount') else None,
            risk_rate=contract.risk_rate if hasattr(contract, 'risk_rate') else None,
            is_archived=contract.is_archived if hasattr(contract, 'is_archived') else False,
            start_date=str(contract.start_date) if hasattr(contract, 'start_date') and contract.start_date else None,
            end_date=str(contract.end_date) if hasattr(contract, 'end_date') and contract.end_date else None,
        )


@dataclass
class CaseDTO:
    """
    案件数据传输对象

    用于跨模块传递案件数据，避免直接传递 Model 对象
    """
    id: int
    name: str
    current_stage: Optional[str] = None
    contract_id: Optional[int] = None
    status: str = "active"
    case_type: Optional[str] = None
    cause_of_action: Optional[str] = None
    target_amount: Optional[Any] = None  # Decimal
    is_archived: bool = False
    start_date: Optional[str] = None
    effective_date: Optional[str] = None

    @classmethod
    def from_model(cls, case) -> "CaseDTO":
        """
        从 Case Model 转换为 DTO

        Args:
            case: Case Model 实例

        Returns:
            CaseDTO 实例
        """
        return cls(
            id=case.id,
            name=case.name,
            current_stage=case.current_stage,
            contract_id=case.contract_id,
            status=case.status if hasattr(case, 'status') else "active",
            case_type=case.case_type if hasattr(case, 'case_type') else None,
            cause_of_action=case.cause_of_action if hasattr(case, 'cause_of_action') else None,
            target_amount=case.target_amount if hasattr(case, 'target_amount') else None,
            is_archived=case.is_archived if hasattr(case, 'is_archived') else False,
            start_date=str(case.start_date) if hasattr(case, 'start_date') and case.start_date else None,
            effective_date=str(case.effective_date) if hasattr(case, 'effective_date') and case.effective_date else None,
        )


# ============================================================
# 服务接口协议 (Protocol)
# 定义跨模块调用的接口规范
# ============================================================

class IAutoTokenAcquisitionService(Protocol):
    """
    自动Token获取服务接口
    
    定义自动Token获取的核心方法
    """
    
    async def acquire_token_if_needed(
        self, 
        site_name: str, 
        credential_id: Optional[int] = None
    ) -> str:
        """
        如果需要则自动获取token
        
        Args:
            site_name: 网站名称
            credential_id: 指定的凭证ID（可选）
            
        Returns:
            有效的token字符串
            
        Raises:
            AutoTokenAcquisitionError: Token获取失败
        """
        ...


class IAccountSelectionStrategy(Protocol):
    """
    账号选择策略接口
    
    定义账号选择的策略方法
    """
    
    async def select_account(
        self, 
        site_name: str, 
        exclude_accounts: Optional[List[str]] = None
    ) -> Optional[AccountCredentialDTO]:
        """
        选择用于登录的账号
        
        Args:
            site_name: 网站名称
            exclude_accounts: 需要排除的账号列表
            
        Returns:
            选中的账号凭证DTO，无可用账号时返回None
        """
        ...


class IAutoLoginService(Protocol):
    """
    自动登录服务接口
    
    定义自动登录的核心方法
    """
    
    async def login_and_get_token(
        self, 
        credential: AccountCredentialDTO
    ) -> str:
        """
        执行自动登录并返回token
        
        Args:
            credential: 账号凭证DTO
            
        Returns:
            登录成功后的token字符串
            
        Raises:
            LoginFailedError: 登录失败
            NetworkError: 网络错误
            TokenError: Token获取失败
        """
        ...


class ITokenService(Protocol):
    """
    Token 服务接口
    
    定义 Token 管理的核心方法
    """
    
    async def get_token(self, site_name: str) -> Optional[str]:
        """
        获取指定站点的 Token
        
        Args:
            site_name: 站点名称
            
        Returns:
            Token 字符串，不存在或已过期时返回 None
        """
        ...
    
    async def save_token(self, site_name: str, token: str, expires_in: int) -> None:
        """
        保存 Token
        
        Args:
            site_name: 站点名称
            token: Token 字符串
            expires_in: 过期时间（秒）
        """
        ...
    
    async def delete_token(self, site_name: str) -> None:
        """
        删除 Token
        
        Args:
            site_name: 站点名称
        """
        ...


class IBrowserService(Protocol):
    """
    浏览器服务接口
    
    定义浏览器管理的核心方法
    """
    
    async def get_browser(self) -> Any:
        """
        获取浏览器实例
        
        Returns:
            浏览器实例对象
        """
        ...
    
    async def close_browser(self) -> None:
        """
        关闭浏览器
        """
        ...


class ICaptchaService(Protocol):
    """
    验证码服务接口
    
    定义验证码识别的核心方法
    """
    
    def recognize(self, image_data: bytes) -> str:
        """
        识别验证码
        
        Args:
            image_data: 验证码图片的二进制数据
            
        Returns:
            识别出的验证码文本
            
        Raises:
            CaptchaRecognitionError: 验证码识别失败
        """
        ...


class IMonitorService(Protocol):
    """
    监控服务接口
    
    定义任务监控和告警的核心方法
    """
    
    def get_task_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Args:
            hours: 统计最近多少小时的数据
            
        Returns:
            统计信息字典
        """
        ...
    
    def check_stuck_tasks(self, timeout_minutes: int = 30) -> List[Any]:
        """
        检查卡住的任务
        
        Args:
            timeout_minutes: 超时分钟数
            
        Returns:
            卡住的任务列表
        """
        ...
    
    def check_high_failure_rate(self, threshold: float = 0.5, min_tasks: int = 10) -> Dict[str, float]:
        """
        检查高失败率的任务类型
        
        Args:
            threshold: 失败率阈值
            min_tasks: 最小任务数
            
        Returns:
            高失败率任务类型字典
        """
        ...
    
    def send_alert(self, title: str, message: str, level: str = "warning") -> None:
        """
        发送告警
        
        Args:
            title: 告警标题
            message: 告警消息
            level: 告警级别
        """
        ...


class ISecurityService(Protocol):
    """
    安全服务接口
    
    定义数据加密解密和脱敏的核心方法
    """
    
    def encrypt(self, text: str) -> str:
        """
        加密文本
        
        Args:
            text: 要加密的文本
            
        Returns:
            加密后的文本
        """
        ...
    
    def decrypt(self, encrypted_text: str) -> str:
        """
        解密文本
        
        Args:
            encrypted_text: 加密的文本
            
        Returns:
            解密后的文本
        """
        ...
    
    def mask_sensitive_data(self, data: dict, keys: list = None) -> dict:
        """
        脱敏敏感数据
        
        Args:
            data: 要脱敏的数据字典
            keys: 敏感字段列表
            
        Returns:
            脱敏后的数据字典
        """
        ...
    
    def encrypt_config(self, config: dict) -> dict:
        """
        加密配置中的敏感字段
        
        Args:
            config: 配置字典
            
        Returns:
            加密后的配置字典
        """
        ...
    
    def decrypt_config(self, config: dict) -> dict:
        """
        解密配置中的敏感字段
        
        Args:
            config: 加密的配置字典
            
        Returns:
            解密后的配置字典
        """
        ...


class IValidatorService(Protocol):
    """
    验证服务接口
    
    定义数据验证和清洗的核心方法
    """
    
    def validate_case_number(self, case_number: str) -> bool:
        """
        校验案号格式
        
        Args:
            case_number: 案号字符串
            
        Returns:
            是否为有效案号
        """
        ...
    
    def normalize_case_number(self, case_number: str) -> str:
        """
        规范化案号
        
        Args:
            case_number: 原始案号
            
        Returns:
            规范化后的案号
        """
        ...
    
    def validate_file(self, file_path: str, expected_extensions: list = None) -> Dict[str, Any]:
        """
        校验文件
        
        Args:
            file_path: 文件路径
            expected_extensions: 期望的文件扩展名列表
            
        Returns:
            验证结果字典
        """
        ...
    
    def clean_text(self, text: str) -> str:
        """
        清洗文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        ...
    
    def extract_case_numbers(self, text: str) -> list:
        """
        从文本中提取所有案号
        
        Args:
            text: 包含案号的文本
            
        Returns:
            案号列表
        """
        ...


class IContractPaymentService(Protocol):
    """
    合同收款服务接口

    定义合同收款管理的核心方法
    """

    def list_payments(
        self,
        contract_id: Optional[int] = None,
        invoice_status: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        user: Optional[Any] = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        获取收款列表

        Args:
            contract_id: 合同 ID（可选）
            invoice_status: 开票状态筛选（可选）
            start_date: 开始日期筛选（可选）
            end_date: 结束日期筛选（可选）
            user: 当前用户
            perm_open_access: 是否开放访问权限

        Returns:
            收款记录查询集
        """
        ...

    def get_payment(
        self,
        payment_id: int,
        user: Optional[Any] = None,
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
        received_at: Optional[Any] = None,
        invoice_status: Optional[str] = None,
        invoiced_amount: Optional[Any] = None,
        note: Optional[str] = None,
        user: Optional[Any] = None,
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
        data: Dict[str, Any],
        user: Optional[Any] = None,
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
        user: Optional[Any] = None,
        confirm: bool = False,
    ) -> Dict[str, bool]:
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


class ICaseLogService(Protocol):
    """
    案件日志服务接口

    定义案件日志管理的核心方法
    """

    def list_logs(
        self,
        case_id: Optional[int] = None,
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> Any:
        """
        获取日志列表

        Args:
            case_id: 案件 ID（可选，用于过滤）
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
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
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
        user: Optional[Any] = None,
        reminder_type: Optional[str] = None,
        reminder_time: Optional[Any] = None,
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
        data: Dict[str, Any],
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
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
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> Dict[str, bool]:
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
        files: List[Any],
        user: Optional[Any] = None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> Dict[str, int]:
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


class ICourtDocumentService(Protocol):
    """
    法院文书服务接口
    
    定义法院文书管理的核心方法
    """
    
    def create_document_from_api_data(
        self,
        scraper_task_id: int,
        api_data: Dict[str, Any],
        case_id: Optional[int] = None
    ) -> Any:
        """
        从API数据创建文书记录
        
        Args:
            scraper_task_id: 爬虫任务ID
            api_data: API返回的文书数据
            case_id: 关联案件ID（可选）
            
        Returns:
            创建的文书记录
            
        Raises:
            ValidationException: 数据验证失败
            NotFoundError: 爬虫任务不存在
        """
        ...
    
    def update_download_status(
        self,
        document_id: int,
        status: str,
        local_file_path: Optional[str] = None,
        file_size: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Any:
        """
        更新文书下载状态
        
        Args:
            document_id: 文书记录ID
            status: 下载状态
            local_file_path: 本地文件路径（可选）
            file_size: 文件大小（可选）
            error_message: 错误信息（可选）
            
        Returns:
            更新后的文书记录
            
        Raises:
            NotFoundError: 文书记录不存在
            ValidationException: 状态值无效
        """
        ...
    
    def get_documents_by_task(
        self,
        scraper_task_id: int
    ) -> List[Any]:
        """
        获取任务的所有文书记录
        
        Args:
            scraper_task_id: 爬虫任务ID
            
        Returns:
            文书记录列表
        """
        ...
    
    def get_document_by_id(
        self,
        document_id: int
    ) -> Optional[Any]:
        """
        根据ID获取文书记录
        
        Args:
            document_id: 文书记录ID
            
        Returns:
            文书记录，不存在时返回 None
        """
        ...


class IPreservationQuoteService(Protocol):
    """
    财产保全询价服务接口
    
    定义财产保全询价的核心方法
    """
    
    def create_quote(
        self,
        case_name: str,
        target_amount: Any,  # Decimal
        applicant_name: str,
        respondent_name: str,
        court_name: str,
        case_type: str = "财产保全",
        **kwargs
    ) -> Any:
        """
        创建询价任务
        
        Args:
            case_name: 案件名称
            target_amount: 保全金额
            applicant_name: 申请人姓名
            respondent_name: 被申请人姓名
            court_name: 法院名称
            case_type: 案件类型
            **kwargs: 其他参数
            
        Returns:
            创建的询价记录
            
        Raises:
            ValidationException: 数据验证失败
        """
        ...
    
    def execute_quote(
        self,
        quote_id: int,
        force_refresh_token: bool = False
    ) -> Dict[str, Any]:
        """
        执行询价任务
        
        Args:
            quote_id: 询价记录ID
            force_refresh_token: 是否强制刷新Token
            
        Returns:
            询价结果字典
            
        Raises:
            NotFoundError: 询价记录不存在
            BusinessException: 询价执行失败
        """
        ...
    
    def get_quote_by_id(self, quote_id: int) -> Optional[Any]:
        """
        根据ID获取询价记录
        
        Args:
            quote_id: 询价记录ID
            
        Returns:
            询价记录，不存在时返回 None
        """
        ...
    
    def list_quotes(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取询价记录列表
        
        Args:
            status: 状态筛选（可选）
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            包含记录列表和总数的字典
        """
        ...


class IDocumentProcessingService(Protocol):
    """
    文档处理服务接口
    
    定义文档处理的核心方法
    """
    
    def extract_text_from_pdf(
        self,
        file_path: str,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从PDF文件提取文本
        
        Args:
            file_path: PDF文件路径
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本和预览图的字典
            
        Raises:
            ValidationException: 文件格式不支持
            FileNotFoundError: 文件不存在
        """
        ...
    
    def extract_text_from_docx(
        self,
        file_path: str,
        limit: Optional[int] = None
    ) -> str:
        """
        从DOCX文件提取文本
        
        Args:
            file_path: DOCX文件路径
            limit: 文本长度限制
            
        Returns:
            提取的文本内容
            
        Raises:
            ValidationException: 文件格式不支持
            FileNotFoundError: 文件不存在
        """
        ...
    
    def extract_text_from_image(
        self,
        file_path: str,
        limit: Optional[int] = None
    ) -> str:
        """
        从图片文件提取文本（OCR）
        
        Args:
            file_path: 图片文件路径
            limit: 文本长度限制
            
        Returns:
            OCR识别的文本内容
            
        Raises:
            ValidationException: 文件格式不支持
            FileNotFoundError: 文件不存在
        """
        ...
    
    def process_uploaded_document(
        self,
        uploaded_file: Any,
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        处理上传的文档
        
        Args:
            uploaded_file: 上传的文件对象
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本和预览信息的字典
            
        Raises:
            ValidationException: 文件格式不支持
        """
        ...


class IAutoNamerService(Protocol):
    """
    自动命名服务接口
    
    定义自动命名的核心方法
    """
    
    def generate_filename(
        self,
        document_content: str,
        prompt: Optional[str] = None,
        model: str = "qwen3:0.6b"
    ) -> str:
        """
        根据文档内容生成文件名
        
        Args:
            document_content: 文档文本内容
            prompt: 自定义提示词（可选）
            model: 使用的AI模型
            
        Returns:
            生成的文件名建议
            
        Raises:
            ValidationException: 内容为空或无效
            BusinessException: AI服务调用失败
        """
        ...
    
    def process_document_for_naming(
        self,
        uploaded_file: Any,
        prompt: Optional[str] = None,
        model: str = "qwen3:0.6b",
        limit: Optional[int] = None,
        preview_page: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        处理文档并生成命名建议
        
        Args:
            uploaded_file: 上传的文件对象
            prompt: 自定义提示词（可选）
            model: 使用的AI模型
            limit: 文本长度限制
            preview_page: 预览页码
            
        Returns:
            包含文本内容、命名建议等信息的字典
            
        Raises:
            ValidationException: 文件格式不支持
            BusinessException: 处理失败
        """
        ...


class IPerformanceMonitorService(Protocol):
    """
    性能监控服务接口
    
    定义性能监控的核心方法
    """
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        获取系统性能指标
        
        Returns:
            系统性能指标字典，包含CPU、内存、磁盘等信息
        """
        ...
    
    def get_token_acquisition_metrics(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取Token获取性能指标
        
        Args:
            hours: 统计最近多少小时的数据
            
        Returns:
            Token获取性能指标字典
        """
        ...
    
    def get_api_performance_metrics(
        self,
        api_name: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        获取API性能指标
        
        Args:
            api_name: API名称（可选，为空时返回所有API）
            hours: 统计最近多少小时的数据
            
        Returns:
            API性能指标字典
        """
        ...
    
    def record_performance_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None
    ) -> None:
        """
        记录性能指标
        
        Args:
            metric_name: 指标名称
            value: 指标值
            tags: 标签字典（可选）
        """
        ...


class IPermissionService(Protocol):
    """
    权限服务接口

    定义权限检查的公共方法，供其他模块使用
    """

    def can_access_case(self, user_id: int, case_id: int) -> bool:
        """
        检查用户是否可以访问案件

        Args:
            user_id: 用户 ID
            case_id: 案件 ID

        Returns:
            是否有权限访问
        """
        ...

    def can_modify_case(self, user_id: int, case_id: int) -> bool:
        """
        检查用户是否可以修改案件

        Args:
            user_id: 用户 ID
            case_id: 案件 ID

        Returns:
            是否有权限修改
        """
        ...

    def can_access_contract(self, user_id: int, contract_id: int) -> bool:
        """
        检查用户是否可以访问合同

        Args:
            user_id: 用户 ID
            contract_id: 合同 ID

        Returns:
            是否有权限访问
        """
        ...

    def has_permission(self, user_id: int, permission: str) -> bool:
        """
        检查用户是否有指定权限

        Args:
            user_id: 用户 ID
            permission: 权限名称

        Returns:
            是否有权限
        """
        ...


class IOrganizationService(Protocol):
    """
    组织服务接口

    定义组织（律所、团队）相关的公共方法
    """

    def get_law_firm(self, law_firm_id: int) -> Optional[Dict[str, Any]]:
        """
        获取律所信息

        Args:
            law_firm_id: 律所 ID

        Returns:
            律所信息字典，不存在时返回 None
        """
        ...

    def get_team(self, team_id: int) -> Optional[Dict[str, Any]]:
        """
        获取团队信息

        Args:
            team_id: 团队 ID

        Returns:
            团队信息字典，不存在时返回 None
        """
        ...

    def get_lawyers_in_organization(self, organization_id: int) -> List[LawyerDTO]:
        """
        获取组织内的所有律师

        Args:
            organization_id: 组织 ID

        Returns:
            律师 DTO 列表
        """
        ...

    def get_all_credentials_internal(self) -> List[AccountCredentialDTO]:
        """
        内部方法：获取所有账号凭证
        
        Returns:
            所有账号凭证的 DTO 列表
        """
        ...

    def get_credential_internal(self, credential_id: int) -> AccountCredentialDTO:
        """
        内部方法：获取账号凭证（无权限检查）
        
        Args:
            credential_id: 凭证 ID
            
        Returns:
            账号凭证 DTO
            
        Raises:
            NotFoundError: 凭证不存在
        """
        ...

class ILawyerService(Protocol):
    """
    律师服务接口

    定义律师服务的公共方法，供其他模块使用
    """

    def get_lawyer(self, lawyer_id: int) -> Optional[LawyerDTO]:
        """
        获取律师信息

        Args:
            lawyer_id: 律师 ID

        Returns:
            律师 DTO，不存在时返回 None
        """
        ...

    def get_lawyers_by_ids(self, lawyer_ids: List[int]) -> List[LawyerDTO]:
        """
        批量获取律师信息

        Args:
            lawyer_ids: 律师 ID 列表

        Returns:
            律师 DTO 列表
        """
        ...

    def get_team_members(self, team_id: int) -> List[LawyerDTO]:
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
        验证律师是否有效（is_active=True）

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

    def get_admin_lawyer_internal(self) -> Optional[LawyerDTO]:
        """
        内部方法：获取管理员律师
        
        Returns:
            管理员律师 DTO，不存在时返回 None
        """
        ...

    def get_all_lawyer_names_internal(self) -> List[str]:
        """
        内部方法：获取所有律师姓名
        
        Returns:
            所有律师的姓名列表
        """
        ...


class ILawFirmService(Protocol):
    """
    律所服务接口

    定义律所服务的公共方法，供其他模块使用
    """

    def get_lawfirm(self, lawfirm_id: int) -> Optional[LawFirmDTO]:
        """
        获取律所信息

        Args:
            lawfirm_id: 律所 ID

        Returns:
            律所 DTO，不存在时返回 None
        """
        ...

    def get_lawfirms_by_ids(self, lawfirm_ids: List[int]) -> List[LawFirmDTO]:
        """
        批量获取律所信息

        Args:
            lawfirm_ids: 律所 ID 列表

        Returns:
            律所 DTO 列表
        """
        ...


class IClientService(Protocol):
    """
    客户服务接口

    定义客户服务的公共方法，供其他模块使用
    """

    def get_client(self, client_id: int) -> Optional[ClientDTO]:
        """
        获取客户信息

        Args:
            client_id: 客户 ID

        Returns:
            客户 DTO，不存在时返回 None
        """
        ...

    def get_clients_by_ids(self, client_ids: List[int]) -> List[ClientDTO]:
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

    def get_client_by_name(self, name: str) -> Optional[ClientDTO]:
        """
        根据名称获取客户

        Args:
            name: 客户名称

        Returns:
            客户 DTO，不存在时返回 None
        """
        ...

    def get_all_clients_internal(self) -> List[ClientDTO]:
        """
        内部方法：获取所有客户
        
        Returns:
            所有客户的 DTO 列表
        """
        ...

    def search_clients_by_name_internal(
        self, 
        name: str,
        exact_match: bool = False
    ) -> List[ClientDTO]:
        """
        内部方法：根据名称搜索客户
        
        Args:
            name: 客户名称或名称片段
            exact_match: 是否精确匹配（默认 False，支持模糊匹配）
            
        Returns:
            匹配的客户 DTO 列表
        """
        ...


class IContractService(Protocol):
    """
    合同服务接口

    定义合同服务的公共方法，供其他模块使用
    """

    def get_contract(self, contract_id: int) -> Optional[ContractDTO]:
        """
        获取合同信息

        Args:
            contract_id: 合同 ID

        Returns:
            合同 DTO，不存在时返回 None
        """
        ...

    def get_contract_stages(self, contract_id: int) -> List[str]:
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
        验证合同是否有效（状态为 active）

        Args:
            contract_id: 合同 ID

        Returns:
            合同是否有效
        """
        ...

    def get_contracts_by_ids(self, contract_ids: List[int]) -> List[ContractDTO]:
        """
        批量获取合同信息

        Args:
            contract_ids: 合同 ID 列表

        Returns:
            合同 DTO 列表
        """
        ...

    def get_contract_assigned_lawyer_id(self, contract_id: int) -> Optional[int]:
        """
        获取合同的主办律师 ID（使用 primary_lawyer）

        Args:
            contract_id: 合同 ID

        Returns:
            主办律师 ID，合同不存在或无主办律师时返回 None
        """
        ...

    def get_contract_lawyers(self, contract_id: int) -> List[LawyerDTO]:
        """
        获取合同的所有律师

        Args:
            contract_id: 合同 ID

        Returns:
            律师 DTO 列表，按 is_primary 降序、order 升序排列

        Raises:
            NotFoundError: 合同不存在
        """
        ...

    def get_all_parties(self, contract_id: int) -> List[Dict[str, Any]]:
        """
        获取合同及其补充协议的所有当事人

        聚合 ContractParty 和 SupplementaryAgreementParty 中的所有 Client，
        按 client_id 去重，返回包含来源标识的当事人列表。

        Args:
            contract_id: 合同 ID

        Returns:
            当事人列表，每个元素包含:
            - id: Client ID
            - name: Client 名称
            - source: 来源 ("contract" 或 "supplementary")

        Raises:
            NotFoundError: 合同不存在
        """
        ...


class ICaseService(Protocol):
    """
    案件服务接口

    定义案件服务的公共方法，供其他模块使用
    """

    def get_case(self, case_id: int) -> Optional[CaseDTO]:
        """
        获取案件信息

        Args:
            case_id: 案件 ID

        Returns:
            案件 DTO，不存在时返回 None
        """
        ...

    def get_cases_by_contract(self, contract_id: int) -> List[CaseDTO]:
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

    def get_cases_by_ids(self, case_ids: List[int]) -> List[CaseDTO]:
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
        验证案件是否有效（状态为 active）

        Args:
            case_id: 案件 ID

        Returns:
            案件是否有效
        """
        ...

    def get_case_current_stage(self, case_id: int) -> Optional[str]:
        """
        获取案件的当前阶段

        Args:
            case_id: 案件 ID

        Returns:
            当前阶段，案件不存在时返回 None
        """
        ...

    def create_case(self, data: Dict[str, Any]) -> CaseDTO:
        """
        创建案件

        Args:
            data: 案件数据字典，包含：
                - name: 案件名称（必填）
                - contract_id: 合同 ID（可选）
                - is_archived: 是否已建档（可选，默认 False）
                - case_type: 案件类型（可选）
                - target_amount: 涉案金额（可选）
                - cause_of_action: 案由（可选）
                - current_stage: 当前阶段（可选）

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

    def create_case_party(self, case_id: int, client_id: int, legal_status: Optional[str] = None) -> bool:
        """
        创建案件当事人

        Args:
            case_id: 案件 ID
            client_id: 客户 ID
            legal_status: 诉讼地位（可选）

        Returns:
            是否创建成功
        """
        ...

    def get_user_extra_case_access(self, user_id: int) -> List[int]:
        """
        获取用户的额外案件访问授权

        Args:
            user_id: 用户 ID

        Returns:
            用户有额外访问权限的案件 ID 列表
        """
        ...

    def get_case_by_id_internal(self, case_id: int) -> Optional[CaseDTO]:
        """
        内部方法：获取案件信息（无权限检查）
        
        Args:
            case_id: 案件 ID
            
        Returns:
            案件 DTO，不存在时返回 None
        """
        ...

    def search_cases_by_party_internal(
        self, 
        party_names: List[str], 
        status: Optional[str] = None
    ) -> List[CaseDTO]:
        """
        内部方法：根据当事人名称搜索案件
        
        Args:
            party_names: 当事人名称列表
            status: 案件状态筛选（可选）
            
        Returns:
            匹配的案件 DTO 列表
        """
        ...

    def get_case_numbers_by_case_internal(self, case_id: int) -> List[str]:
        """
        内部方法：获取案件的所有案号
        
        Args:
            case_id: 案件 ID
            
        Returns:
            案号字符串列表
        """
        ...

    def get_case_party_names_internal(self, case_id: int) -> List[str]:
        """
        内部方法：获取案件的所有当事人名称
        
        Args:
            case_id: 案件 ID
            
        Returns:
            当事人名称列表
        """
        ...

    def search_cases_by_case_number_internal(
        self, 
        case_number: str
    ) -> List[CaseDTO]:
        """
        内部方法：根据案号搜索案件
        
        Args:
            case_number: 案号字符串
            
        Returns:
            匹配的案件 DTO 列表
        """
        ...

    def create_case_log_internal(
        self,
        case_id: int,
        content: str,
        user_id: Optional[int] = None
    ) -> int:
        """
        内部方法：创建案件日志，返回日志ID
        
        Args:
            case_id: 案件 ID
            content: 日志内容
            user_id: 用户 ID（可选）
            
        Returns:
            创建的日志 ID
            
        Raises:
            NotFoundError: 案件不存在
        """
        ...

    def add_case_log_attachment_internal(
        self,
        case_log_id: int,
        file_path: str,
        file_name: str
    ) -> bool:
        """
        内部方法：添加案件日志附件
        
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

    def add_case_number_internal(
        self,
        case_id: int,
        case_number: str,
        user_id: Optional[int] = None
    ) -> bool:
        """
        内部方法：为案件添加案号（如果不存在）
        
        Args:
            case_id: 案件 ID
            case_number: 案号字符串
            user_id: 操作用户 ID（可选）
            
        Returns:
            是否添加成功（已存在也返回 True）
        """
        ...


class ICaseNumberService(Protocol):
    """
    案号服务接口
    
    定义案号管理的核心方法，供跨模块调用
    """
    
    def list_numbers_internal(self, case_id: int) -> List[Any]:
        """
        内部方法：获取案件的所有案号
        
        Args:
            case_id: 案件 ID
            
        Returns:
            案号对象列表
        """
        ...
    
    def create_number_internal(
        self,
        case_id: int,
        number: str,
        remarks: Optional[str] = None
    ) -> Any:
        """
        内部方法：创建案号
        
        Args:
            case_id: 案件 ID
            number: 案号
            remarks: 备注（可选）
            
        Returns:
            创建的案号对象
        """
        ...
    
    def normalize_case_number(self, number: str) -> str:
        """
        规范化案号：统一括号、删除空格
        
        Args:
            number: 原始案号
            
        Returns:
            规范化后的案号
        """
        ...


class IAutomationService(Protocol):
    """
    自动化服务接口
    
    定义自动化模块对外提供的核心方法
    """
    
    def create_token_acquisition_history_internal(self, history_data: Dict[str, Any]) -> Any:
        """
        创建Token获取历史记录（内部方法）
        
        Args:
            history_data: 历史记录数据
            
        Returns:
            创建的历史记录对象
        """
        ...


class ICaseChatService(Protocol):
    """
    案件群聊服务接口
    
    定义案件群聊管理的核心方法
    """
    
    def send_message_to_case_chat(
        self,
        case_id: int,
        message: str,
        files: Optional[List[str]] = None
    ) -> bool:
        """
        发送消息到案件群聊
        
        Args:
            case_id: 案件 ID
            message: 消息内容
            files: 附件文件路径列表（可选）
            
        Returns:
            是否发送成功
            
        Raises:
            NotFoundError: 案件不存在或未配置群聊
            BusinessException: 消息发送失败
        """
        ...
    
    def get_case_chat_id(self, case_id: int) -> Optional[str]:
        """
        获取案件的群聊ID
        
        Args:
            case_id: 案件 ID
            
        Returns:
            群聊 ID，未配置时返回 None
        """
        ...


class ICourtSMSService(Protocol):
    """
    法院短信处理服务接口
    
    定义法院短信处理的核心方法
    """
    
    def submit_sms(
        self,
        content: str,
        received_at: Optional[Any] = None,
        sender: Optional[str] = None
    ) -> Any:
        """
        提交短信内容
        
        Args:
            content: 短信内容
            received_at: 收到时间（可选，默认当前时间）
            sender: 发送方号码（可选）
            
        Returns:
            创建的 CourtSMS 记录
            
        Raises:
            ValidationException: 短信内容为空
        """
        ...
    
    def get_sms_detail(self, sms_id: int) -> Any:
        """
        获取短信处理详情
        
        Args:
            sms_id: 短信记录ID
            
        Returns:
            短信记录对象
            
        Raises:
            NotFoundError: 短信记录不存在
        """
        ...
    
    def list_sms(
        self,
        status: Optional[str] = None,
        sms_type: Optional[str] = None,
        has_case: Optional[bool] = None,
        date_from: Optional[Any] = None,
        date_to: Optional[Any] = None
    ) -> List[Any]:
        """
        查询短信列表
        
        Args:
            status: 状态筛选（可选）
            sms_type: 短信类型筛选（可选）
            has_case: 是否关联案件筛选（可选）
            date_from: 开始日期筛选（可选）
            date_to: 结束日期筛选（可选）
            
        Returns:
            短信记录列表
        """
        ...
    
    def assign_case(self, sms_id: int, case_id: int) -> Any:
        """
        手动指定案件
        
        Args:
            sms_id: 短信记录ID
            case_id: 案件ID
            
        Returns:
            更新后的短信记录
            
        Raises:
            NotFoundError: 短信记录或案件不存在
        """
        ...
    
    def retry_processing(self, sms_id: int) -> Any:
        """
        重新处理短信
        
        Args:
            sms_id: 短信记录ID
            
        Returns:
            重置后的短信记录
            
        Raises:
            NotFoundError: 短信记录不存在
        """
        ...


# ============================================================
# 服务定位器
# 提供跨模块服务的统一获取入口
# ============================================================

class ServiceLocator:
    """
    服务定位器
    用于获取跨模块服务实例，实现依赖注入
    """

    _services: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        """注册服务"""
        cls._services[name] = service

    @classmethod
    def get(cls, name: str) -> Optional[Any]:
        """获取服务"""
        return cls._services.get(name)

    @classmethod
    def clear(cls, name: Optional[str] = None) -> None:
        """
        清除服务（用于测试）

        Args:
            name: 服务名称，如果为 None 则清除所有服务
        """
        if name is not None:
            cls._services.pop(name, None)
        else:
            cls._services.clear()

    @classmethod
    def get_lawyer_service(cls) -> ILawyerService:
        """获取律师服务"""
        service = cls.get("lawyer_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.organization.services import LawyerServiceAdapter
            service = LawyerServiceAdapter()
            cls.register("lawyer_service", service)
        return service

    @classmethod
    def get_client_service(cls) -> IClientService:
        """获取客户服务"""
        service = cls.get("client_service")
        if service is None:
            from apps.client.services import ClientServiceAdapter
            service = ClientServiceAdapter()
            cls.register("client_service", service)
        return service

    @classmethod
    def get_contract_service(cls) -> IContractService:
        """获取合同服务"""
        service = cls.get("contract_service")
        if service is None:
            from apps.contracts.services import ContractServiceAdapter
            service = ContractServiceAdapter()
            cls.register("contract_service", service)
        return service

    @classmethod
    def get_case_service(cls) -> ICaseService:
        """
        获取案件服务

        Returns:
            ICaseService 实例
        """
        service = cls.get("case_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.cases.services import CaseServiceAdapter
            service = CaseServiceAdapter()
            cls.register("case_service", service)
        return service

    @classmethod
    def get_lawfirm_service(cls) -> ILawFirmService:
        """
        获取律所服务

        Returns:
            ILawFirmService 实例
        """
        service = cls.get("lawfirm_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.organization.services import LawFirmServiceAdapter
            service = LawFirmServiceAdapter()
            cls.register("lawfirm_service", service)
        return service

    @classmethod
    def get_auto_token_acquisition_service(cls) -> IAutoTokenAcquisitionService:
        """
        获取自动Token获取服务

        Returns:
            IAutoTokenAcquisitionService 实例
        """
        service = cls.get("auto_token_acquisition_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
            service = AutoTokenAcquisitionService()
            cls.register("auto_token_acquisition_service", service)
        return service

    @classmethod
    def get_account_selection_strategy(cls) -> IAccountSelectionStrategy:
        """
        获取账号选择策略服务

        Returns:
            IAccountSelectionStrategy 实例
        """
        service = cls.get("account_selection_strategy")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy
            service = AccountSelectionStrategy()
            cls.register("account_selection_strategy", service)
        return service

    @classmethod
    def get_auto_login_service(cls) -> IAutoLoginService:
        """
        获取自动登录服务

        Returns:
            IAutoLoginService 实例
        """
        service = cls.get("auto_login_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.token.auto_login_service import AutoLoginService
            service = AutoLoginService()
            cls.register("auto_login_service", service)
        return service

    @classmethod
    def get_token_service(cls) -> ITokenService:
        """
        获取 Token 服务

        Returns:
            ITokenService 实例
        """
        service = cls.get("token_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.scraper.core.token_service import TokenServiceAdapter
            service = TokenServiceAdapter()
            cls.register("token_service", service)
        return service

    @classmethod
    def get_browser_service(cls) -> IBrowserService:
        """
        获取浏览器服务

        Returns:
            IBrowserService 实例
        """
        service = cls.get("browser_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.scraper.core.browser_service import BrowserServiceAdapter
            service = BrowserServiceAdapter()
            cls.register("browser_service", service)
        return service

    @classmethod
    def get_captcha_service(cls) -> ICaptchaService:
        """
        获取验证码服务

        Returns:
            ICaptchaService 实例
        """
        service = cls.get("captcha_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.captcha.captcha_recognition_service import CaptchaServiceAdapter
            service = CaptchaServiceAdapter()
            cls.register("captcha_service", service)
        return service

    @classmethod
    def get_court_document_service(cls) -> ICourtDocumentService:
        """
        获取法院文书服务

        Returns:
            ICourtDocumentService 实例
        """
        service = cls.get("court_document_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter
            service = CourtDocumentServiceAdapter()
            cls.register("court_document_service", service)
        return service

    @classmethod
    def get_monitor_service(cls) -> IMonitorService:
        """
        获取监控服务

        Returns:
            IMonitorService 实例
        """
        service = cls.get("monitor_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.scraper.core.monitor_service import MonitorServiceAdapter
            service = MonitorServiceAdapter()
            cls.register("monitor_service", service)
        return service

    @classmethod
    def get_security_service(cls) -> ISecurityService:
        """
        获取安全服务

        Returns:
            ISecurityService 实例
        """
        service = cls.get("security_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.scraper.core.security_service import SecurityServiceAdapter
            service = SecurityServiceAdapter()
            cls.register("security_service", service)
        return service

    @classmethod
    def get_validator_service(cls) -> IValidatorService:
        """
        获取验证服务

        Returns:
            IValidatorService 实例
        """
        service = cls.get("validator_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter
            service = ValidatorServiceAdapter()
            cls.register("validator_service", service)
        return service

    @classmethod
    def get_contract_payment_service(cls) -> IContractPaymentService:
        """
        获取合同收款服务

        Returns:
            IContractPaymentService 实例
        """
        service = cls.get("contract_payment_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.contracts.services.contract_payment_service import ContractPaymentService
            service = ContractPaymentService()
            cls.register("contract_payment_service", service)
        return service

    @classmethod
    def get_caselog_service(cls) -> ICaseLogService:
        """
        获取案件日志服务

        Returns:
            ICaseLogService 实例
        """
        service = cls.get("caselog_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.cases.services.caselog_service import CaseLogService
            service = CaseLogService()
            cls.register("caselog_service", service)
        return service

    @classmethod
    def get_preservation_quote_service(cls) -> IPreservationQuoteService:
        """
        获取财产保全询价服务

        Returns:
            IPreservationQuoteService 实例
        """
        service = cls.get("preservation_quote_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.insurance.preservation_quote_service_adapter import PreservationQuoteServiceAdapter
            service = PreservationQuoteServiceAdapter()
            cls.register("preservation_quote_service", service)
        return service

    @classmethod
    def get_document_processing_service(cls) -> IDocumentProcessingService:
        """
        获取文档处理服务

        Returns:
            IDocumentProcessingService 实例
        """
        service = cls.get("document_processing_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.document.document_processing_service_adapter import DocumentProcessingServiceAdapter
            service = DocumentProcessingServiceAdapter()
            cls.register("document_processing_service", service)
        return service

    @classmethod
    def get_auto_namer_service(cls) -> IAutoNamerService:
        """
        获取自动命名服务

        Returns:
            IAutoNamerService 实例
        """
        service = cls.get("auto_namer_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter
            service = AutoNamerServiceAdapter()
            cls.register("auto_namer_service", service)
        return service

    @classmethod
    def get_automation_service(cls) -> IAutomationService:
        """
        获取自动化服务

        Returns:
            IAutomationService 实例
        """
        service = cls.get("automation_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.automation_service_adapter import AutomationServiceAdapter
            service = AutomationServiceAdapter()
            cls.register("automation_service", service)
        return service

    @classmethod
    def get_performance_monitor_service(cls) -> IPerformanceMonitorService:
        """
        获取性能监控服务

        Returns:
            IPerformanceMonitorService 实例
        """
        service = cls.get("performance_monitor_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.token.performance_monitor_service_adapter import PerformanceMonitorServiceAdapter
            service = PerformanceMonitorServiceAdapter()
            cls.register("performance_monitor_service", service)
        return service

    @classmethod
    def get_court_sms_service(cls) -> ICourtSMSService:
        """
        获取法院短信处理服务

        Returns:
            ICourtSMSService 实例
        """
        service = cls.get("court_sms_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.automation.services.sms.court_sms_service import CourtSMSService
            service = CourtSMSService()
            cls.register("court_sms_service", service)
        return service

    @classmethod
    def get_case_chat_service(cls) -> ICaseChatService:
        """
        获取案件群聊服务

        Returns:
            ICaseChatService 实例
        """
        service = cls.get("case_chat_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.cases.services.case_chat_service import CaseChatService
            service = CaseChatService()
            cls.register("case_chat_service", service)
        return service

    @classmethod
    def get_organization_service(cls) -> IOrganizationService:
        """
        获取组织服务

        Returns:
            IOrganizationService 实例
        """
        service = cls.get("organization_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.organization.services import OrganizationServiceAdapter
            service = OrganizationServiceAdapter()
            cls.register("organization_service", service)
        return service

    @classmethod
    def get_case_number_service(cls) -> ICaseNumberService:
        """
        获取案号服务

        Returns:
            ICaseNumberService 实例
        """
        service = cls.get("case_number_service")
        if service is None:
            # 延迟导入，避免循环依赖
            from apps.cases.services.case_number_service_adapter import CaseNumberServiceAdapter
            service = CaseNumberServiceAdapter()
            cls.register("case_number_service", service)
        return service


# ============================================================
# 事件总线
# 用于模块间的事件通知，实现松耦合
# ============================================================

class EventBus:
    """
    简单的事件总线
    用于模块间的事件发布和订阅
    """

    _handlers: Dict[str, List[callable]] = {}

    @classmethod
    def subscribe(cls, event_type: str, handler: callable) -> None:
        """订阅事件"""
        if event_type not in cls._handlers:
            cls._handlers[event_type] = []
        cls._handlers[event_type].append(handler)

    @classmethod
    def publish(cls, event_type: str, data: Any = None) -> None:
        """发布事件"""
        handlers = cls._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                import logging
                logging.getLogger("apps").error(f"Event handler error: {e}")

    @classmethod
    def clear(cls, event_type: Optional[str] = None) -> None:
        """清除事件处理器"""
        if event_type:
            cls._handlers.pop(event_type, None)
        else:
            cls._handlers.clear()


# 预定义事件类型
class Events:
    """事件类型常量"""
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_DELETED = "case.deleted"

    CONTRACT_CREATED = "contract.created"
    CONTRACT_UPDATED = "contract.updated"

    PAYMENT_CREATED = "payment.created"
    PAYMENT_UPDATED = "payment.updated"

    USER_TEAM_CHANGED = "user.team_changed"
    CASE_ACCESS_GRANTED = "case.access_granted"
    CASE_ACCESS_REVOKED = "case.access_revoked"
