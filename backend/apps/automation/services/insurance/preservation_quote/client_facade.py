"""External service client."""

from django.utils.translation import gettext_lazy as _
import logging
from decimal import Decimal

from apps.automation.services.insurance.court_insurance_client import (
    CourtInsuranceClient,
    InsuranceCompany,
    PremiumResult,
)
from apps.automation.services.insurance.exceptions import APIError, CompanyListEmptyError

logger = logging.getLogger("apps.automation")


class InsuranceClientFacade:
    def __init__(self, *, client: CourtInsuranceClient) -> None:
        self.client = client

    async def fetch_insurance_companies(self, *, token: str, category_id: str, corp_id: str) -> list[InsuranceCompany]:
        logger.info(
            "开始获取保险公司列表",
            extra={
                "action": "fetch_insurance_companies_wrapper_start",
                "category_id": category_id,
                "corp_id": corp_id,
            },
        )

        try:
            companies = await self.client.fetch_insurance_companies(
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
                    },
                )
                raise CompanyListEmptyError(message=_("未获取到保险公司列表,请检查分类 ID 和法院 ID 是否正确"))

            logger.info(
                f"✅ 获取到 {len(companies)} 家保险公司",
                extra={
                    "action": "fetch_insurance_companies_wrapper_success",
                    "companies_count": len(companies),
                },
            )
            return companies
        except CompanyListEmptyError:
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
                exc_info=True,
            )
            raise APIError(message=f"获取保险公司列表失败: {e!s}") from e

    async def fetch_all_premiums(
        self,
        *,
        token: str,
        preserve_amount: Decimal,
        corp_id: str,
        companies: list[InsuranceCompany],
    ) -> list[PremiumResult]:
        return await self.client.fetch_all_premiums(
            bearer_token=token,
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            companies=companies,
        )
