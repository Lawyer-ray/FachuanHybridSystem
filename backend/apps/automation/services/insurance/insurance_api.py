"""API endpoints."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

"""
保险询价 API 通信模块

提供与法院保险系统的 API 交互功能:
- 获取保险公司列表
- 查询单个保险公司报价

作为 CourtInsuranceClient 的 Mixin 使用.
"""
import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Any

import httpx

from apps.core.config import get_config
from apps.core.exceptions import APIError, NetworkError

from .insurance_data import InsuranceCompany, PremiumResult

logger = logging.getLogger("apps.automation")


class InsuranceApiMixin:
    """保险 API 通信 Mixin

    提供 API 通信相关的方法,包括:
    - 获取保险公司列表
    - 查询单个保险公司报价
    """

    @property
    def insurance_list_url(self) -> Any:
        """获取保险公司列表 API URL"""
        return get_config("services.insurance.list_url", "https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz")

    @property
    def premium_query_url(self) -> Any:
        """获取保险费率查询 API URL"""
        return get_config(
            "services.insurance.premium_query_url", "https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium"
        )

    @property
    def default_timeout(self) -> Any:
        """获取默认超时时间"""
        return get_config("services.insurance.default_timeout", 60.0)

    @property
    def max_connections(self) -> Any:
        """获取最大连接数"""
        return get_config("services.insurance.max_connections", 100)

    async def fetch_insurance_companies(
        self, bearer_token: str, c_pid: str, fy_id: str, timeout: float | None = None, max_retries: int = 3
    ) -> list[InsuranceCompany]:
        """
        获取保险公司列表(带重试)

        Args:
            bearer_token: Bearer Token
            c_pid: 分类 ID
            fy_id: 法院 ID
            timeout: 超时时间(秒),默认使用 DEFAULT_TIMEOUT
            max_retries: 最大重试次数(默认 3 次)

        Returns:
            保险公司列表

        Raises:
            NetworkError: 网络错误(连接失败、超时等),会自动重试
            APIError: API 错误(HTTP 状态码错误、响应格式错误等),不会重试
        """
        if timeout is None:
            timeout = self.default_timeout

        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                return await self._fetch_insurance_companies_once(
                    bearer_token=bearer_token,
                    c_pid=c_pid,
                    fy_id=fy_id,
                    timeout=timeout,
                    attempt=attempt,
                )
            except NetworkError as e:
                last_exception = e
                if attempt < max_retries:
                    retry_delay = attempt * 2
                    logger.warning(
                        f"获取保险公司列表失败(尝试 {attempt}/{max_retries}),{retry_delay}秒后重试: {e.message}",
                        extra={
                            "action": "fetch_insurance_companies_retry",
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "retry_delay": retry_delay,
                            "error_code": e.code,
                        },
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"获取保险公司列表失败,已达最大重试次数 {max_retries}",
                        extra={
                            "action": "fetch_insurance_companies_max_retries",
                            "max_retries": max_retries,
                            "error_code": e.code,
                        },
                    )
            except APIError as e:
                logger.error(
                    f"获取保险公司列表失败(不可重试): {e.message}",
                    extra={
                        "action": "fetch_insurance_companies_non_retryable",
                        "error_code": e.code,
                        "error_type": type(e).__name__,
                    },
                )
                raise

        if last_exception:
            raise last_exception

    async def _fetch_insurance_companies_once(
        self, bearer_token: str, c_pid: str, fy_id: str, timeout: float, attempt: int = 1
    ) -> list[InsuranceCompany]:
        """
        获取保险公司列表(单次尝试)

        Args:
            bearer_token: Bearer Token
            c_pid: 分类 ID
            fy_id: 法院 ID
            timeout: 超时时间(秒)
            attempt: 当前尝试次数

        Returns:
            保险公司列表

        Raises:
            NetworkError: 网络错误(连接失败、超时等)
            APIError: API 错误(HTTP 状态码错误、响应格式错误等)
        """
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }

        params = {
            "cPid": c_pid,
            "fyId": fy_id,
        }

        logger.info(
            "开始获取保险公司列表",
            extra={
                "action": "fetch_insurance_companies_start",
                "url": self.insurance_list_url,
                "params": params,
                "timeout": timeout,
            },
        )

        try:
            start_time = time.time()

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(
                    self.insurance_list_url,
                    headers=headers,
                    params=params,
                )

            elapsed_time = time.time() - start_time

            logger.info(
                "保险公司列表 API 响应",
                extra={
                    "action": "fetch_insurance_companies_response",
                    "url": self.insurance_list_url,
                    "status_code": response.status_code,
                    "response_time_seconds": round(elapsed_time, 3),
                },
            )

            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {getattr(response, 'text', '')}"
                logger.error(
                    "获取保险公司列表失败",
                    extra={
                        "action": "fetch_insurance_companies_error",
                        "url": self.insurance_list_url,
                        "status_code": response.status_code,
                        "error_message": error_msg,
                        "response_time_seconds": round(elapsed_time, 3),
                    },
                )
                raise httpx.HTTPStatusError(error_msg, request=getattr(response, "request", None), response=response)

            data = response.json()
            companies = self._parse_company_list(data)

            logger.info(
                f"✅ 成功获取 {len(companies)} 家保险公司",
                extra={
                    "action": "fetch_insurance_companies_success",
                    "companies_count": len(companies),
                    "total_time_seconds": round(elapsed_time, 3),
                },
            )

            return companies

        except httpx.TimeoutException as e:
            error_msg = f"获取保险公司列表超时({timeout}秒)"
            logger.error(error_msg, extra={"action": "fetch_insurance_companies_timeout"}, exc_info=True)
            raise NetworkError(message=error_msg, code="INSURANCE_LIST_TIMEOUT", errors={}) from e
        except httpx.HTTPStatusError as e:
            self._raise_insurance_http_status_error(e)
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            error_msg = f"获取保险公司列表网络错误: {type(e).__name__}"
            logger.error(error_msg, extra={"action": "fetch_insurance_companies_network_error"}, exc_info=True)
            raise NetworkError(message=error_msg, code="INSURANCE_LIST_NETWORK_ERROR", errors={}) from e
        except httpx.HTTPError as e:
            error_msg = f"获取保险公司列表 HTTP 错误: {type(e).__name__}"
            logger.error(error_msg, extra={"action": "fetch_insurance_companies_http_error"}, exc_info=True)
            raise NetworkError(message=error_msg, code="INSURANCE_LIST_HTTP_ERROR", errors={}) from e
        except Exception as e:
            error_msg = f"获取保险公司列表失败: {type(e).__name__}"
            logger.error(error_msg, extra={"action": "fetch_insurance_companies_exception"}, exc_info=True)
            raise APIError(message=error_msg, code="INSURANCE_LIST_ERROR", errors={}) from e

    def _parse_company_list(self, data: dict[str, Any] | list[Any]) -> list[InsuranceCompany]:
        """从 API 响应数据中解析保险公司列表"""
        if isinstance(data, dict) and "data" in data:
            company_list = data.get("data", [])
        elif isinstance(data, list):
            company_list = data
        else:
            logger.warning(f"未知的响应格式: {data}")
            company_list: list[Any] = []

        companies: list[Any] = []
        for item in company_list:
            if not isinstance(item, dict):
                continue

            c_id = item.get("cId")
            c_code = item.get("cCode")
            c_name = item.get("cName")

            if c_id and c_code and c_name:
                companies.append(
                    InsuranceCompany(
                        c_id=str(c_id),
                        c_code=str(c_code),
                        c_name=str(c_name),
                    )
                )
            else:
                logger.warning(f"保险公司信息不完整,跳过: {item}")

        return companies

    def _raise_insurance_http_status_error(self, e: httpx.HTTPStatusError) -> None:
        """处理保险公司列表 HTTP 状态码错误"""
        error_msg = f"获取保险公司列表失败: HTTP {e.response.status_code}"

        if 500 <= e.response.status_code < 600:
            raise NetworkError(message=error_msg, code="INSURANCE_LIST_SERVER_ERROR", errors={}) from e

        raise APIError(message=error_msg, code="INSURANCE_LIST_HTTP_ERROR", errors={}) from e

    async def fetch_premium(
        self, bearer_token: str, preserve_amount: Decimal, institution: str, corp_id: str, timeout: float | None = None
    ) -> PremiumResult:
        """
        查询单个保险公司报价

        注意:此方法不会抛出异常,而是返回包含错误信息的 PremiumResult.

        Args:
            bearer_token: Bearer Token
            preserve_amount: 保全金额
            institution: 保险公司编码 (cCode)
            corp_id: 企业/法院 ID
            timeout: 超时时间(秒),默认使用 DEFAULT_TIMEOUT

        Returns:
            报价结果(包含成功或失败信息)
        """
        if timeout is None:
            timeout = self.default_timeout

        current_time_ms = str(int(time.time() * 1000))

        headers: dict[str, str] = {}

        preserve_amount_str = str(int(preserve_amount))

        params = {
            "time": current_time_ms,
            "preserveAmount": preserve_amount_str,
            "institution": institution,
            "corpId": corp_id,
        }

        company = InsuranceCompany(c_id="", c_code=institution, c_name="")

        request_info = {
            "url": self.premium_query_url,
            "method": "GET",
            "timestamp": current_time_ms,
            "params": params.copy(),
            "body": None,
            "timeout": timeout,
        }

        logger.info(
            f"🔍 查询保险公司报价: {institution}",
            extra={
                "action": "fetch_premium_start",
                "institution": institution,
                "preserve_amount": preserve_amount_str,
            },
        )

        try:
            start_time = time.time()

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(
                    self.premium_query_url,
                    headers=headers,
                    params=params,
                )

            elapsed_time = time.time() - start_time

            logger.info(
                f"保险公司 {institution} 响应",
                extra={
                    "action": "fetch_premium_response",
                    "institution": institution,
                    "status_code": response.status_code,
                    "response_time_seconds": round(elapsed_time, 3),
                },
            )

            return self._build_premium_result(response, company, institution, request_info)

        except httpx.TimeoutException as e:
            logger.warning(f"保险公司 {institution} 查询超时", extra={"action": "fetch_premium_timeout"})
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=f"超时: {e}",
                response_data=None,
                request_info=request_info,
            )
        except httpx.HTTPError:
            error_details = ({},)
            logger.warning(f"保险公司 {institution} HTTP 错误", extra={"action": "fetch_premium_http_exception"})
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=json.dumps(error_details, ensure_ascii=False, indent=2),
                response_data=None,
                request_info=request_info,
            )
        except Exception as e:
            import traceback

            error_details = {
                "error": "未知错误",
                "exception": str(e),
                "traceback": traceback.format_exc(),
                "request": request_info,
            }
            logger.error(f"保险公司 {institution} 未知错误", extra={"action": "fetch_premium_exception"}, exc_info=True)
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=json.dumps(error_details, ensure_ascii=False, indent=2),
                response_data=None,
                request_info=request_info,
            )

    def _build_premium_result(
        self, response: httpx.Response, company: InsuranceCompany, institution: str, request_info: dict[str, Any]
    ) -> PremiumResult:
        """从 HTTP 响应构建 PremiumResult"""
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {getattr(response, 'text', '')}"
            return PremiumResult(
                company=company,
                premium=None,
                status="failed",
                error_message=error_msg,
                response_data=None,
                request_info=request_info,
            )

        data = response.json()
        premium = self._extract_premium_from_response(data)

        if premium is not None:
            logger.info(f"✅ 保险公司 {institution} 报价: ¥{premium}", extra={})
            return PremiumResult(
                company=company,
                premium=premium,
                status="success",
                error_message=None,
                response_data=data,
                request_info=request_info,
            )

        return PremiumResult(
            company=company,
            premium=None,
            status="failed",
            error_message=_("未找到报价金额"),
            response_data=data,
            request_info=request_info,
        )

    def _extract_premium_from_response(self, data: dict[str, Any]) -> Decimal | None | None:
        """从响应数据中提取报价金额"""
        if not isinstance(data, dict):
            return None

        rate_data = data.get("data", {})

        premium_value = data.get("premium")
        if premium_value is None and isinstance(rate_data, dict):
            premium_value = rate_data.get("premium")
        if premium_value is None and isinstance(rate_data, dict):
            premium_value = rate_data.get("minPremium") or rate_data.get("minAmount")

        if premium_value is None:
            return None

        try:
            return Decimal(str(premium_value))
        except (ValueError, TypeError) as e:
            logger.warning(f"无法解析报价金额: {premium_value}, 错误: {e}")
            return None
