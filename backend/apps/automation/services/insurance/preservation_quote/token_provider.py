"""Business logic services."""

import logging
from typing import Any

from apps.automation.services.insurance.exceptions import TokenError
from apps.automation.services.wiring import get_baoquan_token_service

logger = logging.getLogger("apps.automation")


class BaoquanTokenProvider:
    def __init__(
        self,
        *,
        baoquan_token_service: Any | None = None,
        token_service: Any | None = None,
        auto_token_service: Any | None = None,
    ) -> None:
        self._baoquan_token_service = baoquan_token_service
        self._token_service = token_service
        self._auto_token_service = auto_token_service

    @property
    def baoquan_token_service(self) -> Any:
        if self._baoquan_token_service is None:
            self._baoquan_token_service = get_baoquan_token_service()
        return self._baoquan_token_service

    async def get_token(self, credential_id: int | None = None) -> Any:
        if self._token_service is not None:
            token = self._token_service.get_token(site_name="court_zxfw", account=None)
            if token:
                return token
            raise TokenError(
                "Token 不存在或已过期,请先在后台手动获取 Token.\n\n"
                "备用方案:\n"
                "1. 访问 Django Admin: /admin/automation/testcourt/\n"
                "2. 点击「测试登录」按钮,手动获取 Token\n"
                "3. 重新执行询价任务\n"
            )

        logger.info(
            "开始获取保全系统 Token (HS512)",
            extra={
                "action": "get_baoquan_token_start",
                "credential_id": credential_id,
            },
        )
        try:
            if self._auto_token_service is not None:
                await self._auto_token_service.acquire_token_if_needed(
                    site_name="court_zxfw", credential_id=credential_id
                )
            token = await self.baoquan_token_service.get_valid_baoquan_token(credential_id)
            logger.info(
                "✅ 保全系统 Token 获取成功",
                extra={
                    "action": "get_baoquan_token_success",
                    "credential_id": credential_id,
                    "token_loaded": bool(token),
                },
            )
            return token
        except Exception as e:
            logger.error(
                f"❌ 保全系统 Token 获取失败: {e}",
                extra={
                    "action": "get_baoquan_token_failed",
                    "credential_id": credential_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            error_msg = (
                f"❌ 保全系统 Token 获取失败: {e!s}\n\n"
                "备用方案:\n"
                "1. 访问 Django Admin: /admin/automation/testcourt/\n"
                "2. 点击「测试登录」按钮,手动获取 Token\n"
                "3. 重新执行询价任务\n"
            )
            raise TokenError(error_msg) from e
