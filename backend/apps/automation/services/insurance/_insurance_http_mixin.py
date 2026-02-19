"""保险 HTTP 请求构建与响应解析 Mixin"""

import json
import logging
import time
import traceback
from decimal import Decimal
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("apps.automation")

if TYPE_CHECKING:
    from .court_insurance_client import InsuranceCompany, PremiumResult


class InsuranceHttpMixin:
    """保险 HTTP 请求构建、响应解析、失败结果构建 Mixin"""

    @property
    def premium_query_url(self) -> str:
        """获取保险费率查询 API URL（由主类实现）"""
        raise NotImplementedError

    def _build_premium_request(
        self, bearer_token: str, preserve_amount: Decimal, institution: str, corp_id: str, timeout: float
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, Any]]:
        """构建询价请求的 headers、params、body 和 request_info"""
        current_time_ms = str(int(time.time() * 1000))
        preserve_amount_str = str(int(preserve_amount))

        headers: dict[str, str] = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Bearer": bearer_token,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://zxfw.court.gov.cn",
            "Pragma": "no-cache",
            "Referer": "https://zxfw.court.gov.cn/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
            ),
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        params: dict[str, str] = {
            "time": current_time_ms,
            "preserveAmount": preserve_amount_str,
            "institution": institution,
            "corpId": corp_id,
        }
        body: dict[str, str] = {
            "preserveAmount": preserve_amount_str,
            "institution": institution,
            "corpId": corp_id,
        }
        request_info: dict[str, Any] = {
            "url": self.premium_query_url,
            "method": "POST",
            "timestamp": current_time_ms,
            "params": params.copy(),
            "body": body.copy(),
            "headers": {k: v[:50] + "..." if k == "Bearer" and len(v) > 50 else v for k, v in headers.items()},
            "timeout": timeout,
        }
        logger.info(
            f"查询保险公司报价: {institution}",
            extra={
                "action": "fetch_premium_request",
                "institution": institution,
                "timestamp": current_time_ms,
                "preserve_amount": preserve_amount_str,
            },
        )
        return headers, params, body, request_info

    def _parse_premium_from_response(
        self, data: dict[str, Any], institution: str, elapsed_time: float
    ) -> Decimal | None:
        """从响应数据中提取报价金额"""
        rate_data = data.get("data", {}) if isinstance(data, dict) else {}
        if not rate_data:
            return None
        premium_value = rate_data.get("minPremium") or rate_data.get("minAmount")
        if premium_value is None:
            return None
        try:
            return Decimal(str(premium_value))
        except (ValueError, TypeError) as e:
            logger.warning(f"无法解析报价金额: {premium_value}, 错误: {e}")
            return None

    def _make_failed_result(
        self,
        company: "InsuranceCompany",
        error_label: str,
        exc: BaseException,
        request_info: dict[str, Any],
        response_data: dict[str, Any] | None = None,
        log_level: str = "warning",
        extra: dict[str, Any] | None = None,
    ) -> "PremiumResult":
        """构建失败的 PremiumResult"""
        from .court_insurance_client import PremiumResult

        error_details: dict[str, Any] = {
            "error": error_label,
            "exception": str(exc),
            "exception_type": type(exc).__name__,
            "request": request_info,
        }
        if log_level == "error":
            error_details["traceback"] = traceback.format_exc()
        error_msg = json.dumps(error_details, ensure_ascii=False, indent=2)
        log_extra = {"action": f"fetch_premium_{log_level}", **(extra or {})}
        getattr(logger, log_level)(error_label, extra=log_extra, exc_info=(log_level == "error"))
        return PremiumResult(
            company=company,
            premium=None,
            status="failed",
            error_message=error_msg,
            response_data=response_data,
            request_info=request_info,
        )
