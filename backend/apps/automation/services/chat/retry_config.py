"""
群主设置重试配置和策略

本模块实现了群主设置过程中的重试机制，包括：
- 重试配置管理
- 指数退避算法
- 不同错误类型的重试策略
- 重试状态跟踪

Requirements: 3.3, 3.4
"""

import time
import logging
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings

logger = logging.getLogger(__name__)


class RetryErrorType(Enum):
    """重试错误类型枚举"""
    NETWORK_ERROR = "network_error"          # 网络错误
    TIMEOUT_ERROR = "timeout_error"          # 超时错误
    PERMISSION_ERROR = "permission_error"    # 权限错误
    NOT_FOUND_ERROR = "not_found_error"      # 用户不存在错误
    VALIDATION_ERROR = "validation_error"    # 验证错误
    UNKNOWN_ERROR = "unknown_error"          # 未知错误


class RetryStrategy(Enum):
    """重试策略枚举"""
    NO_RETRY = "no_retry"                    # 不重试
    FIXED_DELAY = "fixed_delay"              # 固定延迟
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    LINEAR_BACKOFF = "linear_backoff"        # 线性退避


@dataclass
class RetryAttempt:
    """重试尝试记录"""
    attempt_number: int                      # 尝试次数（从1开始）
    timestamp: datetime                      # 尝试时间
    error_type: RetryErrorType              # 错误类型
    error_message: str                       # 错误消息
    delay_seconds: float                     # 延迟时间
    success: bool = False                    # 是否成功
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "attempt_number": self.attempt_number,
            "timestamp": self.timestamp.isoformat(),
            "error_type": self.error_type.value,
            "error_message": self.error_message,
            "delay_seconds": self.delay_seconds,
            "success": self.success
        }


