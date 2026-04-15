"""企业数据 provider 注册与配置读取。"""

from __future__ import annotations

import logging
import os
import re
from typing import cast

from apps.core.exceptions import ValidationException
from apps.core.services.system_config_service import SystemConfigService
from apps.enterprise_data.services.providers import TianyanchaMcpProvider
from apps.enterprise_data.services.types import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_PROVIDER_NAME,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TRANSPORT,
    ProviderConfig,
    ProviderDescriptor,
)

_MULTI_VALUE_SPLIT_PATTERN = re.compile(r"[\r\n,;]+")
logger = logging.getLogger(__name__)


class EnterpriseProviderRegistry:
    """从 SystemConfig 读取 provider 配置并创建实例。"""

    def __init__(self, *, config_service: SystemConfigService | None = None) -> None:
        self._config = config_service or SystemConfigService()

    def get_cache_ttl_seconds(self) -> int:
        return cast(int, DEFAULT_CACHE_TTL_SECONDS)

    def get_default_provider_name(self) -> str:
        return cast(str, DEFAULT_PROVIDER_NAME)

    def list_providers(self) -> list[ProviderDescriptor]:
        transport = self.get_tianyancha_transport()
        return [
            ProviderDescriptor(
                name=TianyanchaMcpProvider.name,
                enabled=True,
                is_default=True,
                transport=transport,
                capabilities=TianyanchaMcpProvider.supported_capabilities(),
                note="",
            )
        ]

    def get_provider(self, provider: str | None = None) -> TianyanchaMcpProvider:
        provider_name = (provider or self.get_default_provider_name()).strip().lower()
        if provider_name != TianyanchaMcpProvider.name:
            raise ValidationException(
                message=f"不支持的企业数据提供商: {provider_name}",
                code="UNSUPPORTED_PROVIDER",
                errors={"provider": provider_name},
            )

        config = self._build_provider_config(
            provider_name=provider_name,
            base_url_key="TIANYANCHA_MCP_BASE_URL",
            base_url_default="https://mcp-service.tianyancha.com/mcp",
            sse_url_key="TIANYANCHA_MCP_SSE_URL",
            sse_url_default="https://mcp-service.tianyancha.com/sse",
            api_key_key="TIANYANCHA_MCP_API_KEY",  # pragma: allowlist secret
        )
        return TianyanchaMcpProvider(config=config)

    def get_tianyancha_transport(self) -> str:
        raw_transport = str(self._config.get_value("TIANYANCHA_MCP_TRANSPORT", DEFAULT_TRANSPORT) or "").strip().lower()
        if raw_transport in {"streamable_http", "sse"}:
            return raw_transport
        if raw_transport:
            logger.warning(
                "Invalid TIANYANCHA_MCP_TRANSPORT configured, fallback to default",
                extra={"configured_transport": raw_transport, "fallback_transport": DEFAULT_TRANSPORT},
            )
        return DEFAULT_TRANSPORT

    def get_rate_limit_requests(self) -> int:
        return 60

    def get_rate_limit_window_seconds(self) -> int:
        return 60

    def get_retry_max_attempts(self) -> int:
        return 2

    def get_retry_backoff_seconds(self) -> float:
        return 0.25

    def get_metrics_window_seconds(self) -> int:
        return 300

    def get_alert_min_samples(self) -> int:
        return 20

    def get_alert_success_rate_threshold(self) -> float:
        return 0.9

    def get_alert_fallback_rate_threshold(self) -> float:
        return 0.35

    def get_alert_avg_latency_ms_threshold(self) -> int:
        return 3000

    def _build_provider_config(
        self,
        *,
        provider_name: str,
        base_url_key: str,
        base_url_default: str,
        sse_url_key: str,
        sse_url_default: str,
        api_key_key: str,
    ) -> ProviderConfig:
        api_keys = self._read_sensitive_values(
            api_key_key,
            env_keys=(api_key_key, f"{api_key_key}S"),
        )
        if not api_keys:
            raise ValidationException(
                message=f"{provider_name} MCP API Key 未配置",
                code="PROVIDER_API_KEY_MISSING",
                errors={
                    "provider": provider_name,
                    "config_key": api_key_key,
                    "env_keys": [api_key_key, f"{api_key_key}S"],
                },
            )

        transport = self.get_tianyancha_transport()

        return ProviderConfig(
            name=provider_name,
            enabled=True,
            transport=transport,
            base_url=str(self._config.get_value(base_url_key, base_url_default) or "").strip(),
            sse_url=str(self._config.get_value(sse_url_key, sse_url_default) or "").strip(),
            api_key=api_keys[0],
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            api_keys=api_keys,
            rate_limit_requests=self.get_rate_limit_requests(),
            rate_limit_window_seconds=self.get_rate_limit_window_seconds(),
            retry_max_attempts=self.get_retry_max_attempts(),
            retry_backoff_seconds=self.get_retry_backoff_seconds(),
        )

    def _read_sensitive_str(self, key: str) -> str:
        try:
            return str(self._config.get_value(key, "") or "").strip()
        except Exception as exc:
            logger.warning(
                "Read system config failed, fallback env var",
                extra={"key": key, "error_type": type(exc).__name__},
            )
            return ""

    def _read_sensitive_values(self, key: str, *, env_keys: tuple[str, ...]) -> tuple[str, ...]:
        stored_values = self._split_secret_values(self._read_sensitive_str(key))
        if stored_values:
            return stored_values

        for env_key in env_keys:
            env_value = (os.environ.get(env_key, "") or "").strip()
            parsed_values = self._split_secret_values(env_value)
            if parsed_values:
                return parsed_values
        return ()

    @staticmethod
    def _split_secret_values(raw_value: str) -> tuple[str, ...]:
        if not raw_value:
            return ()
        values: list[str] = []
        seen: set[str] = set()
        for item in _MULTI_VALUE_SPLIT_PATTERN.split(raw_value):
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            values.append(normalized)
            seen.add(normalized)
        return tuple(values)
