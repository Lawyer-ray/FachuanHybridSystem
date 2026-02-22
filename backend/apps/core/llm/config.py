"""Module for config."""

from __future__ import annotations

"""
LLM 配置管理模块

从统一系统配置读取 LLM 相关配置,支持动态更新.
复用 SystemConfigService 实现配置读取和缓存.

Requirements: 2.1, 2.2, 2.3, 2.5, 5.1, 5.3, 5.4
"""


import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django.conf import settings

logger = logging.getLogger("apps.core.llm")

if TYPE_CHECKING:
    from apps.core.llm.backends.base import BackendConfig
    from apps.core.services.system_config_service import SystemConfigService


class LLMConfig:
    """
    LLM 配置管理器

    从统一系统配置读取 LLM 配置,复用 SystemConfigService 实现.
    优先级:SystemConfigService(带缓存)> Django settings > 默认值

    配置项:
    - API_KEY: API 密钥
    - BASE_URL: API 基础 URL
    - DEFAULT_MODEL: 默认模型
    - AVAILABLE_MODELS: 可用模型列表
    - TIMEOUT: 超时时间(秒)
    - ENABLE_TRACKING: 是否启用调用追踪
    """

    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
    DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
    DEFAULT_TIMEOUT = 60

    # Ollama 默认值 (Requirements: 2.2, 2.3)
    DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"
    DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
    DEFAULT_OLLAMA_TIMEOUT = 120

    DEFAULT_MOONSHOT_MODEL = "moonshot-v1-auto"
    DEFAULT_MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
    DEFAULT_MOONSHOT_TIMEOUT = 120

    DEFAULT_AVAILABLE_MODELS: ClassVar[list[str]] = [
        # Qwen 系列
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen3-30B-A3B-Thinking-2507",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/QwQ-32B-Preview",
        # DeepSeek 系列
        "deepseek-ai/DeepSeek-V2.5",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "deepseek-ai/DeepSeek-R1",
        # GLM 系列
        "zai-org/GLM-4.6V",  # 添加你正在使用的模型
        "zai-org/GLM-4.7",
        "zai-org/GLM-4-32B-0414",
        "zai-org/GLM-Z1-32B-0414",
        "THUDM/glm-4-9b-chat",
        # 其他模型
        "Pro/ByteDance/Seed-OSS-36B-Instruct",
        "Pro/Tencent/Hunyuan-Translation-7B",
        "Pro/inclusionAI/Ring-flash-2.0",
    ]

    # 缓存 SystemConfigService 实例
    _config_service: SystemConfigService | None = None

    @classmethod
    def _get_config_service(cls) -> SystemConfigService | None:
        """
        获取 SystemConfigService 实例(延迟加载)

        Returns:
            SystemConfigService 实例,不可用时返回 None
        """
        if cls._config_service is None:
            try:
                from apps.core.services.system_config_service import SystemConfigService

                cls._config_service = SystemConfigService()
            except Exception:
                logger.warning("[LLMConfig] 无法加载 SystemConfigService", exc_info=True)
                return None
        return cls._config_service

    @classmethod
    def _get_django_settings_fallback(cls, key: str, default: str = "") -> str:
        """
        从 Django settings 获取 fallback 值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        siliconflow_config = getattr(settings, "SILICONFLOW", {} or {})
        django_key = key.replace("SILICONFLOW_", "")
        raw_value = siliconflow_config.get(django_key, default)
        fallback_value = raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
        if fallback_value:
            logger.debug("[LLMConfig] 从 Django settings 获取", extra={"namespace": "SILICONFLOW", "key": django_key})
        return fallback_value

    @classmethod
    def _get_system_config(cls, key: str, default: str = "") -> str:
        """
        从统一系统配置获取配置值

        优先级:SystemConfigService(带缓存)> Django settings > 默认值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值

        Requirements: 5.1, 5.3, 5.4
        """
        # 尝试使用 SystemConfigService(带缓存)
        config_service = cls._get_config_service()
        if config_service is not None:
            try:
                # SystemConfigService.get_value 内部已实现缓存机制
                raw_value = config_service.get_value(key, default="")
                value = raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
                if value:
                    logger.debug("[LLMConfig] 从 SystemConfigService 读取", extra={"key": key})
                    return value
                else:
                    logger.debug("[LLMConfig] SystemConfigService 未找到", extra={"key": key})
            except Exception:
                logger.warning("[LLMConfig] SystemConfigService 读取失败", exc_info=True, extra={"key": key})

        # Fallback 到 Django settings(Requirement 5.4)
        fallback_value = cls._get_django_settings_fallback(key, default)
        if fallback_value:
            logger.debug("[LLMConfig] 回退到 Django settings", extra={"key": key})
            return fallback_value

        return default

    @classmethod
    async def _get_system_config_async(cls, key: str, default: str = "") -> str:
        """
        异步版本:从统一系统配置获取配置值

        复用 SystemConfigService,在异步上下文中使用 sync_to_async 包装

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        config_service = cls._get_config_service()
        if config_service is not None:
            try:
                from asgiref.sync import sync_to_async

                @sync_to_async
                def get_value_sync() -> str:
                    raw_value = config_service.get_value(key, default="")
                    return raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))

                value = await get_value_sync()
                if value:
                    logger.debug("[LLMConfig] 异步从 SystemConfigService 读取", extra={"key": key})
                    return value
                else:
                    logger.debug("[LLMConfig] 异步 SystemConfigService 未找到", extra={"key": key})
            except Exception:
                logger.warning("[LLMConfig] 异步 SystemConfigService 读取失败", exc_info=True, extra={"key": key})

        # Fallback 到 Django settings
        return cls._get_django_settings_fallback(key, default)

    @classmethod
    def get_api_key(cls) -> str:
        """
        获取 API Key

        Returns:
            API Key 字符串,未配置时返回空字符串
        """
        raw = cls._get_system_config("SILICONFLOW_API_KEY", "")
        return cls._normalize_api_key(raw)

    @classmethod
    async def get_api_key_async(cls) -> str:
        raw = await cls._get_system_config_async("SILICONFLOW_API_KEY", "")
        return cls._normalize_api_key(raw)

    @classmethod
    def get_base_url(cls) -> str:
        """
        获取 API Base URL

        Returns:
            Base URL 字符串,默认为 https://api.siliconflow.cn/v1
        """
        raw = cls._get_system_config("SILICONFLOW_BASE_URL", cls.DEFAULT_BASE_URL)
        return cls._normalize_base_url(raw)

    @classmethod
    async def get_base_url_async(cls) -> str:
        raw = await cls._get_system_config_async("SILICONFLOW_BASE_URL", cls.DEFAULT_BASE_URL)
        return cls._normalize_base_url(raw)

    @classmethod
    def get_default_model(cls) -> str:
        """
        获取默认模型

        Returns:
            默认模型名称,默认为 Qwen/Qwen2.5-7B-Instruct
        """
        raw = cls._get_system_config("SILICONFLOW_DEFAULT_MODEL", cls.DEFAULT_MODEL)
        return (raw or "").strip() or cls.DEFAULT_MODEL

    @classmethod
    async def get_default_model_async(cls) -> str:
        raw = await cls._get_system_config_async("SILICONFLOW_DEFAULT_MODEL", cls.DEFAULT_MODEL)
        return (raw or "").strip() or cls.DEFAULT_MODEL

    @classmethod
    def _normalize_api_key(cls, value: str) -> str:
        v = (value or "").strip()
        lower = v.lower()
        if lower.startswith("bearer "):
            v = v[7:].strip()
        return v

    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        v = (value or "").strip()
        while v.endswith("/"):
            v = v[:-1]
        return v or cls.DEFAULT_BASE_URL

    @classmethod
    def get_available_models(cls) -> list[str]:
        """
        获取可用模型列表(仅供参考)

        注意:此列表仅作为参考,实际可以使用任何 SiliconFlow 支持的模型.

        Returns:
            可用模型名称列表
        """
        return cls.DEFAULT_AVAILABLE_MODELS.copy()

    @classmethod
    def get_timeout(cls) -> int:
        """
        获取超时时间(秒)

        Returns:
            超时时间,默认 60 秒
        """
        timeout_str = cls._get_system_config("SILICONFLOW_TIMEOUT", str(cls.DEFAULT_TIMEOUT))
        try:
            return int(timeout_str)
        except (ValueError, TypeError):
            return cls.DEFAULT_TIMEOUT

    @classmethod
    async def get_timeout_async(cls) -> int:
        timeout_str = await cls._get_system_config_async("SILICONFLOW_TIMEOUT", str(cls.DEFAULT_TIMEOUT))
        try:
            return int(timeout_str)
        except (ValueError, TypeError):
            return cls.DEFAULT_TIMEOUT

    @classmethod
    def is_tracking_enabled(cls) -> bool:
        """
        是否启用调用追踪

        Returns:
            True 表示启用,False 表示禁用(默认禁用)
        """
        tracking_str = cls._get_system_config("SILICONFLOW_ENABLE_TRACKING", "false")
        return tracking_str.lower() in ("true", "1", "yes", "on")

    @classmethod
    def get_temperature(cls) -> float:
        """
        获取默认生成温度

        Returns:
            生成温度,默认 0.3
        """
        temp_str = cls._get_system_config("LLM_TEMPERATURE", "0.3")
        try:
            return float(temp_str)
        except (ValueError, TypeError):
            return 0.3

    @classmethod
    def get_max_tokens(cls) -> int:
        """
        获取最大输出 Token 数

        Returns:
            最大 Token 数,默认 2000
        """
        tokens_str = cls._get_system_config("LLM_MAX_TOKENS", "2000")
        try:
            return int(tokens_str)
        except (ValueError, TypeError):
            return 2000

    # ============================================================
    # Ollama 配置方法
    # Requirements: 2.2, 2.3
    # ============================================================

    @classmethod
    def get_ollama_model(cls) -> str:
        """
        获取 Ollama 模型名称

        优先级:SystemConfigService > Django settings.OLLAMA > 默认值

        Returns:
            Ollama 模型名称

        Requirements: 2.2, 2.3
        """
        # 尝试从 SystemConfigService 读取
        model = cls._get_system_config("OLLAMA_MODEL", "")
        if model:
            return model

        # Fallback 到 Django settings
        ollama_config = getattr(settings, "OLLAMA", {} or {})
        raw_value = ollama_config.get("MODEL")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return cls.DEFAULT_OLLAMA_MODEL

    @classmethod
    def get_ollama_base_url(cls) -> str:
        """
        获取 Ollama 服务地址

        优先级:SystemConfigService > Django settings.OLLAMA > 默认值

        Returns:
            Ollama 服务地址

        Requirements: 2.2, 2.3
        """
        # 尝试从 SystemConfigService 读取
        url = cls._get_system_config("OLLAMA_BASE_URL", "")
        if url:
            return url

        # Fallback 到 Django settings
        ollama_config = getattr(settings, "OLLAMA", {} or {})
        raw_value = ollama_config.get("BASE_URL")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return cls.DEFAULT_OLLAMA_BASE_URL

    # ============================================================
    # Moonshot 配置方法
    # ============================================================

    @classmethod
    def get_moonshot_api_key(cls) -> str:
        raw = cls._get_system_config("MOONSHOT_API_KEY", "")
        if raw:
            return cls._normalize_api_key(raw)

        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        raw_value = moonshot_config.get("API_KEY", "")
        return cls._normalize_api_key(
            raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
        )

    @classmethod
    def get_moonshot_base_url(cls) -> str:
        raw = cls._get_system_config("MOONSHOT_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)

        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        raw_value = moonshot_config.get("BASE_URL", cls.DEFAULT_MOONSHOT_BASE_URL)
        return cls._normalize_base_url(
            raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
        )

    @classmethod
    def get_moonshot_default_model(cls) -> str:
        raw = cls._get_system_config("MOONSHOT_DEFAULT_MODEL", "")
        if raw:
            return (raw or "").strip() or cls.DEFAULT_MOONSHOT_MODEL

        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        model = moonshot_config.get("DEFAULT_MODEL", cls.DEFAULT_MOONSHOT_MODEL)
        return (model or "").strip() or cls.DEFAULT_MOONSHOT_MODEL

    @classmethod
    def get_moonshot_timeout(cls) -> int:
        timeout_str = cls._get_system_config("MOONSHOT_TIMEOUT", "")
        if timeout_str:
            try:
                return int(timeout_str)
            except (ValueError, TypeError):
                return cls.DEFAULT_MOONSHOT_TIMEOUT

        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        value = moonshot_config.get("TIMEOUT", cls.DEFAULT_MOONSHOT_TIMEOUT)
        try:
            return int(value)
        except (ValueError, TypeError):
            return cls.DEFAULT_MOONSHOT_TIMEOUT

    @classmethod
    def get_ollama_timeout(cls) -> int:
        timeout_str = cls._get_system_config("OLLAMA_TIMEOUT", "")
        if timeout_str:
            try:
                return int(timeout_str)
            except (ValueError, TypeError):
                return cls.DEFAULT_OLLAMA_TIMEOUT

        ollama_config = getattr(settings, "OLLAMA", {} or {})
        value = ollama_config.get("TIMEOUT", cls.DEFAULT_OLLAMA_TIMEOUT)
        try:
            return int(value)
        except (ValueError, TypeError):
            return cls.DEFAULT_OLLAMA_TIMEOUT

    @classmethod
    def get_default_backend(cls) -> str:
        raw = cls._get_system_config("LLM_DEFAULT_BACKEND", "")
        if raw and isinstance(raw, str):
            v = raw.strip().lower()
            if v:
                return v

        llm_settings = getattr(settings, "LLM", {} or {})
        v2 = llm_settings.get("DEFAULT_BACKEND")
        if isinstance(v2, str) and v2.strip():
            return v2.strip().lower()
        return "siliconflow"

    @classmethod
    def get_backend_configs(cls) -> dict[str, BackendConfig]:
        from apps.core.llm.backends.base import BackendConfig

        def enabled_key(name: str) -> str:
            return f"LLM_BACKEND_{name.upper()}_ENABLED"

        def priority_key(name: str) -> str:
            return f"LLM_BACKEND_{name.upper()}_PRIORITY"

        default_priorities = {"siliconflow": 1, "ollama": 2, "moonshot": 3}
        default_enabled = {"siliconflow": True, "ollama": True, "moonshot": True}

        configs: dict[str, BackendConfig] = {}
        for name in ("siliconflow", "ollama", "moonshot"):
            enabled_raw = cls._get_system_config(enabled_key(name), "")
            enabled = cls._parse_bool(enabled_raw, default_enabled[name])

            priority_raw = cls._get_system_config(priority_key(name), "")
            priority = cls._parse_int(priority_raw, default_priorities[name])

            if name == "siliconflow":
                configs[name] = BackendConfig(
                    name=name,
                    enabled=enabled,
                    priority=priority,
                    default_model=cls.get_default_model(),
                    base_url=cls.get_base_url(),
                    api_key=cls.get_api_key(),
                    timeout=cls.get_timeout(),
                )
            elif name == "ollama":
                configs[name] = BackendConfig(
                    name=name,
                    enabled=enabled,
                    priority=priority,
                    default_model=cls.get_ollama_model(),
                    base_url=cls.get_ollama_base_url(),
                    timeout=cls.get_ollama_timeout(),
                )
            else:
                configs[name] = BackendConfig(
                    name=name,
                    enabled=enabled,
                    priority=priority,
                    default_model=cls.get_moonshot_default_model(),
                    base_url=cls.get_moonshot_base_url(),
                    api_key=cls.get_moonshot_api_key(),
                    timeout=cls.get_moonshot_timeout(),
                )
        return configs

    @classmethod
    def _parse_bool(cls, value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if not value:
            return default
        s = str(value).strip().lower()
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @classmethod
    def _parse_int(cls, value: Any, default: int) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
