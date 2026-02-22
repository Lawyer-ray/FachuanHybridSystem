"""
缓存服务层

提供 cached 装饰器和 invalidate_cache 工具函数，
支持 Redis 不可用时降级为直接查询数据库。
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from django.core.cache import cache

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def cached(key_template: str, timeout: int | None = None) -> Callable[[F], F]:
    """
    缓存装饰器

    Args:
        key_template: 缓存键模板，支持 {kwarg_name} 占位符
        timeout: 超时时间（秒），None 使用 Django 默认值

    当 Redis 不可用时自动降级为直接调用原函数，并记录 warning 日志。
    """

    def decorator(func: F) -> F:
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 将位置参数绑定到参数名，跳过 self
            bound: dict[str, Any] = {}
            for i, val in enumerate(args):
                if i < len(param_names):
                    bound[param_names[i]] = val
            bound.update(kwargs)
            # 移除 self
            bound.pop("self", None)

            try:
                cache_key = key_template.format(**bound)
            except KeyError:
                cache_key = key_template

            try:
                result = cache.get(cache_key)
                if result is not None:
                    return result
            except (ConnectionError, TimeoutError, OSError):
                logger.warning("缓存读取失败，降级为直接查询: key=%s", cache_key)
                return func(*args, **kwargs)

            result = func(*args, **kwargs)

            try:
                cache.set(cache_key, result, timeout)
            except (ConnectionError, TimeoutError, OSError):
                logger.warning("缓存写入失败: key=%s", cache_key)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def invalidate_cache(key: str) -> None:
    """
    失效指定缓存键

    Args:
        key: 缓存键

    Redis 不可用时记录 warning 日志，不抛出异常。
    """
    try:
        cache.delete(key)
    except (ConnectionError, TimeoutError, OSError):
        logger.warning("缓存失效操作失败: key=%s", key)
