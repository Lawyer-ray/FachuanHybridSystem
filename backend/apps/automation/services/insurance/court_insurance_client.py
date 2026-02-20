"""
法院保险询价 API 客户端

提供与法院保险系统的 API 交互功能：
- 获取保险公司列表
- 查询单个保险公司报价
- 并发查询所有保险公司报价
"""

from django.utils.translation import gettext_lazy as _
import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import httpx

from apps.core.config import get_config
from apps.core.exceptions import APIError, NetworkError, TokenError
from apps.core.interfaces import ITokenService

from ._insurance_http_mixin import InsuranceHttpMixin

logger = logging.getLogger("apps.automation")


@dataclass
class InsuranceCompany:
    """保险公司信息"""

    c_id: str
    c_code: str
    c_name: str


@dataclass
class PremiumResult:
    """报价结果"""

    company: InsuranceCompany
    premium: Decimal | None
    status: str  # "success" or "failed"
    error_message: str | None
    response_data: dict[str, Any] | None
    request_info: dict[str, Any] | None = None  # 请求信息（用于调试）


class CourtInsuranceClient(InsuranceHttpMixin):
    """
    法院保险询价 API 客户端

    使用 httpx 异步客户端进行 HTTP 请求，支持并发查询多个保险公司报价。

    性能优化：
    - 使用共享的 httpx.AsyncClient 实现连接池复用
    - 配置连接池参数优化并发性能
    - 支持 HTTP/2 多路复用
    """

    # 配置将从统一配置管理系统获取
    # 这些常量保留作为默认值，实际使用时会从配置系统读取

    def __init__(self, token_service: ITokenService | None = None):
        """
        初始化客户端（使用依赖注入）

        Args:
            token_service: Token 管理服务（可选）。
                          如果不提供则使用 ServiceLocator 获取。
                          建议在生产环境中注入以便于测试和管理。

        Example:
            # 使用默认 TokenService（通过 ServiceLocator）
            client = CourtInsuranceClient()

            # 注入自定义 TokenService（推荐用于测试）
            client = CourtInsuranceClient(token_service=mock_token_service)
        """
        self._token_service = token_service

        # 创建共享的 httpx 客户端，配置连接池
        # 使用 Limits 配置连接池参数
        max_connections = self.max_connections
        max_keepalive_connections = get_config("services.insurance.max_keepalive_connections", 20)
        keepalive_expiry = get_config("services.insurance.keepalive_expiry", 30.0)

        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
        )

        # 创建共享客户端（尝试启用 HTTP/2）
        # HTTP/2 需要安装 h2 包: uv add httpx[http2]
        try:
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=self.default_timeout,
                http2=True,  # 启用 HTTP/2 支持
                follow_redirects=True,
            )
            http2_enabled = True
        except ImportError:
            # h2 包未安装，回退到 HTTP/1.1
            logger.warning(
                "h2 包未安装，HTTP/2 已禁用。建议安装: uv add httpx[http2]",
                extra={"action": "client_init_http2_fallback"},
            )
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=self.default_timeout,
                http2=False,
                follow_redirects=True,
            )
            http2_enabled = False

        logger.info(
            "✅ httpx 客户端已初始化",
            extra={
                "action": "client_init",
                "max_connections": max_connections,
                "max_keepalive_connections": max_keepalive_connections,
                "keepalive_expiry": keepalive_expiry,
                "default_timeout": self.default_timeout,
                "http2_enabled": http2_enabled,
            },
        )

    @property
    def token_service(self) -> ITokenService:
        """获取 Token 服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator

            self._token_service = ServiceLocator.get_token_service()
        return self._token_service

    @property
    def insurance_list_url(self) -> str:
        """获取保险公司列表 API URL"""
        return cast(
            str, get_config("services.insurance.list_url", "https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz")
        )

    @property
    def premium_query_url(self) -> str:
        """获取保险费率查询 API URL"""
        return cast(
            str,
            get_config(
                "services.insurance.premium_query_url", "https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium"
            ),
        )

    @property
    def default_timeout(self) -> float:
        """获取默认超时时间"""
        return cast(float, get_config("services.insurance.default_timeout", 60.0))

    @property
    def max_connections(self) -> int:
        """获取最大连接数"""
        return cast(int, get_config("services.insurance.max_connections", 100))

    async def close(self) -> None:
        """
        关闭客户端，释放连接池资源

        应该在应用关闭时调用此方法
        """
        await self._client.aclose()
        logger.info("httpx 客户端已关闭")

    async def __aenter__(self) -> "CourtInsuranceClient":
        """支持异步上下文管理器"""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """支持异步上下文管理器"""
        await self.close()

    async def fetch_insurance_companies( # type: ignore
        self, bearer_token: str, c_pid: str, fy_id: str, timeout: float | None = None, max_retries: int = 3
    ) -> list[InsuranceCompany]:
        """
        获取保险公司列表（带重试）

        Args:
            bearer_token: Bearer Token
            c_pid: 分类 ID
            fy_id: 法院 ID
            timeout: 超时时间（秒），默认使用 DEFAULT_TIMEOUT
            max_retries: 最大重试次数（默认 3 次）

        Returns:
            保险公司列表

        Raises:
            NetworkError: 网络错误（连接失败、超时等），会自动重试
            APIError: API 错误（HTTP 状态码错误、响应格式错误等），不会重试
            TokenError: Token 错误（Token 无效、过期等），不会重试
        """
        if timeout is None:
            timeout = self.default_timeout

        # 重试逻辑
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
                # 网络错误可以重试
                last_exception = e
                if attempt < max_retries:
                    retry_delay = attempt * 2  # 递增延迟：2秒、4秒、6秒
                    logger.warning(
                        f"获取保险公司列表失败（尝试 {attempt}/{max_retries}），{retry_delay}秒后重试: {e.message}",
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
                        f"获取保险公司列表失败，已达最大重试次数 {max_retries}",
                        extra={
                            "action": "fetch_insurance_companies_max_retries",
                            "max_retries": max_retries,
                            "error_code": e.code,
                        },
                    )
            except (APIError, TokenError) as e:
                # API 错误和 Token 错误不重试，直接抛出
                logger.error(
                    f"获取保险公司列表失败（不可重试）: {e.message}",
                    extra={
                        "action": "fetch_insurance_companies_non_retryable",
                        "error_code": e.code,
                        "error_type": type(e).__name__,
                    },
                )
                raise

        # 所有重试都失败，抛出最后一个异常
        if last_exception:
            raise last_exception

    def _parse_insurance_companies(self, data: Any) -> list[InsuranceCompany]:
        """从 API 响应中解析保险公司列表"""
        if isinstance(data, dict) and "data" in data:
            company_list = data.get("data", [])
        elif isinstance(data, list):
            company_list = data
        else:
            logger.warning(f"未知的响应格式: {data}")
            company_list = []

        companies = []
        for item in company_list:
            if not isinstance(item, dict):
                continue
            c_id, c_code, c_name = item.get("cId"), item.get("cCode"), item.get("cName")
            if c_id and c_code and c_name:
                companies.append(InsuranceCompany(c_id=str(c_id), c_code=str(c_code), c_name=str(c_name)))
            else:
                logger.warning(f"保险公司信息不完整，跳过: {item}")
        return companies

    async def _fetch_insurance_companies_once(
        self, bearer_token: str, c_pid: str, fy_id: str, timeout: float, attempt: int = 1
    ) -> list[InsuranceCompany]:
        """获取保险公司列表（单次尝试）"""
        import time

        headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
        params = {"cPid": c_pid, "fyId": fy_id}

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
            response = await self._client.get(
                self.insurance_list_url, headers=headers, params=params, timeout=timeout
            )
            elapsed_time = time.time() - start_time

            logger.info(
                "保险公司列表 API 响应",
                extra={
                    "action": "fetch_insurance_companies_response",
                    "status_code": response.status_code,
                    "response_time_seconds": round(elapsed_time, 3),
                },
            )

            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(
                    "获取保险公司列表失败",
                    extra={"action": "fetch_insurance_companies_error", "status_code": response.status_code},
                )
                raise httpx.HTTPStatusError(error_msg, request=response.request, response=response)

            companies = self._parse_insurance_companies(response.json())
            logger.info(
                f"✅ 成功获取 {len(companies)} 家保险公司",
                extra={"action": "fetch_insurance_companies_success", "companies_count": len(companies)},
            )
            if not companies:
                logger.warning(
                    "保险公司列表为空",
                    extra={"action": "fetch_insurance_companies_empty", "c_pid": c_pid, "fy_id": fy_id},
                )
            return companies

        except httpx.TimeoutException as e:
            error_msg = f"获取保险公司列表超时（{timeout}秒）"
            logger.error(
                error_msg,
                extra={"action": "fetch_insurance_companies_timeout", "timeout": timeout},
                exc_info=True,
            )
            raise NetworkError(
                message=error_msg,
                code="INSURANCE_LIST_TIMEOUT",
                errors={"url": self.insurance_list_url, "timeout": timeout, "original_error": str(e)},
            ) from e
        except httpx.HTTPStatusError as e:
            error_msg = f"获取保险公司列表失败: HTTP {e.response.status_code}"
            if 500 <= e.response.status_code < 600:
                logger.warning(
                    f"服务器错误（可重试）: {error_msg}",
                    extra={"action": "fetch_insurance_companies_server_error", "status_code": e.response.status_code},
                )
                raise NetworkError(
                    message=error_msg,
                    code="INSURANCE_LIST_SERVER_ERROR",
                    errors={
                        "url": self.insurance_list_url,
                        "status_code": e.response.status_code,
                        "original_error": str(e),
                    },
                ) from e
            logger.error(
                error_msg,
                extra={"action": "fetch_insurance_companies_http_status_error", "status_code": e.response.status_code},
                exc_info=True,
            )
            raise APIError(
                message=error_msg,
                code="INSURANCE_LIST_HTTP_ERROR",
                errors={
                    "url": self.insurance_list_url,
                    "status_code": e.response.status_code,
                    "original_error": str(e),
                },
            ) from e
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            error_msg = f"获取保险公司列表网络错误: {type(e).__name__}"
            logger.error(
                error_msg,
                extra={"action": "fetch_insurance_companies_network_error", "error_type": type(e).__name__},
                exc_info=True,
            )
            raise NetworkError(
                message=error_msg,
                code="INSURANCE_LIST_NETWORK_ERROR",
                errors={"url": self.insurance_list_url, "error_type": type(e).__name__, "original_error": str(e)},
            ) from e
        except httpx.HTTPError as e:
            error_msg = f"获取保险公司列表 HTTP 错误: {type(e).__name__}"
            logger.error(
                error_msg,
                extra={"action": "fetch_insurance_companies_http_error", "error_type": type(e).__name__},
                exc_info=True,
            )
            raise NetworkError(
                message=error_msg,
                code="INSURANCE_LIST_HTTP_ERROR",
                errors={"url": self.insurance_list_url, "error_type": type(e).__name__, "original_error": str(e)},
            ) from e
        except Exception as e:
            error_msg = f"获取保险公司列表失败: {type(e).__name__}"
            logger.error(
                error_msg,
                extra={"action": "fetch_insurance_companies_exception", "error_type": type(e).__name__},
                exc_info=True,
            )
            raise APIError(
                message=error_msg,
                code="INSURANCE_LIST_ERROR",
                errors={"url": self.insurance_list_url, "error_type": type(e).__name__, "original_error": str(e)},
            ) from e




    async def fetch_premium(
        self, bearer_token: str, preserve_amount: Decimal, institution: str, corp_id: str, timeout: float | None = None
    ) -> PremiumResult:
        """
        查询单个保险公司报价

        注意：此方法不会抛出异常，而是返回包含错误信息的 PremiumResult。
        这样设计是为了支持并发查询时，单个查询失败不影响其他查询。
        """
        import json
        import time

        if timeout is None:
            timeout = self.default_timeout

        headers, params, request_body, request_info = self._build_premium_request(
            bearer_token, preserve_amount, institution, corp_id, timeout
        )
        company = InsuranceCompany(c_id="", c_code=institution, c_name="")

        try:
            start_time = time.time()
            response = await self._client.post(
                self.premium_query_url,
                headers=headers,
                params=params,
                json=request_body,
                timeout=timeout,
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

            if response.status_code != 200:
                return self._make_failed_result(
                    company,
                    f"HTTP {response.status_code}",
                    Exception(response.text),
                    request_info,
                    extra={"institution": institution, "status_code": response.status_code},
                )

            data: dict[str, Any] = response.json()
            premium = self._parse_premium_from_response(data, institution, elapsed_time)

            if premium is not None:
                success_msg = json.dumps(
                    {
                        "status": "success",
                        "request": request_info,
                        "response": {"body": data, "elapsed_seconds": round(elapsed_time, 3)},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                logger.info(
                    f"保险公司 {institution} 报价: ¥{premium}",
                    extra={"action": "fetch_premium_success", "institution": institution, "premium": str(premium)},
                )
                return PremiumResult(
                    company=company, premium=premium, status="success",
                    error_message=success_msg, response_data=data, request_info=request_info,
                )

            logger.warning(
                f"保险公司 {institution}: 响应中未找到费率数据",
                extra={"action": "fetch_premium_no_premium", "institution": institution},
            )
            return PremiumResult(
                company=company, premium=None, status="failed",
                error_message=_("响应中未找到费率数据"), response_data=data, request_info=request_info, # type: ignore
            )

        except httpx.TimeoutException as e:
            return self._make_failed_result(
                company, "查询超时", e, request_info,
                extra={"institution": institution, "timeout": timeout},
            )
        except httpx.HTTPError as e:
            return self._make_failed_result(
                company, "HTTP 错误", e, request_info,
                extra={"institution": institution},
            )
        except Exception as e:
            return self._make_failed_result(
                company, "未知错误", e, request_info,
                log_level="error",
                extra={"institution": institution},
            )

    async def fetch_all_premiums(
        self,
        bearer_token: str,
        preserve_amount: Decimal,
        corp_id: str,
        companies: list[InsuranceCompany],
        timeout: float | None = None,
    ) -> list[PremiumResult]:
        """
        并发查询所有保险公司报价

        使用 asyncio.gather 并发执行所有查询，单个查询失败不影响其他查询。

        Args:
            bearer_token: Bearer Token
            preserve_amount: 保全金额
            corp_id: 企业/法院 ID
            companies: 保险公司列表
            timeout: 超时时间（秒），默认使用 DEFAULT_TIMEOUT

        Returns:
            所有保险公司的报价结果列表
        """
        if not companies:
            logger.warning(
                "保险公司列表为空，无法查询报价",
                extra={
                    "action": "fetch_all_premiums_empty",
                },
            )
            return []

        # 记录并发查询开始
        logger.info(
            f"开始并发查询 {len(companies)} 家保险公司报价",
            extra={
                "action": "fetch_all_premiums_start",
                "preserve_amount": str(preserve_amount),
                "corp_id": corp_id,
                "total_companies": len(companies),
                "timeout": timeout,
            },
        )

        # 使用分批并发 + 延迟策略，避免请求过快
        import time

        start_time = time.time()

        # 配置：每批并发数量和批次间延迟
        BATCH_SIZE = 2  # 每批最多2个并发请求（降低并发数）
        BATCH_DELAY = 2.0  # 批次间延迟2秒（增加延迟）
        REQUEST_DELAY = 0.5  # 同一批次内请求间延迟0.5秒（增加延迟）

        logger.info(
            f"使用分批并发策略: 每批{BATCH_SIZE}个请求，批次间延迟{BATCH_DELAY}秒，请求间延迟{REQUEST_DELAY}秒",
            extra={
                "action": "fetch_all_premiums_batch_strategy",
                "batch_size": BATCH_SIZE,
                "batch_delay": BATCH_DELAY,
                "request_delay": REQUEST_DELAY,
            },
        )

        results = []

        # 分批处理
        for batch_idx in range(0, len(companies), BATCH_SIZE):
            batch_companies = companies[batch_idx : batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            total_batches = (len(companies) + BATCH_SIZE - 1) // BATCH_SIZE

            logger.info(
                f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch_companies)} 家保险公司",
                extra={
                    "action": "fetch_all_premiums_batch_start",
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_size": len(batch_companies),
                },
            )

            # 创建当前批次的任务（带延迟）
            batch_tasks = []
            for idx, company in enumerate(batch_companies):
                # 同一批次内的请求也添加小延迟
                if idx > 0:
                    await asyncio.sleep(REQUEST_DELAY)

                task = self.fetch_premium(
                    bearer_token=bearer_token,
                    preserve_amount=preserve_amount,
                    institution=company.c_code,
                    corp_id=corp_id,
                    timeout=timeout,
                )
                batch_tasks.append(task)

            # 并发执行当前批次
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            results.extend(batch_results)

            # 批次间延迟（最后一批不需要延迟）
            if batch_idx + BATCH_SIZE < len(companies):
                logger.info(
                    f"批次 {batch_num} 完成，等待 {BATCH_DELAY} 秒后处理下一批",
                    extra={
                        "action": "fetch_all_premiums_batch_delay",
                        "batch_num": batch_num,
                        "delay_seconds": BATCH_DELAY,
                    },
                )
                await asyncio.sleep(BATCH_DELAY)

        elapsed_time = time.time() - start_time

        # 处理结果
        premium_results = []
        for i, result in enumerate(results):
            company = companies[i]

            if isinstance(result, Exception):
                # 任务抛出异常（记录完整堆栈信息）
                error_msg = f"查询异常: {result!s}"
                logger.error(
                    f"保险公司 {company.c_name} ({company.c_code}) {error_msg}",
                    extra={
                        "action": "fetch_all_premiums_task_exception",
                        "company_name": company.c_name,
                        "company_code": company.c_code,
                        "error_type": type(result).__name__,
                        "error_message": str(result),
                    },
                    exc_info=result,  # 记录完整堆栈信息
                )
                premium_results.append(
                    PremiumResult(
                        company=company,
                        premium=None,
                        status="failed",
                        error_message=error_msg,
                        response_data=None,
                    )
                )
            elif isinstance(result, PremiumResult):
                # 正常返回结果，补充公司信息
                result.company.c_id = company.c_id
                result.company.c_name = company.c_name
                premium_results.append(result)
            else:
                # 未知结果类型
                error_msg = f"未知结果类型: {type(result)}"
                logger.error(
                    f"保险公司 {company.c_name} ({company.c_code}) {error_msg}",
                    extra={
                        "action": "fetch_all_premiums_unknown_result",
                        "company_name": company.c_name,
                        "company_code": company.c_code,
                        "result_type": str(type(result)),
                    },
                )
                premium_results.append(
                    PremiumResult(
                        company=company,
                        premium=None,
                        status="failed",
                        error_message=error_msg,
                        response_data=None,
                    )
                )

        # 统计结果
        success_count = sum(1 for r in premium_results if r.status == "success")
        failed_count = len(premium_results) - success_count

        # 记录并发查询完成（包含执行时长和统计信息）
        logger.info(
            "✅ 并发查询完成",
            extra={
                "action": "fetch_all_premiums_complete",
                "total_time_seconds": round(elapsed_time, 2),
                "total_companies": len(companies),
                "success_count": success_count,
                "failed_count": failed_count,
                "success_rate": round(success_count / len(companies) * 100, 2) if companies else 0,
                "avg_time_per_company": round(elapsed_time / len(companies), 3) if companies else 0,
            },
        )

        return premium_results
