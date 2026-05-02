"""浏览器与验证码相关 Protocol 接口定义。"""

from __future__ import annotations

from typing import Any, Protocol


class IBrowserService(Protocol):
    """浏览器服务接口"""

    async def get_browser(self) -> Any: ...

    async def close_browser(self) -> None: ...

    def create_context(self, use_anti_detection: bool = True, **kwargs: Any) -> Any: ...


class ICaptchaService(Protocol):
    """验证码服务接口"""

    def recognize(self, image_data: bytes) -> str: ...


class IOcrService(Protocol):
    def extract_text(self, image_bytes: bytes) -> Any: ...
