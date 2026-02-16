"""
财产保险询价服务适配器

提供依赖注入支持的服务适配器，遵循现有的架构模式
"""

from typing import Any, Dict, Optional

from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.automation.services.insurance.preservation_quote_service import PreservationQuoteService
from apps.automation.services.scraper.core.token_service import TokenService
from apps.core.interfaces import IAutoTokenAcquisitionService, IPreservationQuoteService, ServiceLocator


class PreservationQuoteServiceAdapter(IPreservationQuoteService):
    """
    财产保险询价服务适配器

    职责：
    - 创建PreservationQuoteService实例并注入依赖
    - 提供自动Token获取功能的集成
    - 遵循现有的依赖注入模式
    """

    def __init__(
        self,
        token_service: Optional[TokenService] = None,
        insurance_client: Optional[CourtInsuranceClient] = None,
        auto_token_service: Optional[IAutoTokenAcquisitionService] = None,
    ):
        """
        初始化服务适配器

        Args:
            token_service: Token管理服务（可选）
            insurance_client: 保险询价客户端（可选）
            auto_token_service: 自动Token获取服务（可选）
        """
        self._token_service = token_service
        self._insurance_client = insurance_client
        self._auto_token_service = auto_token_service
        self._service = None

    @property
    def token_service(self) -> TokenService:
        """获取Token服务（延迟加载）"""
        if self._token_service is None:
            self._token_service = TokenService()
        return self._token_service

    @property
    def insurance_client(self) -> CourtInsuranceClient:
        """获取保险客户端（延迟加载）"""
        if self._insurance_client is None:
            self._insurance_client = CourtInsuranceClient()
        return self._insurance_client

    @property
    def auto_token_service(self) -> IAutoTokenAcquisitionService:
        """获取自动Token获取服务（延迟加载）"""
        if self._auto_token_service is None:
            self._auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        return self._auto_token_service

    @property
    def service(self) -> PreservationQuoteService:
        """获取核心服务实例（延迟加载）"""
        if self._service is None:
            self._service = EnhancedPreservationQuoteService(
                token_service=self.token_service,
                insurance_client=self.insurance_client,
                auto_token_service=self.auto_token_service,
            )
        return self._service

    def create_quote(
        self,
        case_name: str,
        target_amount: Any,
        applicant_name: str,
        respondent_name: str,
        court_name: str,
        case_type: str = "财产保全",
        **kwargs,
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
        """
        preserve_amount = target_amount
        corp_id = kwargs.get("corp_id", 1)
        category_id = kwargs.get("category_id", 1)
        credential_id = kwargs.get("credential_id")
        return self.service.create_quote(preserve_amount, corp_id, category_id, credential_id)

    def execute_quote(self, quote_id: int, force_refresh_token: bool = False) -> Dict[str, Any]:
        """
        执行询价任务

        Args:
            quote_id: 询价记录ID
            force_refresh_token: 是否强制刷新Token

        Returns:
            询价结果字典
        """
        import asyncio

        if force_refresh_token:
            self.token_service.delete_token("court_zxfw")
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import asyncio

            return asyncio.create_task(self.service.execute_quote(quote_id))
        else:
            return loop.run_until_complete(self.service.execute_quote(quote_id))

    def get_quote_by_id(self, quote_id: int) -> Any:
        """
        根据ID获取询价记录

        Args:
            quote_id: 询价记录ID

        Returns:
            询价记录，不存在时返回 None
        """
        return self.service.get_quote(quote_id)

    def get_quote(self, quote_id: int) -> Any:
        """
        根据ID获取询价记录（别名方法）

        Args:
            quote_id: 询价记录ID

        Returns:
            询价记录，不存在时返回 None
        """
        return self.get_quote_by_id(quote_id)

    def list_quotes(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取询价记录列表

        Args:
            status: 状态筛选（可选）
            limit: 限制数量
            offset: 偏移量
            page: 页码（可选，优先使用）
            page_size: 每页大小（可选，优先使用）

        Returns:
            包含记录列表和总数的字典
        """
        if page is not None:
            actual_page = page
            actual_page_size = page_size or limit
        else:
            actual_page = offset // limit + 1
            actual_page_size = limit
        quotes, total = self.service.list_quotes(actual_page, actual_page_size, status)
        return {"quotes": quotes, "total": total, "page": actual_page, "page_size": actual_page_size}

    async def retry_quote(self, quote_id: int) -> Any:
        """重试失败的询价任务"""
        return await self.service.retry_quote(quote_id)

    def create_quote_internal(
        self,
        case_name: str,
        target_amount: Any,
        applicant_name: str,
        respondent_name: str,
        court_name: str,
        case_type: str = "财产保全",
        **kwargs,
    ) -> Any:
        """创建询价任务（内部接口，无权限检查）"""
        return self.create_quote(
            case_name, target_amount, applicant_name, respondent_name, court_name, case_type, **kwargs
        )

    def execute_quote_internal(self, quote_id: int, force_refresh_token: bool = False) -> Dict[str, Any]:
        """执行询价任务（内部接口，无权限检查）"""
        return self.execute_quote(quote_id, force_refresh_token)

    def get_quote_by_id_internal(self, quote_id: int) -> Any:
        """根据ID获取询价记录（内部接口，无权限检查）"""
        return self.get_quote_by_id(quote_id)

    def list_quotes_internal(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取询价记录列表（内部接口，无权限检查）"""
        return self.list_quotes(status, limit, offset, page, page_size)


class EnhancedPreservationQuoteService(PreservationQuoteService):
    """
    增强版财产保险询价服务

    在原有功能基础上集成自动Token获取功能
    """

    def __init__(
        self,
        token_service: TokenService,
        insurance_client: CourtInsuranceClient,
        auto_token_service: IAutoTokenAcquisitionService,
    ):
        """
        初始化增强版服务

        Args:
            token_service: Token管理服务
            insurance_client: 保险询价客户端
            auto_token_service: 自动Token获取服务
        """
        super().__init__(
            token_service=token_service, auto_token_service=auto_token_service, insurance_client=insurance_client
        )

    async def _get_valid_token(self, credential_id: int = None) -> str:
        """
        获取有效的Token（集成自动获取功能）

        优化策略：
        1. 首先尝试获取现有的有效Token
        2. 如果没有有效Token，自动触发登录流程获取新Token
        3. 支持指定凭证ID或自动选择最优账号
        4. 提供详细的日志记录和错误处理

        Args:
            credential_id: 凭证ID（可选）

        Returns:
            Bearer Token

        Raises:
            AutoTokenAcquisitionError: Token获取失败
            ValidationException: 参数验证失败
        """
        import logging

        from asgiref.sync import sync_to_async

        from apps.core.exceptions import AutoTokenAcquisitionError

        logger = logging.getLogger(__name__)
        logger.info(
            "开始获取Token（增强版）",
            extra={
                "action": "get_valid_token_enhanced_start",
                "credential_id": credential_id,
                "method": "auto_acquisition_integrated",
            },
        )
        site_name = "court_zxfw"
        try:
            token = await self.auto_token_service.acquire_token_if_needed(
                site_name=site_name, credential_id=credential_id
            )
            logger.info(
                "✅ Token获取成功（增强版）",
                extra={
                    "action": "get_valid_token_enhanced_success",
                    "site_name": site_name,
                    "credential_id": credential_id,
                    "token_length": len(token) if token else 0,
                },
            )
            return token
        except Exception as e:
            logger.error(
                f"❌ Token获取失败（增强版）: {e}",
                extra={
                    "action": "get_valid_token_enhanced_failed",
                    "site_name": site_name,
                    "credential_id": credential_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            if isinstance(e, AutoTokenAcquisitionError):
                from apps.automation.services.insurance.exceptions import TokenError

                error_msg = f"❌ 自动Token获取失败: {str(e)}\n\n可能的原因：\n1. 所有账号的Token都已过期\n2. 自动登录过程中遇到网络问题\n3. 验证码识别失败\n4. 账号密码错误\n\n建议操作：\n1. 检查网络连接\n2. 访问 Django Admin 手动测试登录\n3. 检查账号凭证是否正确\n4. 查看详细日志获取更多信息"
                raise TokenError(error_msg)
            else:
                raise

    def create_quote_internal(
        self,
        case_name: str,
        target_amount: Any,
        applicant_name: str,
        respondent_name: str,
        court_name: str,
        case_type: str = "财产保全",
        **kwargs,
    ) -> Any:
        """创建询价任务（内部接口，无权限检查）"""
        return self.create_quote(
            case_name, target_amount, applicant_name, respondent_name, court_name, case_type, **kwargs
        )

    def execute_quote_internal(self, quote_id: int, force_refresh_token: bool = False) -> Dict[str, Any]:
        """执行询价任务（内部接口，无权限检查）"""
        return self.execute_quote(quote_id, force_refresh_token)

    def get_quote_by_id_internal(self, quote_id: int) -> Any:
        """根据ID获取询价记录（内部接口，无权限检查）"""
        return self.get_quote_by_id(quote_id)

    def list_quotes_internal(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取询价记录列表（内部接口，无权限检查）"""
        return self.list_quotes(status, limit, offset, page, page_size)
