"""企业数据 provider 注册与配置读取。"""

from __future__ import annotations

import logging
import os
import re

from apps.core.exceptions import ValidationException
from apps.core.services.system_config_service import SystemConfigService
from apps.enterprise_data.services.providers import QichachaMcpProvider, TianyanchaMcpProvider
from apps.enterprise_data.services.types import (
    DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
    DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
    DEFAULT_ALERT_MIN_SAMPLES,
    DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_METRICS_WINDOW_SECONDS,
    DEFAULT_PROVIDER_NAME,
    DEFAULT_RATE_LIMIT_REQUESTS,
    DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TRANSPORT,
    ProviderConfig,
    ProviderDescriptor,
)

_TRUE_VALUES = ("true", "1", "yes", "y", "on")
_MULTI_VALUE_SPLIT_PATTERN = re.compile(r"[\r\n,;]+")
logger = logging.getLogger(__name__)


class EnterpriseProviderRegistry:
    """从 SystemConfig 读取 provider 配置并创建实例。"""

    def __init__(self, *, config_service: SystemConfigService | None = None) -> None:
        self._config = config_service or SystemConfigService()

    def get_cache_ttl_seconds(self) -> int:
        return self._read_int("ENTERPRISE_DATA_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS, min_value=30)

    def get_default_provider_name(self) -> str:
        value = str(self._config.get_value("ENTERPRISE_DATA_DEFAULT_PROVIDER", DEFAULT_PROVIDER_NAME) or "").strip().lower()
        return value or DEFAULT_PROVIDER_NAME

    def list_providers(self) -> list[ProviderDescriptor]:
        default_name = self.get_default_provider_name()
        return [
            ProviderDescriptor(
                name=TianyanchaMcpProvider.name,
                enabled=self._read_bool("TIANYANCHA_MCP_ENABLED", True),
                is_default=default_name == TianyanchaMcpProvider.name,
                transport=self._normalize_transport(
                    str(self._config.get_value("TIANYANCHA_MCP_TRANSPORT", DEFAULT_TRANSPORT) or "").strip()
                ),
                capabilities=TianyanchaMcpProvider.supported_capabilities(),
                note="",
            ),
            ProviderDescriptor(
                name=QichachaMcpProvider.name,
                enabled=self._read_bool("QICHACHA_MCP_ENABLED", False),
                is_default=default_name == QichachaMcpProvider.name,
                transport=self._normalize_transport(
                    str(self._config.get_value("QICHACHA_MCP_TRANSPORT", DEFAULT_TRANSPORT) or "").strip()
                ),
                capabilities=QichachaMcpProvider.supported_capabilities(),
                note="当前为骨架实现，尚未完成 MCP 工具映射",
            ),
        ]

    def get_provider(self, provider: str | None = None) -> TianyanchaMcpProvider | QichachaMcpProvider:
        provider_name = (provider or self.get_default_provider_name()).strip().lower()
        if provider_name == TianyanchaMcpProvider.name:
            enabled = self._read_bool("TIANYANCHA_MCP_ENABLED", True)
            if not enabled:
                raise ValidationException(
                    message="天眼查企业数据查询未启用",
                    code="PROVIDER_DISABLED",
                    errors={"provider": provider_name},
                )
            config = self._build_provider_config(
                provider_name=provider_name,
                transport_key="TIANYANCHA_MCP_TRANSPORT",
                base_url_key="TIANYANCHA_MCP_BASE_URL",
                base_url_default="https://mcp-service.tianyancha.com/mcp",
                sse_url_key="TIANYANCHA_MCP_SSE_URL",
                sse_url_default="https://mcp-service.tianyancha.com/sse",
                api_key_key="TIANYANCHA_MCP_API_KEY",
                timeout_key="TIANYANCHA_MCP_TIMEOUT_SECONDS",
                enabled=enabled,
            )
            return TianyanchaMcpProvider(config=config)

        if provider_name == QichachaMcpProvider.name:
            enabled = self._read_bool("QICHACHA_MCP_ENABLED", False)
            if not enabled:
                raise ValidationException(
                    message="企查查企业数据查询未启用",
                    code="PROVIDER_DISABLED",
                    errors={"provider": provider_name},
                )
            config = self._build_provider_config(
                provider_name=provider_name,
                transport_key="QICHACHA_MCP_TRANSPORT",
                base_url_key="QICHACHA_MCP_BASE_URL",
                base_url_default="https://mcp-service.qichacha.com/mcp",
                sse_url_key="QICHACHA_MCP_SSE_URL",
                sse_url_default="https://mcp-service.qichacha.com/sse",
                api_key_key="QICHACHA_MCP_API_KEY",
                timeout_key="QICHACHA_MCP_TIMEOUT_SECONDS",
                enabled=enabled,
            )
            return QichachaMcpProvider(config=config)

        raise ValidationException(
            message=f"不支持的企业数据提供商: {provider_name}",
            code="UNSUPPORTED_PROVIDER",
            errors={"provider": provider_name},
        )

    def get_rate_limit_requests(self) -> int:
        return self._read_int("ENTERPRISE_DATA_RATE_LIMIT_REQUESTS", DEFAULT_RATE_LIMIT_REQUESTS, min_value=1)

    def get_rate_limit_window_seconds(self) -> int:
        return self._read_int(
            "ENTERPRISE_DATA_RATE_LIMIT_WINDOW_SECONDS",
            DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
            min_value=1,
        )

    def get_retry_max_attempts(self) -> int:
        value = self._read_int("ENTERPRISE_DATA_RETRY_MAX_ATTEMPTS", DEFAULT_RETRY_MAX_ATTEMPTS, min_value=1)
        return min(5, value)

    def get_retry_backoff_seconds(self) -> float:
        return self._read_float(
            "ENTERPRISE_DATA_RETRY_BACKOFF_SECONDS",
            DEFAULT_RETRY_BACKOFF_SECONDS,
            min_value=0.0,
            max_value=5.0,
        )

    def get_metrics_window_seconds(self) -> int:
        return self._read_int("ENTERPRISE_DATA_METRICS_WINDOW_SECONDS", DEFAULT_METRICS_WINDOW_SECONDS, min_value=60)

    def get_alert_min_samples(self) -> int:
        return self._read_int("ENTERPRISE_DATA_ALERT_MIN_SAMPLES", DEFAULT_ALERT_MIN_SAMPLES, min_value=1)

    def get_alert_success_rate_threshold(self) -> float:
        return self._read_float(
            "ENTERPRISE_DATA_ALERT_SUCCESS_RATE_THRESHOLD",
            DEFAULT_ALERT_SUCCESS_RATE_THRESHOLD,
            min_value=0.01,
            max_value=1.0,
        )

    def get_alert_fallback_rate_threshold(self) -> float:
        return self._read_float(
            "ENTERPRISE_DATA_ALERT_FALLBACK_RATE_THRESHOLD",
            DEFAULT_ALERT_FALLBACK_RATE_THRESHOLD,
            min_value=0.0,
            max_value=1.0,
        )

    def get_alert_avg_latency_ms_threshold(self) -> int:
        return self._read_int(
            "ENTERPRISE_DATA_ALERT_AVG_LATENCY_MS_THRESHOLD",
            DEFAULT_ALERT_AVG_LATENCY_MS_THRESHOLD,
            min_value=100,
        )

    def _build_provider_config(
        self,
        *,
        provider_name: str,
        transport_key: str,
        base_url_key: str,
        base_url_default: str,
        sse_url_key: str,
        sse_url_default: str,
        api_key_key: str,
        timeout_key: str,
        enabled: bool,
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

        return ProviderConfig(
            name=provider_name,
            enabled=enabled,
            transport=self._normalize_transport(str(self._config.get_value(transport_key, DEFAULT_TRANSPORT) or "").strip()),
            base_url=str(self._config.get_value(base_url_key, base_url_default) or "").strip(),
            sse_url=str(self._config.get_value(sse_url_key, sse_url_default) or "").strip(),
            api_key=api_keys[0],
            timeout_seconds=self._read_int(timeout_key, DEFAULT_TIMEOUT_SECONDS, min_value=5),
            api_keys=api_keys,
            rate_limit_requests=self.get_rate_limit_requests(),
            rate_limit_window_seconds=self.get_rate_limit_window_seconds(),
            retry_max_attempts=self.get_retry_max_attempts(),
            retry_backoff_seconds=self.get_retry_backoff_seconds(),
        )

    def _read_bool(self, key: str, default: bool) -> bool:
        raw = str(self._config.get_value(key, "True" if default else "False") or "").strip().lower()
        if not raw:
            return default
        return raw in _TRUE_VALUES

    def _read_int(self, key: str, default: int, min_value: int) -> int:
        raw = str(self._config.get_value(key, str(default)) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(min_value, value)

    def _read_float(self, key: str, default: float, min_value: float, max_value: float) -> float:
        raw = str(self._config.get_value(key, str(default)) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            return default
        if value < min_value:
            return min_value
        if value > max_value:
            return max_value
        return value

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

    @staticmethod
    def _normalize_transport(raw: str) -> str:
        value = (raw or DEFAULT_TRANSPORT).strip().lower().replace("-", "_")
        if value not in {"streamable_http", "sse"}:
            return DEFAULT_TRANSPORT
        return value