class RetryConfig:
    """重试配置类
    
    管理不同错误类型的重试策略和参数。
    支持从Django settings加载配置。
    
    Requirements: 3.3, 3.4
    """
    
    def __init__(self):
        """初始化重试配置"""
        self._load_config()
    
    def _load_config(self) -> None:
        """从Django settings加载重试配置"""
        # 获取飞书配置
        feishu_config = getattr(settings, 'FEISHU', {})
        
        # 默认配置
        self.enabled = feishu_config.get('OWNER_RETRY_ENABLED', True)
        self.max_retries = feishu_config.get('OWNER_MAX_RETRIES', 3)
        self.base_delay = feishu_config.get('OWNER_RETRY_BASE_DELAY', 1.0)
        self.max_delay = feishu_config.get('OWNER_RETRY_MAX_DELAY', 60.0)
        self.backoff_factor = feishu_config.get('OWNER_RETRY_BACKOFF_FACTOR', 2.0)
        self.timeout_seconds = feishu_config.get('OWNER_RETRY_TIMEOUT', 300.0)  # 5分钟总超时
        
        # 错误类型特定配置
        self.error_strategies = {
            RetryErrorType.NETWORK_ERROR: {
                'strategy': RetryStrategy.EXPONENTIAL_BACKOFF,
                'max_retries': self.max_retries,
                'base_delay': self.base_delay,
                'backoff_factor': self.backoff_factor,
                'max_delay': self.max_delay
            },
            RetryErrorType.TIMEOUT_ERROR: {
                'strategy': RetryStrategy.EXPONENTIAL_BACKOFF,
                'max_retries': max(1, self.max_retries - 1),  # 超时错误少重试一次
                'base_delay': self.base_delay * 2,  # 超时错误延迟更长
                'backoff_factor': self.backoff_factor,
                'max_delay': self.max_delay
            },
            RetryErrorType.PERMISSION_ERROR: {
                'strategy': RetryStrategy.NO_RETRY,  # 权限错误不重试
                'max_retries': 0,
                'base_delay': 0,
                'backoff_factor': 1.0,
                'max_delay': 0
            },
            RetryErrorType.NOT_FOUND_ERROR: {
                'strategy': RetryStrategy.FIXED_DELAY,  # 用户不存在可能是临时问题
                'max_retries': 1,  # 只重试一次
                'base_delay': 5.0,  # 固定延迟5秒
                'backoff_factor': 1.0,
                'max_delay': 5.0
            },
            RetryErrorType.VALIDATION_ERROR: {
                'strategy': RetryStrategy.NO_RETRY,  # 验证错误不重试
                'max_retries': 0,
                'base_delay': 0,
                'backoff_factor': 1.0,
                'max_delay': 0
            },
            RetryErrorType.UNKNOWN_ERROR: {
                'strategy': RetryStrategy.LINEAR_BACKOFF,
                'max_retries': max(1, self.max_retries - 1),
                'base_delay': self.base_delay,
                'backoff_factor': 1.5,  # 线性增长因子
                'max_delay': self.max_delay / 2  # 未知错误最大延迟减半
            }
        }
        
        logger.debug(f"已加载重试配置: enabled={self.enabled}, max_retries={self.max_retries}")
    
    def is_enabled(self) -> bool:
        """检查重试机制是否启用"""
        return self.enabled
    
    def get_max_retries(self, error_type: Optional[RetryErrorType] = None) -> int:
        """获取最大重试次数
        
        Args:
            error_type: 错误类型，如果指定则返回该类型的最大重试次数
            
        Returns:
            int: 最大重试次数
        """
        if error_type and error_type in self.error_strategies:
            return self.error_strategies[error_type]['max_retries']
        return self.max_retries
    
    def get_strategy(self, error_type: RetryErrorType) -> RetryStrategy:
        """获取指定错误类型的重试策略
        
        Args:
            error_type: 错误类型
            
        Returns:
            RetryStrategy: 重试策略
        """
        if error_type in self.error_strategies:
            strategy_name = self.error_strategies[error_type]['strategy']
            return strategy_name
        return RetryStrategy.EXPONENTIAL_BACKOFF
    
    def should_retry(self, error_type: RetryErrorType, attempt_count: int) -> bool:
        """判断是否应该重试
        
        Args:
            error_type: 错误类型
            attempt_count: 当前尝试次数
            
        Returns:
            bool: 是否应该重试
        """
        if not self.enabled:
            return False
        
        max_retries = self.get_max_retries(error_type)
        strategy = self.get_strategy(error_type)
        
        # 不重试策略
        if strategy == RetryStrategy.NO_RETRY:
            return False
        
        # 检查是否超过最大重试次数
        return attempt_count < max_retries
    
    def calculate_delay(self, error_type: RetryErrorType, attempt_number: int) -> float:
        """计算重试延迟时间
        
        Args:
            error_type: 错误类型
            attempt_number: 尝试次数（从0开始）
            
        Returns:
            float: 延迟时间（秒）
        """
        if error_type not in self.error_strategies:
            error_type = RetryErrorType.UNKNOWN_ERROR
        
        config = self.error_strategies[error_type]
        strategy = config['strategy']
        base_delay = config['base_delay']
        backoff_factor = config['backoff_factor']
        max_delay = config['max_delay']
        
        if strategy == RetryStrategy.NO_RETRY:
            return 0.0
        elif strategy == RetryStrategy.FIXED_DELAY:
            return min(base_delay, max_delay)
        elif strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = base_delay + (attempt_number * backoff_factor)
            return min(delay, max_delay)
        elif strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = base_delay * (backoff_factor ** attempt_number)
            return min(delay, max_delay)
        else:
            # 默认使用指数退避
            delay = base_delay * (backoff_factor ** attempt_number)
            return min(delay, max_delay)
    
    def get_timeout_seconds(self) -> float:
        """获取总超时时间"""
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
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """初始化重试管理器
        
        Args:
            config: 重试配置，如果不提供则使用默认配置
        """
        self.config = config or RetryConfig()
        self.attempts: List[RetryAttempt] = []
        self.start_time: Optional[datetime] = None
    
    def classify_error(self, exception: Exception) -> RetryErrorType:
        """分类错误类型
        
        根据异常类型和错误消息分类错误类型，用于确定重试策略。
        
        Args:
            exception: 异常对象
            
        Returns:
            RetryErrorType: 错误类型
        """
        # 导入异常类（避免循环导入）
        from apps.core.exceptions import (
            OwnerPermissionException,
            OwnerNotFoundException,
            OwnerValidationException,
            OwnerTimeoutException,
            OwnerNetworkException
        )
        from apps.core.exceptions import (
            PermissionDenied,
            NotFoundError,
            ValidationException,
            NetworkError
        )
        import requests
        
        # 根据异常类型分类
        if isinstance(exception, (OwnerPermissionException, PermissionDenied)):
            return RetryErrorType.PERMISSION_ERROR
        elif isinstance(exception, (OwnerNotFoundException, NotFoundError)):
            return RetryErrorType.NOT_FOUND_ERROR
        elif isinstance(exception, (OwnerValidationException, ValidationException)):
            return RetryErrorType.VALIDATION_ERROR
        elif isinstance(exception, (OwnerTimeoutException,)):
            return RetryErrorType.TIMEOUT_ERROR
        elif isinstance(exception, (OwnerNetworkException, NetworkError, requests.RequestException)):
            return RetryErrorType.NETWORK_ERROR
        else:
            # 根据错误消息进一步分类
            error_message = str(exception).lower()
            if 'timeout' in error_message or 'timed out' in error_message:
                return RetryErrorType.TIMEOUT_ERROR
            elif 'network' in error_message or 'connection' in error_message:
                return RetryErrorType.NETWORK_ERROR
            elif 'permission' in error_message or 'forbidden' in error_message:
                return RetryErrorType.PERMISSION_ERROR
            elif 'not found' in error_message or 'does not exist' in error_message:
                return RetryErrorType.NOT_FOUND_ERROR
            else:
                return RetryErrorType.UNKNOWN_ERROR
    
    def execute_with_retry(
        self,
        operation: Callable[[], Any],
        operation_name: str = "operation",
        context: Optional[Dict[str, Any]] = None
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
                    from apps.core.exceptions import OwnerTimeoutException
                    raise OwnerTimeoutException(
                        message=f"操作总超时: {operation_name}",
                        timeout_seconds=self.config.get_timeout_seconds(),
                        errors={
                            "operation_name": operation_name,
                            "elapsed_time": self._get_elapsed_time(),
                            "attempts": len(self.attempts),
                            "context": context
                        }
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
                
                logger.warning(f"操作失败: {operation_name}, 尝试 {attempt_number + 1}, 错误类型: {error_type.value}, 错误: {str(e)}")
                
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
                    success=False
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
            from apps.core.exceptions import OwnerRetryException
            raise OwnerRetryException(
                message=f"操作重试失败: {operation_name}",
                retry_count=len(self.attempts),
                max_retries=self.config.max_retries,
                errors={
                    "operation_name": operation_name,
                    "attempts": [attempt.to_dict() for attempt in self.attempts],
                    "context": context
                }
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
    
    def get_retry_summary(self) -> Dict[str, Any]:
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
                "timeout_seconds": self.config.timeout_seconds
            }
        }