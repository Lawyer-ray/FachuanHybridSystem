"""
群主设置重试配置和策略

本模块实现了群主设置过程中的重试机制，包括：
- 重试配置管理
- 指数退避算法
- 不同错误类型的重试策略
- 重试状态跟踪

Requirements: 3.3, 3.4
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)


def _get_system_config_service() -> "SystemConfigService":
    from apps.core.services.system_config_service import SystemConfigService

    return SystemConfigService()


if TYPE_CHECKING:
    from apps.core.services.system_config_service import SystemConfigService


class RetryErrorType(Enum):
    """重试错误类型枚举"""

    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    PERMISSION_ERROR = "permission_error"
    NOT_FOUND_ERROR = "not_found_error"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN_ERROR = "unknown_error"


class RetryStrategy(Enum):
    """重试策略枚举"""

    NO_RETRY = "no_retry"
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"


@dataclass
class RetryAttempt:
    """重试尝试记录"""

    attempt_number: int
    timestamp: datetime
    error_type: RetryErrorType
    error_message: str
    delay_seconds: float
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "timestamp": self.timestamp.isoformat(),
            "error_type": self.error_type.value,
            "error_message": self.error_message,
            "delay_seconds": self.delay_seconds,
            "success": self.success,
        }


@dataclass
class ErrorStrategyConfig:
    """单个错误类型的重试策略配置"""

    strategy: RetryStrategy
    max_retries: int
    base_delay: float
    backoff_factor: float
    max_delay: float


class RetryConfig:
    """重试配置类

    Requirements: 3.3, 3.4
    """

    def __init__(self) -> None:
        self._load_config()

    def _load_config(self) -> None:
        """从 SystemConfigService 加载重试配置"""
        svc = _get_system_config_service()

        def _get_bool(key: str, default: bool) -> bool:
            val = svc.get_value(key, "")
            if not val:
                return default
            return val.lower() in ("true", "1", "yes")

        def _get_int(key: str, default: int) -> int:
            val = svc.get_value(key, "")
            try:
                return int(val) if val else default
            except ValueError:
                return default

        def _get_float(key: str, default: float) -> float:
            val = svc.get_value(key, "")
            try:
                return float(val) if val else default
            except ValueError:
                return default

        self.enabled: bool = _get_bool("FEISHU_OWNER_RETRY_ENABLED", True)
        self.max_retries: int = _get_int("FEISHU_OWNER_MAX_RETRIES", 3)
        self.base_delay: float = _get_float("FEISHU_OWNER_RETRY_BASE_DELAY", 1.0)
        self.max_delay: float = _get_float("FEISHU_OWNER_RETRY_MAX_DELAY", 60.0)
        self.backoff_factor: float = _get_float("FEISHU_OWNER_RETRY_BACKOFF_FACTOR", 2.0)
        self.timeout_seconds: float = _get_float("FEISHU_OWNER_RETRY_TIMEOUT", 300.0)

        self.error_strategies: dict[RetryErrorType, ErrorStrategyConfig] = {
            RetryErrorType.NETWORK_ERROR: ErrorStrategyConfig(
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                max_retries=self.max_retries,
                base_delay=self.base_delay,
                backoff_factor=self.backoff_factor,
                max_delay=self.max_delay,
            ),
            RetryErrorType.TIMEOUT_ERROR: ErrorStrategyConfig(
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                max_retries=max(1, self.max_retries - 1),
                base_delay=self.base_delay * 2,
                backoff_factor=self.backoff_factor,
                max_delay=self.max_delay,
            ),
            RetryErrorType.PERMISSION_ERROR: ErrorStrategyConfig(
                strategy=RetryStrategy.NO_RETRY,
                max_retries=0,
                base_delay=0.0,
                backoff_factor=1.0,
                max_delay=0.0,
            ),
            RetryErrorType.NOT_FOUND_ERROR: ErrorStrategyConfig(
                strategy=RetryStrategy.FIXED_DELAY,
                max_retries=1,
                base_delay=5.0,
                backoff_factor=1.0,
                max_delay=5.0,
            ),
            RetryErrorType.VALIDATION_ERROR: ErrorStrategyConfig(
                strategy=RetryStrategy.NO_RETRY,
                max_retries=0,
                base_delay=0.0,
                backoff_factor=1.0,
                max_delay=0.0,
            ),
            RetryErrorType.UNKNOWN_ERROR: ErrorStrategyConfig(
                strategy=RetryStrategy.LINEAR_BACKOFF,
                max_retries=max(1, self.max_retries - 1),
                base_delay=self.base_delay,
                backoff_factor=1.5,
                max_delay=self.max_delay / 2,
            ),
        }

        logger.debug(f"已加载重试配置: enabled={self.enabled}, max_retries={self.max_retries}")

    def is_enabled(self) -> bool:
        return self.enabled

    def get_max_retries(self, error_type: RetryErrorType | None = None) -> int:
        if error_type and error_type in self.error_strategies:
            return self.error_strategies[error_type].max_retries
        return self.max_retries

    def get_strategy(self, error_type: RetryErrorType) -> RetryStrategy:
        if error_type in self.error_strategies:
            return self.error_strategies[error_type].strategy
        return RetryStrategy.EXPONENTIAL_BACKOFF

    def should_retry(self, error_type: RetryErrorType, attempt_count: int) -> bool:
        if not self.enabled:
            return False
        strategy = self.get_strategy(error_type)
        if strategy == RetryStrategy.NO_RETRY:
            return False
        return attempt_count < self.get_max_retries(error_type)

    def calculate_delay(self, error_type: RetryErrorType, attempt_number: int) -> float:
        if error_type not in self.error_strategies:
            error_type = RetryErrorType.UNKNOWN_ERROR

        cfg = self.error_strategies[error_type]

        if cfg.strategy == RetryStrategy.NO_RETRY:
            return 0.0
        elif cfg.strategy == RetryStrategy.FIXED_DELAY:
            return min(cfg.base_delay, cfg.max_delay)
        elif cfg.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = cfg.base_delay + (attempt_number * cfg.backoff_factor)
            return min(delay, cfg.max_delay)
        else:  # EXPONENTIAL_BACKOFF（含默认）
            delay = cfg.base_delay * (cfg.backoff_factor**attempt_number)
            return min(delay, cfg.max_delay)

    def get_timeout_seconds(self) -> float:
        return self.timeout_seconds


class RetryManager:
    """重试管理器

    管理重试过程的执行，包括：
    - 重试逻辑控制
    - 重试历史记录
    - 超时控制
    - 错误分类

    Requirements: 3.3, 3.4
    """

    def __init__(self, config: RetryConfig | None = None):
        """初始化重试管理器

        Args:
            config: 重试配置，如果不提供则使用默认配置
        """
        self.config = config or RetryConfig()
        self.attempts: list[RetryAttempt] = []
        self.start_time: datetime | None = None

    def _classify_by_message(self, error_message: str) -> RetryErrorType:
        """根据错误消息分类"""
        if "timeout" in error_message or "timed out" in error_message:
            return RetryErrorType.TIMEOUT_ERROR
        if "network" in error_message or "connection" in error_message:
            return RetryErrorType.NETWORK_ERROR
        if "permission" in error_message or "forbidden" in error_message:
            return RetryErrorType.PERMISSION_ERROR
        if "not found" in error_message or "does not exist" in error_message:
            return RetryErrorType.NOT_FOUND_ERROR
        return RetryErrorType.UNKNOWN_ERROR

    def classify_error(self, exception: Exception) -> RetryErrorType:
        """分类错误类型"""
        import httpx

        from apps.core.exceptions import (
            NetworkError,
            NotFoundError,
            OwnerSettingException,
            PermissionDenied,
            ValidationException,
        )

        if isinstance(exception, OwnerSettingException):
            code = getattr(exception, "code", "")
            _owner_code_map = {
                "OWNER_PERMISSION_ERROR": RetryErrorType.PERMISSION_ERROR,
                "OWNER_NOT_FOUND": RetryErrorType.NOT_FOUND_ERROR,
                "OWNER_VALIDATION_ERROR": RetryErrorType.VALIDATION_ERROR,
                "OWNER_TIMEOUT_ERROR": RetryErrorType.TIMEOUT_ERROR,
                "OWNER_NETWORK_ERROR": RetryErrorType.NETWORK_ERROR,
            }
            if code in _owner_code_map:
                return _owner_code_map[code]

        if isinstance(exception, PermissionDenied):
            return RetryErrorType.PERMISSION_ERROR
        if isinstance(exception, NotFoundError):
            return RetryErrorType.NOT_FOUND_ERROR
        if isinstance(exception, ValidationException):
            return RetryErrorType.VALIDATION_ERROR
        if isinstance(exception, (NetworkError, httpx.RequestError)):
            return RetryErrorType.NETWORK_ERROR
        return self._classify_by_message(str(exception).lower())

    def execute_with_retry(
        self, operation: Callable[[], Any], operation_name: str = "operation", context: dict[str, Any] | None = None
    ) -> Any:
        """执行带重试的操作

        Args:
            operation: 要执行的操作函数
            operation_name: 操作名称（用于日志）
            context: 操作上下文信息

        Returns:
            Any: 操作结果

        Raises:
            Exception: 重试失败后抛出最后一次的异常
        """
        self.start_time = datetime.now()
        self.attempts = []
        context = context or {}

        logger.info(f"开始执行带重试的操作: {operation_name}")

        attempt_number = 0
        last_exception = None

        while True:
            try:
                # 检查总超时
                if self._is_total_timeout():
                    logger.error(f"操作总超时: {operation_name}, 耗时: {self._get_elapsed_time():.2f}秒")
                    from apps.core.exceptions import owner_timeout_error

                    raise owner_timeout_error(
                        message=f"操作总超时: {operation_name}",
                        timeout_seconds=self.config.get_timeout_seconds(),
                        errors={
                            "operation_name": operation_name,
                            "elapsed_time": self._get_elapsed_time(),
                            "attempts": len(self.attempts),
                            "context": context,
                        },
                    )

                # 执行操作
                logger.debug(f"执行操作尝试 {attempt_number + 1}: {operation_name}")
                result = operation()

                # 操作成功
                if self.attempts:
                    # 更新最后一次尝试为成功
                    self.attempts[-1].success = True

                logger.info(f"操作成功: {operation_name}, 尝试次数: {attempt_number + 1}")
                return result

            except Exception as e:
                last_exception = e
                error_type = self.classify_error(e)

                logger.warning(
                    f"操作失败: {operation_name}, 尝试 {attempt_number + 1}, 错误类型: {error_type.value}, 错误: {e!s}"
                )

                # 检查是否应该重试
                if not self.config.should_retry(error_type, attempt_number):
                    logger.error(f"不再重试: {operation_name}, 错误类型: {error_type.value}")
                    break

                # 计算延迟时间
                delay = self.config.calculate_delay(error_type, attempt_number)

                # 记录重试尝试
                attempt = RetryAttempt(
                    attempt_number=attempt_number + 1,
                    timestamp=datetime.now(),
                    error_type=error_type,
                    error_message=str(e),
                    delay_seconds=delay,
                    success=False,
                )
                self.attempts.append(attempt)

                # 如果有延迟，等待
                if delay > 0:
                    logger.info(f"等待重试: {operation_name}, 延迟 {delay:.2f} 秒")
                    time.sleep(delay)

                attempt_number += 1

        # 所有重试都失败了
        logger.error(f"操作最终失败: {operation_name}, 总尝试次数: {len(self.attempts)}")

        # 抛出最后一次的异常
        if last_exception:
            raise last_exception
        else:
            from apps.core.exceptions import owner_retry_error

            raise owner_retry_error(
                message=f"操作重试失败: {operation_name}",
                retry_count=len(self.attempts),
                max_retries=self.config.max_retries,
                errors={
                    "operation_name": operation_name,
                    "attempts": [attempt.to_dict() for attempt in self.attempts],
                    "context": context,
                },
            )

    def _is_total_timeout(self) -> bool:
        """检查是否总超时"""
        if not self.start_time:
            return False

        elapsed = self._get_elapsed_time()
        return elapsed >= self.config.get_timeout_seconds()

    def _get_elapsed_time(self) -> float:
        """获取已经过的时间（秒）"""
        if not self.start_time:
            return 0.0

        return (datetime.now() - self.start_time).total_seconds()

    def get_retry_summary(self) -> dict[str, Any]:
        """获取重试摘要信息

        Returns:
            Dict[str, Any]: 重试摘要
        """
        return {
            "total_attempts": len(self.attempts),
            "success": any(attempt.success for attempt in self.attempts),
            "elapsed_time": self._get_elapsed_time(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "config": {
                "enabled": self.config.enabled,
                "max_retries": self.config.max_retries,
                "timeout_seconds": self.config.timeout_seconds,
            },
        }
