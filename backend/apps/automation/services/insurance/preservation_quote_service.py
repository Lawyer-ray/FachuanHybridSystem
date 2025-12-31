"""
财产保全询价服务

提供财产保全担保费询价的业务逻辑：
- 创建询价任务
- 执行询价流程
- 获取询价结果
- 列表查询
"""
import logging
import asyncio
from typing import List, Tuple, Dict, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator

from apps.core.config import get_config

from apps.automation.models import PreservationQuote, InsuranceQuote, QuoteStatus, QuoteItemStatus
from apps.core.interfaces import ITokenService, IAutoTokenAcquisitionService
from apps.automation.services.insurance.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)
from apps.automation.services.insurance.exceptions import (
    TokenError,
    APIError,
    NetworkError,
    ValidationError,
    CompanyListEmptyError,
    QuoteExecutionError,
)
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.automation")


def get_or_create_token(site_name="court_zxfw", account=None):
    """
    获取或创建 Token
    
    如果存在有效的 Token 则直接返回，否则需要手动登录获取
    
    Args:
        site_name: 网站名称
        account: 账号（可选，如果不提供则查找任意有效 Token）
        
    Returns:
        Token 字符串，如果不存在则返回 None
    """
    from apps.automation.models import CourtToken
    from django.utils import timezone
    from apps.automation.services.scraper.core.token_service import TokenService
    
    token_service = TokenService()
    
    # 如果提供了账号，尝试获取指定账号的 Token
    if account:
        token = token_service.get_token(site_name=site_name, account=account)
        if token:
            logger.info(f"✅ 找到指定账号的有效 Token: {site_name} - {account}")
            return token
    
    # 如果没有提供账号，或指定账号的 Token 不存在，查找任意有效 Token
    try:
        # 查找所有未过期的 Token
        valid_tokens = CourtToken.objects.filter(
            site_name=site_name,
            expires_at__gt=timezone.now()
        ).order_by('-created_at')  # 优先使用最新的 Token
        
        if valid_tokens.exists():
            token_obj = valid_tokens.first()
            logger.info(f"✅ 找到有效 Token: {site_name} - {token_obj.account}")
            return token_obj.token
    
    except Exception as e:
        logger.error(f"查找 Token 失败: {e}", exc_info=True)
    
    logger.warning(f"⚠️ 未找到有效 Token: {site_name}，需要手动登录获取")
    return None


