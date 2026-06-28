"""Module for config."""

from __future__ import annotations

"""
LLM 配置管理模块

从统一系统配置读取 LLM 相关配置,支持动态更新.
复用 SystemConfigService 实现配置读取和缓存.

Requirements: 2.1, 2.2, 2.3, 2.5, 5.1, 5.3, 5.4
"""

import logging
from typing import TYPE_CHECKING, Any, ClassVar, cast

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

    # Ollama 默认值 (Requirements: 2.2, 2.3)
    DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"
    DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
    DEFAULT_OLLAMA_TIMEOUT = 300

    # OpenAI-compatible 默认值
    DEFAULT_OPENAI_COMPATIBLE_MODEL = "kimi26"
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "http://116.196.92.175:8001/v1"
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT = 120

    # 跨调用缓存（async 预热后 sync 调用可复用，避免 SynchronousOnlyOperation）
    _config_cache: ClassVar[dict[str, str]] = {}

    DEFAULT_AVAILABLE_MODELS: ClassVar[list[str]] = [
        # Kimi26 (vLLM self-hosted)
        "kimi26",
    ]

    # 模型名 → 后端映射规则：含 ":" 的走 ollama，其余走 openai_compatible
    _MODEL_BACKEND_RULES: ClassVar[list[tuple[str, str]]] = [
        (":", "ollama"),
    ]

    # 缓存 SystemConfigService 实例
    _config_service: SystemConfigService | None = None
    _VALID_BACKENDS: ClassVar[set[str]] = {"ollama", "openai_compatible"}

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
            except (ImportError, AttributeError):
                logger.warning("[LLMConfig] 无法加载 SystemConfigService")
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
        # 尝试读取 LLM 配置组
        llm_config = getattr(settings, "LLM", {} or {})
        # 尝试读取 OPENAI_COMPATIBLE 配置组
        oc_config = getattr(settings, "OPENAI_COMPATIBLE", {} or {})
        # 尝试读取 OLLAMA 配置组
        ollama_config = getattr(settings, "OLLAMA", {} or {})

        # 根据 key 前缀选择配置组
        if key.startswith("OPENAI_COMPATIBLE_"):
            django_key = key.replace("OPENAI_COMPATIBLE_", "")
            raw_value = oc_config.get(django_key, default)
        elif key.startswith("OLLAMA_"):
            django_key = key.replace("OLLAMA_", "")
            raw_value = ollama_config.get(django_key, default)
        else:
            raw_value = llm_config.get(key, default)

        fallback_value = raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
        return fallback_value

    @classmethod
    def _get_system_config(cls, key: str, default: str = "") -> str:
        """
        从统一系统配置获取配置值

        优先级: 缓存 > SystemConfigService(带缓存) > Django settings > 默认值
        """
        # 先查缓存（async 预热后可直接命中）
        cached = cls._config_cache.get(key)
        if cached is not None:
            return cached

        # 如果在 async 上下文中，使用 _get_system_config_async 的同步等价逻辑
        # 注意: 此方法不应在 async 上下文中被直接调用，请使用 _get_system_config_async
        try:
            import asyncio
            asyncio.get_running_loop()
            # 在 async 上下文中，检测到 event loop
            # 尝试从缓存和 settings 获取，DB 查询应走 _get_system_config_async
            logger.debug(
                "[LLMConfig] _get_system_config 在 async 上下文中被调用 (key=%s), "
                "建议使用 _get_system_config_async",
                key,
            )
            fallback_value = cls._get_django_settings_fallback(key, default)
            return fallback_value if fallback_value else default
        except RuntimeError:
            pass  # 不在 async 上下文，正常执行

        # 尝试使用 SystemConfigService(带缓存)
        config_service = cls._get_config_service()
        if config_service is not None:
            try:
                raw_value = config_service.get_value(key, default="")
                value = raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
                if value:
                    cls._config_cache[key] = value
                    return value
            except (KeyError, AttributeError, TypeError):
                logger.warning("[LLMConfig] SystemConfigService 读取失败", extra={"key": key})

        # Fallback 到 Django settings(Requirement 5.4)
        fallback_value = cls._get_django_settings_fallback(key, default)
        if fallback_value:
            return fallback_value

        return default

    @classmethod
    async def _get_system_config_async(cls, key: str, default: str = "") -> str:
        """
        异步版本:从统一系统配置获取配置值

        优先级: 缓存 > SystemConfigService(带缓存,用 sync_to_async 包装) > Django settings > 默认值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        # 先查缓存（sync 预热后可直接命中）
        cached = cls._config_cache.get(key)
        if cached is not None:
            return cached

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
                    cls._config_cache[key] = value
                    return value
            except (KeyError, AttributeError, TypeError):
                logger.warning("[LLMConfig] 异步 SystemConfigService 读取失败", extra={"key": key})

        # Fallback 到 Django settings
        fallback_value = cls._get_django_settings_fallback(key, default)
        if fallback_value:
            return fallback_value

        return default

    # ============================================================
    # 通用配置方法
    # ============================================================

    @classmethod
    def get_temperature(cls) -> float:
        """获取默认生成温度"""
        temp_str = cls._get_system_config("LLM_TEMPERATURE", "0.3")
        try:
            return float(temp_str)
        except (ValueError, TypeError):
            return 0.3

    @classmethod
    def get_max_tokens(cls) -> int:
        """获取最大输出 Token 数"""
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
        """获取 Ollama 模型名称"""
        model = cls._get_system_config("OLLAMA_MODEL", "")
        if model:
            return model

        ollama_config = getattr(settings, "OLLAMA", {} or {})
        raw_value = ollama_config.get("MODEL")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return cls.DEFAULT_OLLAMA_MODEL

    @classmethod
    async def get_ollama_model_async(cls) -> str:
        """异步版本: 获取 Ollama 模型名称"""
        model = await cls._get_system_config_async("OLLAMA_MODEL", "")
        if model:
            return model

        ollama_config = getattr(settings, "OLLAMA", {} or {})
        raw_value = ollama_config.get("MODEL")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return cls.DEFAULT_OLLAMA_MODEL

    @classmethod
    def get_ollama_base_url(cls) -> str:
        """获取 Ollama 服务地址"""
        url = cls._get_system_config("OLLAMA_BASE_URL", "")
        if url:
            return url

        ollama_config = getattr(settings, "OLLAMA", {} or {})
        raw_value = ollama_config.get("BASE_URL")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return cls.DEFAULT_OLLAMA_BASE_URL

    @classmethod
    def get_ollama_timeout(cls) -> int:
        """获取 Ollama 超时时间（秒）。"""
        timeout_str = cls._get_system_config("OLLAMA_TIMEOUT", str(cls.DEFAULT_OLLAMA_TIMEOUT))
        try:
            return int(timeout_str)
        except (ValueError, TypeError):
            return cls.DEFAULT_OLLAMA_TIMEOUT

    @classmethod
    def get_ollama_embedding_model(cls) -> str:
        raw = cls._get_system_config("OLLAMA_EMBEDDING_MODEL", "")
        if raw and raw.strip():
            return raw.strip()

        ollama_config = getattr(settings, "OLLAMA", {} or {})
        raw_value = ollama_config.get("EMBEDDING_MODEL")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return cls.get_ollama_model()

    # ============================================================
    # OpenAI-compatible 配置方法
    # ============================================================

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
        return v

    @classmethod
    def get_openai_compatible_api_key(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_API_KEY", "")
        return cls._normalize_api_key(raw)

    @classmethod
    async def get_openai_compatible_api_key_async(cls) -> str:
        raw = await cls._get_system_config_async("OPENAI_COMPATIBLE_API_KEY", "")
        return cls._normalize_api_key(raw)

    @classmethod
    def get_openai_compatible_base_url(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)
        return cls.DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    @classmethod
    async def get_openai_compatible_base_url_async(cls) -> str:
        raw = await cls._get_system_config_async("OPENAI_COMPATIBLE_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)
        return cls.DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    @classmethod
    def get_openai_compatible_model(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_DEFAULT_MODEL", "")
        return (raw or "").strip() or cls.DEFAULT_OPENAI_COMPATIBLE_MODEL

    @classmethod
    async def get_openai_compatible_model_async(cls) -> str:
        raw = await cls._get_system_config_async("OPENAI_COMPATIBLE_DEFAULT_MODEL", "")
        return (raw or "").strip() or cls.DEFAULT_OPENAI_COMPATIBLE_MODEL

    @classmethod
    def get_openai_compatible_embedding_model(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_EMBEDDING_MODEL", "")
        if raw and raw.strip():
            return raw.strip()
        return cls.get_openai_compatible_model()

    @classmethod
    def get_openai_compatible_timeout(cls) -> int:
        timeout_str = cls._get_system_config("OPENAI_COMPATIBLE_TIMEOUT", "")
        if timeout_str:
            try:
                return int(timeout_str)
            except (ValueError, TypeError):
                return cls.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT
        return cls.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

    @classmethod
    async def get_openai_compatible_timeout_async(cls) -> int:
        timeout_str = await cls._get_system_config_async("OPENAI_COMPATIBLE_TIMEOUT", "")
        if timeout_str:
            try:
                return int(timeout_str)
            except (ValueError, TypeError):
                return cls.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT
        return cls.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

    # ============================================================
    # 后端选择
    # ============================================================

    @classmethod
    def get_default_backend(cls) -> str:
        raw = cls._get_system_config("LLM_DEFAULT_BACKEND", "")
        if raw and isinstance(raw, str):
            v = raw.strip().lower()
            if v in cls._VALID_BACKENDS:
                return v

        llm_settings = getattr(settings, "LLM", {} or {})
        v2 = llm_settings.get("DEFAULT_BACKEND")
        if isinstance(v2, str) and v2.strip():
            normalized = v2.strip().lower()
            if normalized in cls._VALID_BACKENDS:
                return normalized
        return "openai_compatible"

    @classmethod
    async def get_default_backend_async(cls) -> str:
        """异步版本: 获取默认 LLM 后端"""
        raw = await cls._get_system_config_async("LLM_DEFAULT_BACKEND", "")
        if raw and isinstance(raw, str):
            v = raw.strip().lower()
            if v in cls._VALID_BACKENDS:
                return v

        llm_settings = getattr(settings, "LLM", {} or {})
        v2 = llm_settings.get("DEFAULT_BACKEND")
        if isinstance(v2, str) and v2.strip():
            normalized = v2.strip().lower()
            if normalized in cls._VALID_BACKENDS:
                return normalized
        return "openai_compatible"

    @classmethod
    def get_backend_configs(cls) -> dict[str, BackendConfig]:
        from apps.core.llm.backends.base import BackendConfig

        def enabled_key(name: str) -> str:
            return f"LLM_BACKEND_{name.upper()}_ENABLED"

        def priority_key(name: str) -> str:
            return f"LLM_BACKEND_{name.upper()}_PRIORITY"

        default_priorities = {"ollama": 2, "openai_compatible": 1}
        default_enabled = {"ollama": True, "openai_compatible": True}

        configs: dict[str, BackendConfig] = {}
        for name in ("ollama", "openai_compatible"):
            enabled_raw = cls._get_system_config(enabled_key(name), "")
            enabled = cls._parse_bool(enabled_raw, default_enabled[name])

            # openai_compatible: 如果配置了 base_url 但未显式设置 enabled，自动启用
            if name == "openai_compatible" and not enabled and not enabled_raw:
                base_url = cls._get_system_config("OPENAI_COMPATIBLE_BASE_URL", "")
                if base_url:
                    enabled = True

            priority_raw = cls._get_system_config(priority_key(name), "")
            priority = cls._parse_int(priority_raw, default_priorities[name])

            if name == "ollama":
                configs[name] = BackendConfig(
                    name=name,
                    enabled=enabled,
                    priority=priority,
                    default_model=cls.get_ollama_model(),
                    base_url=cls.get_ollama_base_url(),
                    timeout=cls.get_ollama_timeout(),
                    embedding_model=cls.get_ollama_embedding_model(),
                )
            else:
                configs[name] = BackendConfig(
                    name=name,
                    enabled=enabled,
                    priority=priority,
                    default_model=cls.get_openai_compatible_model(),
                    base_url=cls.get_openai_compatible_base_url(),
                    api_key=cls.get_openai_compatible_api_key(),
                    timeout=cls.get_openai_compatible_timeout(),
                    embedding_model=cls.get_openai_compatible_embedding_model(),
                )
        return configs

    @classmethod
    def resolve_backend_for_model(cls, model: str) -> str:
        """
        根据模型名称推断应使用的后端.

        规则:
        - 模型名含 ":" → ollama（如 qwen3:0.6b）
        - 其余 → openai_compatible（如 kimi26）

        Args:
            model: 模型名称

        Returns:
            推断的后端名称
        """
        if not model:
            return cls.get_default_backend()
        for pattern, backend in cls._MODEL_BACKEND_RULES:
            if pattern in model:
                return backend
        return "openai_compatible"

    @classmethod
    def get_available_models(cls) -> list[dict[str, str]]:
        """
        获取所有已配置的可用模型列表（含后端信息）.

        合并 DEFAULT_AVAILABLE_MODELS 与 SystemConfig 中的 LLM_EXTRA_MODELS,
        为每个模型标注推荐后端.

        Returns:
            模型信息列表,每项含 id、name、backend
        """
        models: list[dict[str, str]] = []
        seen: set[str] = set()

        # 从默认列表收集
        for model_id in cls.DEFAULT_AVAILABLE_MODELS:
            if model_id not in seen:
                seen.add(model_id)
                models.append(
                    {
                        "id": model_id,
                        "name": model_id.split("/")[-1].split(":")[-1],
                        "backend": cls.resolve_backend_for_model(model_id),
                    }
                )

        # 从 SystemConfig 额外模型收集
        extra_raw = cls._get_system_config("LLM_EXTRA_MODELS", "")
        if extra_raw:
            for part in extra_raw.split(","):
                model_id = part.strip()
                if model_id and model_id not in seen:
                    seen.add(model_id)
                    models.append(
                        {
                            "id": model_id,
                            "name": model_id.split("/")[-1].split(":")[-1],
                            "backend": cls.resolve_backend_for_model(model_id),
                        }
                    )

        # 各后端的默认模型也加入列表（确保当前配置的默认模型可选）
        for backend_name, default_model in [
            ("ollama", cls.get_ollama_model()),
            ("openai_compatible", cls.get_openai_compatible_model()),
        ]:
            if default_model and default_model not in seen:
                seen.add(default_model)
                models.append(
                    {
                        "id": default_model,
                        "name": default_model.split("/")[-1].split(":")[-1],
                        "backend": backend_name,
                    }
                )

        return models

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
