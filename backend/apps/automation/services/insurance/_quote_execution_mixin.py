"""询价执行 Mixin — 负责 Token 获取、保险公司查询、报价保存"""

from django.utils.translation import gettext_lazy as _
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from apps.automation.models import InsuranceQuote, QuoteItemStatus
from apps.automation.services.insurance.exceptions import APIError, CompanyListEmptyError, TokenError

if TYPE_CHECKING:
    from apps.automation.models import PreservationQuote
    from apps.automation.services.insurance.court_insurance_client import InsuranceCompany, PremiumResult

logger = logging.getLogger("apps.automation")


def get_or_create_token(site_name: str = "court_zxfw", account: Any | None = None) -> str | None:
    """获取或创建 Token（模块级工具函数）"""
    from django.utils import timezone

    from apps.automation.models import CourtToken
    from apps.automation.services.scraper.core.token_service import TokenService

    token_service = TokenService()

    if account:
        token = token_service.get_token(site_name=site_name, account=account)
        if token:
            logger.info(f"✅ 找到指定账号的有效 Token: {site_name} - {account}")
            return token

    try:
        valid_tokens = CourtToken.objects.filter(site_name=site_name, expires_at__gt=timezone.now()).order_by(
            "-created_at"
        )
        if valid_tokens.exists():
            token_obj = valid_tokens.first()
            logger.info(f"✅ 找到有效 Token: {site_name} - {token_obj.account}") # type: ignore
            return token_obj.token # type: ignore
    except Exception as e:
        logger.error(f"查找 Token 失败: {e}", exc_info=True)

    logger.warning(f"⚠️ 未找到有效 Token: {site_name}，需要手动登录获取")
    return None


class QuoteExecutionMixin:
    """负责询价执行流程的私有方法"""

    from apps.core.interfaces import IAutoTokenAcquisitionService, ITokenService

    @property
    def auto_token_service(self) -> Any:
        """由主类提供"""
        raise NotImplementedError  # pragma: no cover

    @property
    def insurance_client(self) -> Any:
        """由主类提供"""
        raise NotImplementedError  # pragma: no cover

    async def _get_valid_token(self, credential_id: int | None = None) -> str:
        """获取有效的 Token（集成自动获取功能）"""
        from asgiref.sync import sync_to_async

        site_name = "court_zxfw"

        logger.info(
            "开始获取 Token",
            extra={"action": "get_valid_token_start", "credential_id": credential_id},
        )

        try:
            if credential_id is not None:
                try:
                    from apps.core.interfaces import ServiceLocator

                    organization_service = ServiceLocator.get_organization_service()
                    credential = await organization_service.get_credential_internal(credential_id) # type: ignore
                    account = credential.account

                    from apps.automation.services.scraper.core.token_service import TokenService

                    sync_token_service = TokenService()
                    token = await sync_to_async(sync_token_service.get_token)(site_name=site_name, account=account)
                    if token:
                        logger.info(f"✅ 找到指定账号的有效 Token: {account}")
                        return token
                    logger.info(f"指定账号 {account} 无有效Token，将自动获取")
                except Exception as e:
                    logger.warning(f"凭证 {credential_id} 获取失败: {e}，将自动选择账号")
                    credential_id = None

            if credential_id is None:
                token = await sync_to_async(get_or_create_token)(site_name=site_name)
                if token:
                    logger.info("✅ 找到现有有效Token")
                    return token

            token = await self.auto_token_service.acquire_token_if_needed(
                site_name=site_name, credential_id=credential_id
            )
            logger.info("✅ 自动Token获取成功", extra={"action": "get_valid_token_success"})
            return token # type: ignore

        except Exception as e:
            logger.error(
                f"❌ Token获取失败: {e}",
                extra={"action": "get_valid_token_failed", "error_type": type(e).__name__},
                exc_info=True,
            )
            error_type = str(type(e))
            if "NoAvailableAccountError" in error_type:
                msg = "❌ 没有找到法院一张网的账号凭证，请在 Admin 后台添加账号"
            elif "LoginFailedError" in error_type:
                msg = "❌ 自动登录失败，请检查账号密码或验证码"
            elif "TokenAcquisitionTimeoutError" in error_type:
                msg = "❌ Token获取超时，请检查网络连接后重试"
            else:
                msg = f"❌ Token获取失败: {e!s}"
            raise TokenError(msg) from e

    async def _fetch_insurance_companies(self, token: str, category_id: str, corp_id: str) -> "list[InsuranceCompany]":
        """获取保险公司列表"""
        logger.info(
            "开始获取保险公司列表",
            extra={"action": "fetch_insurance_companies_wrapper_start", "category_id": category_id},
        )
        try:
            companies = await self.insurance_client.fetch_insurance_companies(
                bearer_token=token, c_pid=category_id, fy_id=corp_id
            )
            if not companies:
                raise CompanyListEmptyError(message=_("未获取到保险公司列表，请检查分类 ID 和法院 ID 是否正确")) # type: ignore
            logger.info(f"✅ 获取到 {len(companies)} 家保险公司")
            return companies # type: ignore
        except CompanyListEmptyError:
            raise
        except Exception as e:
            logger.error(f"获取保险公司列表失败: {e}", exc_info=True)
            raise APIError(message=f"获取保险公司列表失败: {e!s}") from e

    async def _fetch_all_premiums(
        self,
        token: str,
        preserve_amount: Decimal,
        corp_id: str,
        companies: "list[InsuranceCompany]",
    ) -> "list[PremiumResult]":
        """并发查询所有保险公司报价"""
        return await self.insurance_client.fetch_all_premiums( # type: ignore
            bearer_token=token,
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            companies=companies,
        )

    async def _save_premium_results(
        self,
        quote: "PreservationQuote",
        results: "list[PremiumResult]",
    ) -> tuple[int, int]:
        """保存报价结果到数据库"""
        from asgiref.sync import sync_to_async

        logger.info(
            "开始保存报价结果",
            extra={"action": "save_premium_results_start", "quote_id": quote.id, "results_count": len(results)},
        )

        success_count = 0
        failed_count = 0
        insurance_quotes = []

        for result in results:
            status = QuoteItemStatus.SUCCESS if result.status == "success" else QuoteItemStatus.FAILED

            rate_data: dict[str, Any] = {}
            if result.response_data and isinstance(result.response_data, dict):
                raw = result.response_data.get("data")
                if isinstance(raw, dict):
                    rate_data = raw

            def clean_decimal(value: Any) -> Decimal | None:
                if value is None or value == "" or value == "null":
                    return None
                try:
                    return Decimal(str(value))
                except (ValueError, TypeError, ArithmeticError):
                    return None

            insurance_quotes.append(
                InsuranceQuote(
                    preservation_quote=quote,
                    company_id=result.company.c_id,
                    company_code=result.company.c_code,
                    company_name=result.company.c_name,
                    premium=result.premium,
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
            )

            if result.status == "success":
                success_count += 1
            else:
                failed_count += 1

        await sync_to_async(InsuranceQuote.objects.bulk_create)(insurance_quotes)

        logger.info(
            "✅ 保存报价结果成功",
            extra={
                "action": "save_premium_results_success",
                "quote_id": quote.id,
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )
        return success_count, failed_count
