"""Business logic services."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

from apps.core.exceptions import ChatCreationException, MessageSendException
from apps.core.models.enums import ChatPlatform

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30


class ChatProviderFacade:
    def __init__(self, *, factory: Any | None = None, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        if factory is None:
            from apps.cases.dependencies import get_chat_provider_factory

            factory = get_chat_provider_factory()
        self.factory = factory
        self.timeout = timeout

    def _call_with_timeout(self, fn: Any, *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
        """在独立线程中执行 provider 调用，强制超时保护。

        Args:
            fn: 要执行的 callable
            *args, **kwargs: 传递给 fn 的参数
            timeout: 超时秒数，默认使用 self.timeout

        Returns:
            fn 的返回值

        Raises:
            TimeoutError: 超过指定时间未返回
        """
        effective_timeout = timeout if timeout is not None else self.timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=effective_timeout)
            except concurrent.futures.TimeoutError:
                future.cancel()
                raise TimeoutError(
                    f"外部服务调用超时（{effective_timeout}秒）: {getattr(fn, '__name__', str(fn))}"
                ) from None

    async def _call_with_timeout_async(self, fn: Any, *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
        """异步版本：使用 asyncio.wait_for() 替代 ThreadPoolExecutor。

        从 async 上下文调用时使用此方法，避免嵌套线程池。
        """
        from asgiref.sync import sync_to_async

        effective_timeout = timeout if timeout is not None else self.timeout
        async_fn = sync_to_async(fn)
        try:
            return await asyncio.wait_for(async_fn(*args, **kwargs), timeout=effective_timeout)
        except TimeoutError:
            raise TimeoutError(
                f"外部服务调用超时（{effective_timeout}秒）: {getattr(fn, '__name__', str(fn))}"
            ) from None

    def get_provider_for_creation(self, *, platform: ChatPlatform) -> Any:
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            raise ChatCreationException(
                message="无法获取群聊提供者: %(platform)s" % {"platform": platform.label},
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                errors={"original_error": str(e)},
            ) from e

        if not provider.is_available():
            raise ChatCreationException(
                message="群聊平台不可用: %(platform)s" % {"platform": platform.label},
                code="PROVIDER_NOT_AVAILABLE",
                platform=platform.value,
                errors={"platform_status": "配置不完整或服务不可用"},
            )
        return provider

    def get_provider_for_messaging(self, *, platform: ChatPlatform, chat_id: str) -> Any:
        try:
            provider = self.factory.get_provider(platform)
        except Exception as e:
            raise MessageSendException(
                message="无法获取群聊提供者: %(platform)s" % {"platform": platform.label},
                code="PROVIDER_UNAVAILABLE",
                platform=platform.value,
                chat_id=chat_id,
                errors={"original_error": str(e)},
            ) from e
        return provider

    def try_get_chat_name(self, *, platform: ChatPlatform, chat_id: str) -> Any:
        try:
            provider = self.factory.get_provider(platform)
            if not provider.is_available():
                return None
            result = self._call_with_timeout(provider.get_chat_info, chat_id)
            if result.success and result.chat_name:
                return result.chat_name
            return None
        except TimeoutError:
            logger.warning(
                "try_get_chat_name_timeout",
                extra={"platform": platform.value, "chat_id": chat_id, "timeout": self.timeout},
            )
            return None
        except Exception:
            logger.debug(
                "try_get_chat_name_failed", exc_info=True, extra={"platform": platform.value, "chat_id": chat_id}
            )
            return None

    def create_chat(self, *, provider: Any, chat_name: str, owner_id: str | None) -> Any:
        try:
            return self._call_with_timeout(provider.create_chat, chat_name, owner_id)
        except TimeoutError as e:
            raise ChatCreationException(
                message="创建群聊超时，请稍后重试",
                code="CHAT_CREATE_TIMEOUT",
                platform=getattr(provider, "platform", "unknown"),
                errors={"timeout": self.timeout},
            ) from e

    def send_message(self, *, provider: Any, chat_id: str, content: Any) -> Any:  # pragma: no cover
        try:
            return self._call_with_timeout(provider.send_message, chat_id, content)
        except TimeoutError as e:
            raise MessageSendException(
                message="发送消息超时，请稍后重试",
                code="MESSAGE_SEND_TIMEOUT",
                platform=getattr(provider, "platform", "unknown"),
                chat_id=chat_id,
                errors={"timeout": self.timeout},
            ) from e

    def send_file(self, *, provider: Any, chat_id: str, file_path: str) -> Any:  # pragma: no cover
        try:
            return self._call_with_timeout(provider.send_file, chat_id, file_path, timeout=60)
        except TimeoutError as e:
            raise MessageSendException(
                message="发送文件超时，请稍后重试",
                code="FILE_SEND_TIMEOUT",
                platform=getattr(provider, "platform", "unknown"),
                chat_id=chat_id,
                errors={"timeout": 60},
            ) from e
