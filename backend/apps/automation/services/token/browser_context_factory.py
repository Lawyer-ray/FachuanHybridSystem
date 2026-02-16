"""Factory pattern implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from apps.core.exceptions import NetworkError


class AntiDetectionOptionsProvider(Protocol):
    def get_options(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DefaultAntiDetectionOptionsProvider:
    def get_options(self) -> dict[str, Any]:
        from apps.automation.services.scraper.core.anti_detection import anti_detection

        return anti_detection.get_browser_context_options()


class BrowserContextFactory(Protocol):
    def new_context(self) -> Any: ...


@dataclass(frozen=True)
class PlaywrightBrowserContextFactory:
    browser_service: Any
    anti_detection_options_provider: AntiDetectionOptionsProvider

    def new_context(self) -> Any:
        try:
            if hasattr(self.browser_service, "create_context"):
                return self.browser_service.create_context(
                    use_anti_detection=True,
                    **self.anti_detection_options_provider.get_options(),
                )
            browser = self.browser_service.get_browser()
            return browser.new_context(**self.anti_detection_options_provider.get_options())
        except Exception as e:
            raise NetworkError(f"无法获取浏览器上下文: {e!s}") from e
