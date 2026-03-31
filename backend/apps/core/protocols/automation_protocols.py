"""
自动化相关 Protocol 接口定义

包含:IAutoTokenAcquisitionService, IAutoLoginService, ITokenService, IBrowserService,
      ICaptchaService, IAutomationService, ICourtSMSService, ICourtDocumentService,
      ICourtDocumentRecognitionService, IPreservationQuoteService, IDocumentProcessingService,
      IAutoNamerService, IPerformanceMonitorService
"""

from typing import TYPE_CHECKING, Any, Optional, Protocol

from apps.core.dto import AccountCredentialDTO

if TYPE_CHECKING:
    from apps.automation.dtos import CourtTokenDTO
    from apps.core.dto import CourtPleadingSignalsDTO


class IAutoTokenAcquisitionService(Protocol):
    """
    自动Token获取服务接口

    定义自动Token获取的核心方法
    """

    async def acquire_token_if_needed(self, site_name: str, credential_id: int | None = None) -> str:
        """
        如果需要则自动获取token

        Args:
            site_name: 网站名称
            credential_id: 指定的凭证ID(可选)

        Returns:
            有效的token字符串

        Raises:
            AutoTokenAcquisitionError: Token获取失败
        """
        ...


class IAutoLoginService(Protocol):
    """
    自动登录服务接口

    定义自动登录的核心方法
    """

    async def login_and_get_token(self, credential: AccountCredentialDTO) -> str:
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

    async def get_token(self, site_name: str) -> str | None:
        """
        获取指定站点的 Token

        Args:
            site_name: 站点名称

        Returns:
            Token 字符串,不存在或已过期时返回 None
        """
        ...


class ICourtTokenStoreService(Protocol):
    def get_latest_valid_token_internal(
        self,
        *,
        site_name: str,
        account: str | None = None,
        token_prefix: str | None = None,
    ) -> Optional["CourtTokenDTO"]: ...

    def save_token_internal(
        self,
        *,
        site_name: str,
        account: str,
        token: str,
        expires_in: int,
        token_type: str = "Bearer",
        credential_id: int | None = None,
    ) -> None: ...

    async def save_token(self, site_name: str, token: str, expires_in: int) -> None:
        """
        保存 Token

        Args:
            site_name: 站点名称
            token: Token 字符串
            expires_in: 过期时间(秒)
        """
        ...

    async def delete_token(self, site_name: str) -> None:
        """
        删除 Token

        Args:
            site_name: 站点名称
        """
        ...


class ICourtPleadingSignalsService(Protocol):
    def get_signals_internal(self, case_id: int) -> "CourtPleadingSignalsDTO": ...


class IBaoquanTokenService(Protocol):
    async def get_valid_baoquan_token(self, credential_id: int | None = None) -> str: ...


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


class IOcrService(Protocol):
    def extract_text(self, image_bytes: bytes) -> Any: ...


class IAutomationService(Protocol):
    """
    自动化服务接口

    定义自动化模块对外提供的核心方法
    """

    def create_token_acquisition_history_internal(self, history_data: dict[str, Any]) -> Any:
        """
        创建Token获取历史记录(内部方法)

        Args:
            history_data: 历史记录数据

        Returns:
            创建的历史记录对象
        """
        ...


class ICourtSMSService(Protocol):
    """
    法院短信处理服务接口

    定义法院短信处理的核心方法
    """

    def submit_sms(self, content: str, received_at: Any | None = None, sender: str | None = None) -> Any:
        """
        提交短信内容

        Args:
            content: 短信内容
            received_at: 收到时间(可选,默认当前时间)
            sender: 发送方号码(可选)

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
        status: str | None = None,
        sms_type: str | None = None,
        has_case: bool | None = None,
        date_from: Any | None = None,
        date_to: Any | None = None,
    ) -> list[Any]:
        """
        查询短信列表

        Args:
            status: 状态筛选(可选)
            sms_type: 短信类型筛选(可选)
            has_case: 是否关联案件筛选(可选)
            date_from: 开始日期筛选(可选)
            date_to: 结束日期筛选(可选)

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


