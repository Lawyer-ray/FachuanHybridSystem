"""
自动Token获取核心服务

实现财产保险询价任务的自动token获取机制。当系统检测到没有有效token时，
将自动触发法院一张网登录流程，获取新token后继续执行询价任务。
集成性能监控、缓存管理和并发优化。
"""

import asyncio
import logging
import time
from typing import Any, ClassVar

from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
    ValidationException,
)
from apps.core.interfaces import (
    AccountCredentialDTO,
    IAccountSelectionStrategy,
    IAutoLoginService,
    ITokenService,
)

from .cache_manager import cache_manager
from .concurrency_optimizer import ConcurrencyConfig, concurrency_optimizer
from .history_recorder import history_recorder
from .performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class AutoTokenAcquisitionService:
    """
    自动Token获取核心服务实现

    功能：
    1. 检查token有效性，无效时自动获取
    2. 集成账号选择策略和自动登录服务
    3. 实现并发控制，避免多个任务同时触发登录
    4. 提供结构化日志记录，包含完整的执行轨迹
    5. 支持指定凭证ID或自动选择账号
    """

    # 类级别的并发控制
    _active_acquisitions: ClassVar[set[str]] = set()
    _acquisition_locks: ClassVar[dict[str, asyncio.Lock]] = {}
    _lock_creation_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(
        self,
        account_selection_strategy: IAccountSelectionStrategy | None = None,
        auto_login_service: IAutoLoginService | None = None,
        token_service: ITokenService | None = None,
        concurrency_config: ConcurrencyConfig | None = None,
    ):
        """
        初始化自动Token获取服务

        Args:
            account_selection_strategy: 账号选择策略，None则延迟加载默认实现
            auto_login_service: 自动登录服务，None则延迟加载默认实现
            token_service: Token服务，None则延迟加载默认实现
            concurrency_config: 并发控制配置，None则使用默认配置
        """
        self._account_selection_strategy = account_selection_strategy
        self._auto_login_service = auto_login_service
        self._token_service = token_service
        self.concurrency_config = concurrency_config or ConcurrencyConfig()

        # 执行统计（保留用于向后兼容）
        self._acquisition_count = 0
        self._success_count = 0
        self._failure_count = 0

    @property
    def account_selection_strategy(self) -> IAccountSelectionStrategy:
        """获取账号选择策略（延迟加载）"""
        if self._account_selection_strategy is None:
            from apps.core.dependencies import build_account_selection_strategy

            self._account_selection_strategy = build_account_selection_strategy()
        return self._account_selection_strategy

    @property
    def auto_login_service(self) -> IAutoLoginService:
        """获取自动登录服务（延迟加载）"""
        if self._auto_login_service is None:
            from apps.core.dependencies import build_auto_login_service

            self._auto_login_service = build_auto_login_service()
        return self._auto_login_service

    @property
    def token_service(self) -> ITokenService:
        """获取Token服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.dependencies import build_token_service

            self._token_service = build_token_service()
        return self._token_service

    def _get_login_handler(self) -> "Any":
        """获取登录处理器（延迟创建）"""
        from ._login_handler import LoginHandler

        return LoginHandler(
            account_selection_strategy=self.account_selection_strategy,
            auto_login_service=self.auto_login_service,
            token_service=self.token_service,
            concurrency_config=self.concurrency_config,
        )

    async def acquire_token_if_needed(self, site_name: str, credential_id: int | None = None) -> str:
        """
        如果需要则自动获取token

        Args:
            site_name: 网站名称
            credential_id: 指定的凭证ID（可选）

        Returns:
            有效的token字符串

        Raises:
            AutoTokenAcquisitionError: Token获取失败
            ValidationException: 参数验证失败
            NoAvailableAccountError: 无可用账号
            TokenAcquisitionTimeoutError: 获取超时
        """
        start_time = time.time()
        acquisition_id = f"{site_name}_{credential_id or 'auto'}_{int(start_time)}"

        # 参数验证
        if not site_name or not site_name.strip():
            raise ValidationException(
                message="网站名称不能为空",
                code="INVALID_SITE_NAME",
                errors={"site_name": "网站名称不能为空"},
            )

        from apps.automation.utils.logging import AutomationLogger

        AutomationLogger.log_token_acquisition_start(
            acquisition_id=acquisition_id,
            site_name=site_name,
            credential_id=credential_id,
            trigger_reason="token_needed",
        )

        self._acquisition_count += 1

        # 记录性能监控开始
        performance_monitor.record_acquisition_start(
            acquisition_id,
            site_name,
            credential_id or "auto", # type: ignore
        )

        try:
            # 并发控制和资源获取
            await concurrency_optimizer.acquire_resource(
                acquisition_id,
                site_name,
                credential_id or "auto", # type: ignore
            )

            try:
                # 再次检查token（可能在等待期间已被其他任务获取）
                credential, existing_token = await self._resolve_credential_and_token(
                    site_name, credential_id, acquisition_id
                )
                if existing_token:
                    return existing_token

                # 执行自动登录获取token
                login_handler = self._get_login_handler()
                result = await login_handler.acquire_token_by_login(
                    acquisition_id, site_name, credential_id, credential
                )

                total_duration = time.time() - start_time

                if result.success:
                    self._success_count += 1

                    # 记录性能监控结束（成功）
                    performance_monitor.record_acquisition_end(
                        acquisition_id,
                        True,
                        total_duration,
                        result.login_attempts[0].attempt_duration if result.login_attempts else None,
                    )

                    # 记录历史到数据库
                    await history_recorder.record_acquisition_history(
                        acquisition_id,
                        site_name,
                        credential.account if credential else "unknown",
                        credential_id,
                        result,
                        "token_needed",
                    )

                    AutomationLogger.log_token_acquisition_success(
                        acquisition_id=acquisition_id,
                        site_name=site_name,
                        account=credential.account, # type: ignore
                        total_duration=total_duration,
                        acquisition_method=result.acquisition_method,
                        login_attempts=len(result.login_attempts),
                        success_rate=self._success_count / self._acquisition_count,
                    )
                    return result.token # type: ignore
                else:
                    self._failure_count += 1
                    error_msg = f"Token获取失败: {result.error_details.get('message', '未知错误')}"

                    # 记录性能监控结束（失败）
                    error_type = result.error_details.get("error_type", "unknown")
                    performance_monitor.record_acquisition_end(
                        acquisition_id, False, total_duration, error_type=error_type
                    )

                    # 记录历史到数据库
                    await history_recorder.record_acquisition_history(
                        acquisition_id,
                        site_name,
                        credential.account if credential else "unknown",
                        credential_id,
                        result,
                        "token_needed",
                    )

                    logger.error(
                        "Token获取失败",
                        extra={
                            "acquisition_id": acquisition_id,
                            "site_name": site_name,
                            "total_duration": total_duration,
                            "error_details": result.error_details,
                            "login_attempts": len(result.login_attempts),
                            "failure_rate": self._failure_count / self._acquisition_count,
                        },
                    )
                    raise AutoTokenAcquisitionError(
                        message=error_msg,
                        code="TOKEN_ACQUISITION_FAILED",
                        errors=result.error_details,
                    )

            finally:
                # 释放并发资源
                await concurrency_optimizer.release_resource(
                    acquisition_id,
                    site_name,
                    credential_id or "auto", # type: ignore
                )

        except Exception as e:
            total_duration = time.time() - start_time

            # 记录性能监控结束（异常）
            error_type = type(e).__name__
            performance_monitor.record_acquisition_end(acquisition_id, False, total_duration, error_type=error_type)

            if isinstance(
                e,
                (
                    AutoTokenAcquisitionError,
                    ValidationException,
                    NoAvailableAccountError,
                    TokenAcquisitionTimeoutError,
                ),
            ):
                raise
            else:
                self._failure_count += 1
                logger.error(
                    "Token获取过程中发生未预期错误",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "error": str(e),
                        "total_duration": total_duration,
                    },
                    exc_info=True,
                )

                raise AutoTokenAcquisitionError(
                    message=f"Token获取过程中发生未预期错误: {e!s}",
                    code="TOKEN_ACQUISITION_ERROR",
                    errors={"original_error": str(e)},
                ) from e

    async def _get_acquisition_lock(self, site_name: str) -> asyncio.Lock:
        """获取站点级别的获取锁"""
        async with self._lock_creation_lock:
            if site_name not in self._acquisition_locks:
                self._acquisition_locks[site_name] = asyncio.Lock()
            return self._acquisition_locks[site_name]

    async def _check_any_valid_token(self, site_name: str) -> str | None:
        """检查是否有任何有效token"""
        try:
            available_accounts = await self.account_selection_strategy.select_account(site_name)
            if not available_accounts:
                return None

            token = await self.token_service.get_token_internal(site_name, available_accounts.account) # type: ignore
            if token:
                logger.info(
                    "找到有效Token",
                    extra={"site_name": site_name, "account": available_accounts.account},
                )
                return token # type: ignore

            return None

        except Exception as e:
            logger.warning(f"检查现有Token时发生错误: {e!s}")
            return None

    async def _get_cached_or_db_token(self, site_name: str, account: str) -> str | None:
        """先查缓存，再查数据库，命中时回填缓存"""
        token = cache_manager.get_cached_token(site_name, account)
        if not token:
            token = await self.token_service.get_token_internal(site_name, account) # type: ignore
            if token:
                cache_manager.cache_token(site_name, account, token)
        return token

    async def _resolve_credential_and_token(
        self,
        site_name: str,
        credential_id: int | None,
        acquisition_id: str,
    ) -> tuple[AccountCredentialDTO | None, str | None]:
        """
        解析凭证并检查是否已有有效 token。

        Returns:
            (credential, existing_token)，existing_token 非 None 时可直接返回
        """
        if credential_id:
            login_handler = self._get_login_handler()
            credential = await login_handler._get_credential_by_id(credential_id)
            if not credential:
                raise ValidationException(f"无效的凭证ID: {credential_id}")
            existing_token = await self._get_cached_or_db_token(site_name, credential.account)
            if existing_token:
                logger.info(
                    "使用现有Token（指定凭证）",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account,
                        "acquisition_method": "existing",
                    },
                )
            return credential, existing_token

        credential = await self.account_selection_strategy.select_account(site_name)
        if not credential:
            logger.error(
                "没有找到可用账号",
                extra={"acquisition_id": acquisition_id, "site_name": site_name},
            )
            raise NoAvailableAccountError(
                "没有找到法院一张网的账号凭证\n\n"
                "请在 Admin 后台添加账号：\n"
                "1. 访问 /admin/organization/accountcredential/\n"
                "2. 点击「添加账号密码」\n"
                "3. URL 填写：https://zxfw.court.gov.cn\n"
                "4. 填写账号和密码\n"
                "5. 保存后重新执行询价"
            )
        existing_token = await self._get_cached_or_db_token(site_name, credential.account)
        if existing_token:
            logger.info(
                "使用现有Token（自动选择账号）",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                },
            )
        return credential, existing_token

    def get_statistics(self) -> dict[str, Any]:
        """获取服务统计信息"""
        return {
            "acquisition_count": self._acquisition_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "success_rate": (self._success_count / self._acquisition_count if self._acquisition_count > 0 else 0),
            "active_acquisitions": len(self._active_acquisitions),
            "active_locks": len(self._acquisition_locks),
        }

    def reset_statistics(self) -> None:
        """重置统计信息"""
        self._acquisition_count = 0
        self._success_count = 0
        self._failure_count = 0

    @classmethod
    def clear_locks(cls) -> None:
        """清除所有锁（用于测试）"""
        cls._active_acquisitions.clear()
        cls._acquisition_locks.clear()