class PreservationQuoteService:
    """
    财产保全询价服务
    
    职责：
    - 管理询价任务的生命周期
    - 集成 TokenService 进行 Token 管理
    - 调用 CourtInsuranceClient 执行询价
    - 持久化询价结果
    
    使用依赖注入，所有依赖通过构造函数传递
    """
    
    def __init__(
        self,
        token_service: Optional[ITokenService] = None,
        auto_token_service: Optional['IAutoTokenAcquisitionService'] = None,
        insurance_client: Optional[CourtInsuranceClient] = None
    ):
        """
        初始化服务（依赖注入）
        
        Args:
            token_service: Token 管理服务，None 时使用 ServiceLocator 获取
            auto_token_service: 自动Token获取服务，None 时使用 ServiceLocator 获取
            insurance_client: 保险询价客户端，None 时创建默认实例
        """
        self._token_service = token_service
        self._auto_token_service = auto_token_service
        self.insurance_client = insurance_client or CourtInsuranceClient()
    
    @property
    def token_service(self) -> ITokenService:
        """获取 Token 服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator
            self._token_service = ServiceLocator.get_token_service()
        return self._token_service
    
    @property
    def auto_token_service(self) -> 'IAutoTokenAcquisitionService':
        """获取自动Token获取服务（延迟加载）"""
        if self._auto_token_service is None:
            from apps.core.interfaces import ServiceLocator
            self._auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        return self._auto_token_service
    
    @transaction.atomic
    def create_quote(
        self,
        preserve_amount: Decimal,
        corp_id: str,
        category_id: str,
        credential_id: int = None
    ) -> PreservationQuote:
        """
        创建询价任务
        
        Args:
            preserve_amount: 保全金额
            corp_id: 企业/法院 ID
            category_id: 分类 ID (cPid)
            credential_id: 凭证 ID
            
        Returns:
            创建的询价任务
            
        Raises:
            ValidationException: 数据验证失败
        """
        # 数据验证
        try:
            self._validate_create_params(
                preserve_amount=preserve_amount,
                corp_id=corp_id,
                category_id=category_id,
                credential_id=credential_id
            )
        except ValidationError as e:
            # 记录验证失败日志
            logger.warning(
                "创建询价任务验证失败",
                extra={
                    "action": "create_quote_validation_failed",
                    "preserve_amount": str(preserve_amount),
                    "corp_id": corp_id,
                    "category_id": category_id,
                    "credential_id": credential_id,
                    "errors": e.errors if hasattr(e, 'errors') else str(e),
                }
            )
            raise
        
        # 记录任务创建开始
        logger.info(
            "创建询价任务",
            extra={
                "action": "create_quote_start",
                "preserve_amount": str(preserve_amount),
                "corp_id": corp_id,
                "category_id": category_id,
                "credential_id": credential_id,
            }
        )
        
        # 创建任务
        quote = PreservationQuote.objects.create(
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            category_id=category_id,
            credential_id=credential_id,
            status=QuoteStatus.PENDING,
        )
        
        # 记录任务创建成功
        logger.info(
            f"✅ 询价任务创建成功",
            extra={
                "action": "create_quote_success",
                "quote_id": quote.id,
                "status": quote.status,
                "preserve_amount": str(quote.preserve_amount),
            }
        )
        
        return quote
    
    @transaction.atomic
    async def execute_quote(self, quote_id: int) -> Dict:
        """
        执行询价流程
        
        Args:
            quote_id: 询价任务 ID
            
        Returns:
            执行结果统计
            
        Raises:
            NotFoundError: 任务不存在
            TokenError: Token 相关错误
            BusinessError: 其他业务错误
        """
        from asgiref.sync import sync_to_async
        import time
        
        # 记录任务开始时间
        task_start_time = time.time()
        
        # 获取任务
        try:
            quote = await sync_to_async(PreservationQuote.objects.get)(id=quote_id)
        except PreservationQuote.DoesNotExist:
            logger.error(
                "询价任务不存在",
                extra={
                    "quote_id": quote_id,
                    "action": "execute_quote",
                }
            )
            raise NotFoundError(
                message="询价任务不存在",
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id}
            )
        
        # 记录任务开始日志（包含任务 ID 和参数）
        logger.info(
            "开始执行询价任务",
            extra={
                "action": "execute_quote_start",
                "quote_id": quote.id,
                "preserve_amount": str(quote.preserve_amount),
                "corp_id": quote.corp_id,
                "category_id": quote.category_id,
                "credential_id": quote.credential_id,
                "status": quote.status,
            }
        )
        
        # 更新任务状态为执行中
        quote.status = QuoteStatus.RUNNING
        quote.started_at = timezone.now()
        await sync_to_async(quote.save)(update_fields=["status", "started_at"])
        
        try:
            # 1. 获取 Token
            token = await self._get_valid_token(quote.credential_id)
            
            # 2. 获取保险公司列表
            companies = await self._fetch_insurance_companies(
                token=token,
                category_id=quote.category_id,
                corp_id=quote.corp_id,
            )
            
            # 更新保险公司总数
            quote.total_companies = len(companies)
            await sync_to_async(quote.save)(update_fields=["total_companies"])
            
            # 3. 并发查询所有保险公司报价
            premium_results = await self._fetch_all_premiums(
                token=token,
                preserve_amount=quote.preserve_amount,
                corp_id=quote.corp_id,
                companies=companies,
            )
            
            # 4. 保存报价结果
            success_count, failed_count = await self._save_premium_results(
                quote=quote,
                results=premium_results,
            )
            
            # 5. 更新任务状态
            quote.success_count = success_count
            quote.failed_count = failed_count
            quote.finished_at = timezone.now()
            
            # 根据成功/失败情况设置状态
            if success_count == 0:
                quote.status = QuoteStatus.FAILED
                quote.error_message = "所有保险公司查询均失败"
            elif failed_count == 0:
                quote.status = QuoteStatus.SUCCESS
            else:
                quote.status = QuoteStatus.PARTIAL_SUCCESS
            
            await sync_to_async(quote.save)(update_fields=[
                "success_count",
                "failed_count",
                "status",
                "finished_at",
                "error_message",
            ])
            
            # 计算执行时长
            execution_time = (quote.finished_at - quote.started_at).total_seconds()
            total_elapsed_time = time.time() - task_start_time
            
            # 记录任务完成日志（包含执行时长和统计信息）
            logger.info(
                "✅ 询价任务执行完成",
                extra={
                    "action": "execute_quote_complete",
                    "quote_id": quote.id,
                    "status": quote.status,
                    "total_companies": quote.total_companies,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "execution_time_seconds": round(execution_time, 2),
                    "total_elapsed_time_seconds": round(total_elapsed_time, 2),
                    "success_rate": round(success_count / quote.total_companies * 100, 2) if quote.total_companies > 0 else 0,
                }
            )
            
            return {
                "quote_id": quote.id,
                "status": quote.status,
                "total_companies": quote.total_companies,
                "success_count": success_count,
                "failed_count": failed_count,
                "execution_time": execution_time,
            }
        
        except Exception as e:
            # 任务执行失败
            quote.status = QuoteStatus.FAILED
            quote.error_message = str(e)
            quote.finished_at = timezone.now()
            await sync_to_async(quote.save)(update_fields=["status", "error_message", "finished_at"])
            
            # 计算失败时的执行时长
            failed_elapsed_time = time.time() - task_start_time
            
            # 记录错误日志（包含完整堆栈信息）
            logger.error(
                f"❌ 询价任务执行失败: {e}",
                extra={
                    "action": "execute_quote_failed",
                    "quote_id": quote.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "elapsed_time_seconds": round(failed_elapsed_time, 2),
                },
                exc_info=True  # 记录完整堆栈信息
            )
            
            raise
    
    def get_quote(self, quote_id: int) -> PreservationQuote:
        """
        获取询价结果
        
        Args:
            quote_id: 询价任务 ID
            
        Returns:
            询价任务（包含所有报价记录）
            
        Raises:
            NotFoundError: 任务不存在
        """
        logger.info(
            "获取询价任务",
            extra={
                "action": "get_quote",
                "quote_id": quote_id,
            }
        )
        
        try:
            quote = PreservationQuote.objects.prefetch_related("quotes").get(id=quote_id)
            
            logger.info(
                "✅ 获取询价任务成功",
                extra={
                    "action": "get_quote_success",
                    "quote_id": quote.id,
                    "status": quote.status,
                    "quotes_count": quote.quotes.count(),
                }
            )
            
            return quote
        except PreservationQuote.DoesNotExist:
            logger.error(
                "询价任务不存在",
                extra={
                    "action": "get_quote_not_found",
                    "quote_id": quote_id,
                }
            )
            raise NotFoundError(
                message="询价任务不存在",
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id}
            )
    
    @transaction.atomic
    async def retry_quote(self, quote_id: int) -> Dict:
        """
        重试失败的询价任务
        
        此方法允许重新执行失败或部分成功的询价任务。
        
        Args:
            quote_id: 询价任务 ID
            
        Returns:
            执行结果统计
            
        Raises:
            NotFoundError: 任务不存在
            ValidationError: 任务状态不允许重试
        """
        from asgiref.sync import sync_to_async
        
        # 获取任务
        try:
            quote = await sync_to_async(PreservationQuote.objects.get)(id=quote_id)
        except PreservationQuote.DoesNotExist:
            logger.error(
                "询价任务不存在",
                extra={
                    "quote_id": quote_id,
                    "action": "retry_quote",
                }
            )
            raise NotFoundError(
                message="询价任务不存在",
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id}
            )
        
        # 检查任务状态是否允许重试
        if quote.status not in [QuoteStatus.FAILED, QuoteStatus.PARTIAL_SUCCESS]:
            logger.warning(
                "任务状态不允许重试",
                extra={
                    "action": "retry_quote_invalid_status",
                    "quote_id": quote.id,
                    "current_status": quote.status,
                }
            )
            raise ValidationError(
                message=f"任务状态为 {quote.get_status_display()}，不允许重试。只有失败或部分成功的任务可以重试。",
                code="INVALID_QUOTE_STATUS",
                errors={"status": quote.status}
            )
        
        logger.info(
            "开始重试询价任务",
            extra={
                "action": "retry_quote_start",
                "quote_id": quote.id,
                "previous_status": quote.status,
                "previous_success_count": quote.success_count,
                "previous_failed_count": quote.failed_count,
            }
        )
        
        # 重置任务状态
        quote.status = QuoteStatus.PENDING
        quote.error_message = None
        quote.started_at = None
        quote.finished_at = None
        await sync_to_async(quote.save)(update_fields=[
            "status",
            "error_message",
            "started_at",
            "finished_at",
        ])
        
        # 删除之前的报价记录（可选，根据业务需求决定）
        # await sync_to_async(quote.quotes.all().delete)()
        
        # 执行询价
        result = await self.execute_quote(quote_id)
        
        logger.info(
            "✅ 重试询价任务完成",
            extra={
                "action": "retry_quote_complete",
                "quote_id": quote.id,
                "new_status": result["status"],
                "new_success_count": result["success_count"],
                "new_failed_count": result["failed_count"],
            }
        )
        
        return result
    
    def list_quotes(
        self,
        page: int = 1,
        page_size: Optional[int] = None,
        status: Optional[str] = None
    ) -> Tuple[List[PreservationQuote], int]:
        """
        列表查询（优化版）
        
        性能优化：
        - 使用 prefetch_related 预加载 quotes 关系，避免 N+1 查询
        - 使用 only() 只查询需要的字段，减少数据传输
        - 使用索引优化排序和筛选
        
        Args:
            page: 页码（从 1 开始）
            page_size: 每页数量
            status: 状态筛选（可选）
            
        Returns:
            (任务列表, 总数)
            
        Raises:
            ValidationError: 参数验证失败
        """
        # 获取分页配置
        if page_size is None:
            page_size = get_config("pagination.default_page_size", 20)
        
        # 参数验证
        errors = {}
        max_page_size = get_config("pagination.max_page_size", 100)
        
        if page < 1:
            errors["page"] = "页码必须大于 0"
        if page_size < 1 or page_size > max_page_size:
            errors["page_size"] = f"每页数量必须在 1-{max_page_size} 之间"
        
        if errors:
            raise ValidationError(
                message="参数验证失败",
                code="INVALID_PARAMETERS",
                errors=errors
            )
        
        logger.info(
            "查询询价任务列表",
            extra={
                "action": "list_quotes",
                "page": page,
                "page_size": page_size,
                "status": status,
            }
        )
        
        # 构建查询
        queryset = PreservationQuote.objects.all()
        
        # 状态筛选（使用索引）
        if status:
            queryset = queryset.filter(status=status)
        
        # 排序（使用索引：status + created_at）
        queryset = queryset.order_by("-created_at")
        
        # 预加载关联的报价记录，避免 N+1 查询
        # 如果列表页面需要显示报价数量或报价详情，这会显著提升性能
        queryset = queryset.prefetch_related("quotes")
        
        # 只查询列表展示需要的字段，减少数据传输
        # 注意：如果需要访问其他字段，需要在这里添加
        queryset = queryset.only(
            "id",
            "preserve_amount",
            "corp_id",
            "category_id",
            "credential_id",
            "status",
            "total_companies",
            "success_count",
            "failed_count",
            "created_at",
            "started_at",
            "finished_at",
        )
        
        # 分页
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        logger.info(
            "✅ 查询询价任务列表成功",
            extra={
                "action": "list_quotes_success",
                "page": page,
                "page_size": page_size,
                "total_count": paginator.count,
                "returned_count": len(page_obj.object_list),
            }
        )
        
        return list(page_obj.object_list), paginator.count
    
    # ==================== 私有方法 ====================
    
    def _validate_create_params(
        self,
        preserve_amount: Decimal,
        corp_id: str,
        category_id: str,
        credential_id: int
    ) -> None:
        """
        验证创建参数
        
        Raises:
            ValidationException: 验证失败
        """
        errors = {}
        
        # 验证保全金额
        if preserve_amount <= 0:
            errors["preserve_amount"] = "保全金额必须为正数"
        
        # 验证法院 ID
        if not corp_id or not corp_id.strip():
            errors["corp_id"] = "法院 ID 不能为空"
        
        # 验证分类 ID
        if not category_id or not category_id.strip():
            errors["category_id"] = "分类 ID 不能为空"
        
        # 验证凭证 ID（可选）
        if credential_id is not None and credential_id <= 0:
            errors["credential_id"] = "凭证 ID 必须为正整数"
        
        if errors:
            raise ValidationError(
                message="数据验证失败",
                code="INVALID_CREATE_PARAMS",
                errors=errors
            )
    
    async def _get_valid_token(self, credential_id: int = None) -> str:
        """
        获取有效的 Token（集成自动获取功能）
        
        功能：
        1. 首先检查现有Token是否有效
        2. 如果无有效Token，自动触发登录流程获取新Token
        3. 支持指定凭证ID或自动选择最佳账号
        4. 完整的错误处理和日志记录
        
        Args:
            credential_id: 凭证 ID（可选）
            
        Returns:
            Bearer Token
            
        Raises:
            TokenError: Token 获取失败
        """
        from asgiref.sync import sync_to_async
        
        logger.info(
            "开始获取 Token",
            extra={
                "action": "get_valid_token_start",
                "credential_id": credential_id,
            }
        )
        
        site_name = "court_zxfw"  # 法院一张网
        
        try:
            # 1. 首先检查现有Token
            if credential_id is not None:
                try:
                    # 通过ServiceLocator获取organization服务
                    from apps.core.interfaces import ServiceLocator
                    organization_service = ServiceLocator.get_organization_service()
                    credential = await organization_service.get_credential_internal(credential_id)
                    account = credential.account
                    
                    logger.info(f"检查指定账号 {account} 的现有Token")
                    # 使用同步方法调用 TokenService
                    from apps.automation.services.scraper.core.token_service import TokenService
                    sync_token_service = TokenService()
                    token = await sync_to_async(sync_token_service.get_token)(site_name=site_name, account=account)
                    
                    if token:
                        logger.info(f"✅ 找到指定账号的有效 Token: {account}")
                        return token
                    else:
                        logger.info(f"指定账号 {account} 无有效Token，将自动获取")
                        
                except Exception as e:
                    logger.warning(f"凭证 {credential_id} 获取失败: {e}，将自动选择账号")
                    credential_id = None  # 重置为None，使用自动选择
            
            # 2. 检查是否有任意有效Token（快速路径）
            if credential_id is None:
                logger.info("检查是否有任意有效Token")
                token = await sync_to_async(get_or_create_token)(site_name=site_name)
                if token:
                    logger.info("✅ 找到现有有效Token")
                    return token
                else:
                    logger.info("无现有有效Token，将自动获取")
            
            # 3. 使用自动Token获取服务
            logger.info("启动自动Token获取流程")
            
            # 使用注入的自动Token获取服务
            token = await self.auto_token_service.acquire_token_if_needed(
                site_name=site_name,
                credential_id=credential_id
            )
            
            logger.info(
                "✅ 自动Token获取成功",
                extra={
                    "action": "get_valid_token_success",
                    "site_name": site_name,
                    "credential_id": credential_id,
                    "acquisition_method": "auto"
                }
            )
            
            return token
            
        except Exception as e:
            # 统一错误处理
            logger.error(
                f"❌ Token获取失败: {e}",
                extra={
                    "action": "get_valid_token_failed",
                    "site_name": site_name,
                    "credential_id": credential_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                },
                exc_info=True
            )
            
            # 根据错误类型提供不同的用户提示
            if "NoAvailableAccountError" in str(type(e)):
                error_msg = (
                    "❌ 没有找到法院一张网的账号凭证\n\n"
                    "请在 Admin 后台添加账号：\n"
                    "1. 访问 /admin/organization/accountcredential/\n"
                    "2. 点击「添加账号密码」\n"
                    "3. URL 填写：https://zxfw.court.gov.cn\n"
                    "4. 填写账号和密码\n"
                    "5. 保存后重新执行询价"
                )
            elif "LoginFailedError" in str(type(e)):
                error_msg = (
                    "❌ 自动登录失败\n\n"
                    "可能原因：\n"
                    "- 账号密码错误\n"
                    "- 验证码识别失败\n"
                    "- 网络连接问题\n\n"
                    "建议操作：\n"
                    "1. 访问 Django Admin: /admin/automation/testcourt/\n"
                    "2. 手动测试登录，确认账号可用\n"
                    "3. 检查网络连接\n"
                    "4. 重新执行询价任务\n"
                )
            elif "TokenAcquisitionTimeoutError" in str(type(e)):
                error_msg = (
                    "❌ Token获取超时\n\n"
                    "可能原因：\n"
                    "- 网络连接缓慢\n"
                    "- 法院网站响应慢\n"
                    "- 验证码处理耗时过长\n\n"
                    "建议操作：\n"
                    "1. 检查网络连接\n"
                    "2. 稍后重试\n"
                    "3. 如持续失败，请手动获取Token\n"
                )
            else:
                error_msg = (
                    f"❌ Token获取失败: {str(e)}\n\n"
                    "备用方案：\n"
                    "1. 访问 Django Admin: /admin/automation/testcourt/\n"
                    "2. 点击「测试登录」按钮，手动获取Token\n"
                    "3. Token会自动保存到: /admin/automation/courttoken/\n"
                    "4. 重新执行询价任务\n"
                )
            
            raise TokenError(error_msg)
    
    async def _fetch_insurance_companies(
        self,
        token: str,
        category_id: str,
        corp_id: str,
    ) -> List[InsuranceCompany]:
        """
        获取保险公司列表
        
        Args:
            token: Bearer Token
            category_id: 分类 ID
            corp_id: 法院 ID
            
        Returns:
            保险公司列表
            
        Raises:
            BusinessError: API 调用失败
        """
        logger.info(
            "开始获取保险公司列表",
            extra={
                "action": "fetch_insurance_companies_wrapper_start",
                "category_id": category_id,
                "corp_id": corp_id,
            }
        )
        
        try:
            companies = await self.insurance_client.fetch_insurance_companies(
                bearer_token=token,
                c_pid=category_id,
                fy_id=corp_id,
            )
            
            if not companies:
                logger.error(
                    "未获取到保险公司列表",
                    extra={
                        "action": "fetch_insurance_companies_empty",
                        "category_id": category_id,
                        "corp_id": corp_id,
                    }
                )
                raise CompanyListEmptyError(
                    message="未获取到保险公司列表，请检查分类 ID 和法院 ID 是否正确"
                )
            
            logger.info(
                f"✅ 获取到 {len(companies)} 家保险公司",
                extra={
                    "action": "fetch_insurance_companies_wrapper_success",
                    "companies_count": len(companies),
                }
            )
            
            return companies
        
        except CompanyListEmptyError:
            # 重新抛出，不包装
            raise
        except Exception as e:
            logger.error(
                f"获取保险公司列表失败: {e}",
                extra={
                    "action": "fetch_insurance_companies_wrapper_failed",
                    "category_id": category_id,
                    "corp_id": corp_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True  # 记录完整堆栈信息
            )
            raise APIError(
                message=f"获取保险公司列表失败: {str(e)}"
            )
    
    async def _fetch_all_premiums(
        self,
        token: str,
        preserve_amount: Decimal,
        corp_id: str,
        companies: List[InsuranceCompany],
    ) -> List[PremiumResult]:
        """
        并发查询所有保险公司报价
        
        Args:
            token: Bearer Token
            preserve_amount: 保全金额
            corp_id: 法院 ID
            companies: 保险公司列表
            
        Returns:
            报价结果列表
        """
        results = await self.insurance_client.fetch_all_premiums(
            bearer_token=token,
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            companies=companies,
        )
        
        return results
    
    async def _save_premium_results(
        self,
        quote: PreservationQuote,
        results: List[PremiumResult],
    ) -> Tuple[int, int]:
        """
        保存报价结果到数据库
        
        Args:
            quote: 询价任务
            results: 报价结果列表
            
        Returns:
            (成功数量, 失败数量)
        """
        from asgiref.sync import sync_to_async
        
        logger.info(
            "开始保存报价结果",
            extra={
                "action": "save_premium_results_start",
                "quote_id": quote.id,
                "results_count": len(results),
            }
        )
        
        success_count = 0
        failed_count = 0
        
        # 批量创建报价记录
        insurance_quotes = []
        
        for result in results:
            status = QuoteItemStatus.SUCCESS if result.status == "success" else QuoteItemStatus.FAILED
            
            # 从 response_data 中提取费率信息
            rate_data = {}
            if result.response_data and isinstance(result.response_data, dict):
                rate_data = result.response_data.get("data") or {}
            
            # 确保 rate_data 是字典
            if not isinstance(rate_data, dict):
                rate_data = {}
            
            # 辅助函数：清洗数值，将空字符串和无效值转换为 None
            def clean_decimal(value):
                """清洗 Decimal 字段的值"""
                if value is None or value == "" or value == "null":
                    return None
                try:
                    from decimal import Decimal
                    return Decimal(str(value))
                except:
                    return None
            
            insurance_quote = InsuranceQuote(
                preservation_quote=quote,
                company_id=result.company.c_id,
                company_code=result.company.c_code,
                company_name=result.company.c_name,
                premium=result.premium,
                # 保存费率信息（清洗数据）
                min_premium=clean_decimal(rate_data.get("minPremium")),
                min_amount=clean_decimal(rate_data.get("minAmount")),
                max_amount=clean_decimal(rate_data.get("maxAmount")),
                min_rate=clean_decimal(rate_data.get("minRate")),
                max_rate=clean_decimal(rate_data.get("maxRate")),
                max_apply_amount=clean_decimal(rate_data.get("maxApplyAmount")),
                status=status,
                error_message=result.error_message,
                response_data=result.response_data,
            )
            
            insurance_quotes.append(insurance_quote)
            
            if result.status == "success":
                success_count += 1
            else:
                failed_count += 1
        
        # 批量插入
        await sync_to_async(InsuranceQuote.objects.bulk_create)(insurance_quotes)
        
        logger.info(
            f"✅ 保存报价结果成功",
            extra={
                "action": "save_premium_results_success",
                "quote_id": quote.id,
                "total_records": len(insurance_quotes),
                "success_count": success_count,
                "failed_count": failed_count,
            }
        )
        
        return success_count, failed_count