class ICourtDocumentService(Protocol):
    """
    法院文书服务接口

    定义法院文书管理的核心方法
    """

    def create_document_from_api_data(
        self, scraper_task_id: int, api_data: dict[str, Any], case_id: int | None = None
    ) -> Any:
        """
        从API数据创建文书记录

        Args:
            scraper_task_id: 爬虫任务ID
            api_data: API返回的文书数据
            case_id: 关联案件ID(可选)

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
        local_file_path: str | None = None,
        file_size: int | None = None,
        error_message: str | None = None,
    ) -> Any:
        """
        更新文书下载状态

        Args:
            document_id: 文书记录ID
            status: 下载状态
            local_file_path: 本地文件路径(可选)
            file_size: 文件大小(可选)
            error_message: 错误信息(可选)

        Returns:
            更新后的文书记录

        Raises:
            NotFoundError: 文书记录不存在
            ValidationException: 状态值无效
        """
        ...

    def get_documents_by_task(self, scraper_task_id: int) -> list[Any]:
        """
        获取任务的所有文书记录

        Args:
            scraper_task_id: 爬虫任务ID

        Returns:
            文书记录列表
        """
        ...

    def get_document_by_id(self, document_id: int) -> Any | None:
        """
        根据ID获取文书记录

        Args:
            document_id: 文书记录ID

        Returns:
            文书记录,不存在时返回 None
        """
        ...


class ICourtDocumentRecognitionService(Protocol):
    """
    法院文书智能识别服务接口

    定义法院文书识别的核心方法,支持传票、执行裁定书等文书的
    类型识别、关键信息提取和案件绑定.

    Requirements: 7.1, 7.2, 7.3
    """

    def recognize_document(self, file_path: str, user: Any | None = None) -> Any:
        """
        识别文书并绑定案件

        完整的识别流程:
        1. 从文件提取文本(PDF直接提取或OCR)
        2. 使用 AI 分类文书类型
        3. 提取关键信息(案号、开庭时间等)
        4. 匹配案件并创建日志

        Args:
            file_path: 文书文件路径(支持 PDF、JPG、PNG)
            user: 当前用户(可选,用于日志记录)

        Returns:
            RecognitionResponse 对象,包含识别结果和绑定结果

        Raises:
            ValidationException: 文件格式不支持
            ServiceUnavailableError: AI 服务不可用
            TimeoutError: 识别超时
        """
        ...

    def recognize_document_from_text(self, text: str) -> Any:
        """
        从已提取的文本识别文书

        供其他服务调用(如短信下载服务),跳过文本提取步骤,
        直接进行文书分类和信息提取.

        Args:
            text: 已提取的文书文本内容

        Returns:
            RecognitionResult 对象,包含文书类型、案号、关键时间等

        Raises:
            ValidationException: 文本内容为空
            ServiceUnavailableError: AI 服务不可用
            TimeoutError: 识别超时
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
        **kwargs: Any,
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

    def execute_quote(self, quote_id: int, force_refresh_token: bool = False) -> dict[str, Any]:
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

    def get_quote_by_id(self, quote_id: int) -> Any | None:
        """
        根据ID获取询价记录

        Args:
            quote_id: 询价记录ID

        Returns:
            询价记录,不存在时返回 None
        """
        ...

    def list_quotes(self, status: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """
        获取询价记录列表

        Args:
            status: 状态筛选(可选)
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
        self, file_path: str, limit: int | None = None, preview_page: int | None = None
    ) -> dict[str, Any]:
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

    def extract_text_from_docx(self, file_path: str, limit: int | None = None) -> str:
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

    def extract_text_from_image(self, file_path: str, limit: int | None = None) -> str:
        """
        从图片文件提取文本(OCR)

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
        self, uploaded_file: Any, limit: int | None = None, preview_page: int | None = None
    ) -> dict[str, Any]:
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

    def generate_filename(self, document_content: str, prompt: str | None = None, model: str = "qwen3:0.6b") -> str:
        """
        根据文档内容生成文件名

        Args:
            document_content: 文档文本内容
            prompt: 自定义提示词(可选)
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
        prompt: str | None = None,
        model: str = "qwen3:0.6b",
        limit: int | None = None,
        preview_page: int | None = None,
    ) -> dict[str, Any]:
        """
        处理文档并生成命名建议

        Args:
            uploaded_file: 上传的文件对象
            prompt: 自定义提示词(可选)
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

    def get_system_metrics(self) -> dict[str, Any]:
        """
        获取系统性能指标

        Returns:
            系统性能指标字典,包含CPU、内存、磁盘等信息
        """
        ...

    def get_token_acquisition_metrics(self, hours: int = 24) -> dict[str, Any]:
        """
        获取Token获取性能指标

        Args:
            hours: 统计最近多少小时的数据

        Returns:
            Token获取性能指标字典
        """
        ...

    def get_api_performance_metrics(self, api_name: str | None = None, hours: int = 24) -> dict[str, Any]:
        """
        获取API性能指标

        Args:
            api_name: API名称(可选,为空时返回所有API)
            hours: 统计最近多少小时的数据

        Returns:
            API性能指标字典
        """
        ...

    def record_performance_metric(self, metric_name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """
        记录性能指标

        Args:
            metric_name: 指标名称
            value: 指标值
            tags: 标签字典(可选)
        """
        ...
