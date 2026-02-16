"""
废弃装饰器模块

提供统一的废弃标记机制,用于标记将在未来版本移除的代码.
发出 DeprecationWarning 并包含迁移指导信息.

Usage:
    from apps.core.deprecation import deprecated

    @deprecated(
        reason="此函数已被新的统一服务替代",
        replacement="ServiceLocator.get_llm_service()",
        version="v6"
    )
    def old_function() -> None:
        pass
"""

import functools
import warnings
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def deprecated(reason: str, replacement: str | None = None, version: str = "v6") -> Callable[[F], F]:
    """
    废弃装饰器

    用于标记将在未来版本移除的函数、方法或类.
    当被装饰的代码被调用时,会发出 DeprecationWarning 警告.

    Args:
        reason: 废弃原因,说明为什么这段代码被废弃
        replacement: 替代方案,建议使用的新代码路径(可选)
        version: 废弃版本,标记从哪个版本开始废弃,默认为 "v6"

    Returns:
        装饰器函数

    Example:
        @deprecated(
            reason="此客户端已被统一 LLM 服务替代",
            replacement="ServiceLocator.get_llm_service()",
            version="v6"
        )
        def chat(prompt: str) -> str:
            ...

    Warning Message Format:
        "{func_name} 已废弃 (since {version}): {reason}"
        如果提供了 replacement,会追加:" 请使用 {replacement} 替代"
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            message = f"{func.__name__} 已废弃 (since {version}): {reason}"
            if replacement:
                message += f" 请使用 {replacement} 替代"
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def deprecated_class(reason: str, replacement: str | None = None, version: str = "v6") -> Callable[[type], type]:
    """
    类废弃装饰器

    用于标记将在未来版本移除的类.
    当类被实例化时,会发出 DeprecationWarning 警告.

    Args:
        reason: 废弃原因
        replacement: 替代方案(可选)
        version: 废弃版本,默认为 "v6"

    Returns:
        装饰器函数

    Example:
        @deprecated_class(
            reason="此配置类已被 LLMConfig 替代",
            replacement="apps.core.llm.config.LLMConfig",
            version="v6"
        )
        class OllamaConfig:
            ...
    """

    def decorator(cls: type) -> type:
        original_init = cls.__init__  # type: ignore[misc]

        @functools.wraps(original_init)
        def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
            message = f"{cls.__name__} 已废弃 (since {version}): {reason}"
            if replacement:
                message += f" 请使用 {replacement} 替代"
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            original_init(self, *args, **kwargs)

        cls.__init__ = new_init  # type: ignore[misc]
        return cls

    return decorator


def emit_deprecation_warning(
    name: str, reason: str, replacement: str | None = None, version: str = "v6", stacklevel: int = 2
) -> None:
    """
    直接发出废弃警告

    用于在模块级别或其他无法使用装饰器的场景发出废弃警告.

    Args:
        name: 被废弃的模块/函数/类名称
        reason: 废弃原因
        replacement: 替代方案(可选)
        version: 废弃版本,默认为 "v6"
        stacklevel: 警告堆栈层级,默认为 2

    Example:
        # 在模块顶部
        from apps.core.deprecation import emit_deprecation_warning

        emit_deprecation_warning(
            name="ollama_client",
            reason="此模块已被统一 LLM 服务替代",
            replacement="ServiceLocator.get_llm_service()",
            stacklevel=3
        )
    """
    message = f"{name} 已废弃 (since {version}): {reason}"
    if replacement:
        message += f" 请使用 {replacement} 替代"
    warnings.warn(message, DeprecationWarning, stacklevel=stacklevel)
