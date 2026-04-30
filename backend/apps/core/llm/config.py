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

    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
    DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
    DEFAULT_TIMEOUT = 900

    # Ollama 默认值 (Requirements: 2.2, 2.3)
    DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"
    DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
    DEFAULT_OLLAMA_TIMEOUT = 300

    # OpenAI-compatible 默认值（用于 Moonshot/Kimi/DeepSeek 等兼容接口）
    DEFAULT_OPENAI_COMPATIBLE_MODEL = "moonshot-v1-8k"
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.moonshot.cn/v1"
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT = 120
    # Moonshot 历史常量别名（兼容旧调用与测试）
    DEFAULT_MOONSHOT_MODEL = DEFAULT_OPENAI_COMPATIBLE_MODEL
    DEFAULT_MOONSHOT_BASE_URL = DEFAULT_OPENAI_COMPATIBLE_BASE_URL
    DEFAULT_MOONSHOT_TIMEOUT = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

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
        "zai-org/GLM-4.6V",
        "zai-org/GLM-4.7",
        "zai-org/GLM-4-32B-0414",
        "zai-org/GLM-Z1-32B-0414",
        "THUDM/glm-4-9b-chat",
        # 其他模型
        "Pro/ByteDance/Seed-OSS-36B-Instruct",
        "Pro/Tencent/Hunyuan-Translation-7B",
        "Pro/inclusionAI/Ring-flash-2.0",
    ]

    # 模型名 → 后端映射规则：含 "/" 的走 siliconflow，含 ":" 的走 ollama，其余走 openai_compatible
    _MODEL_BACKEND_RULES: ClassVar[list[tuple[str, str]]] = [
        ("/", "siliconflow"),
        (":", "ollama"),
    ]

    # 缓存 SystemConfigService 实例
    _config_service: SystemConfigService | None = None
    _VALID_BACKENDS: ClassVar[set[str]] = {"siliconflow", "ollama", "openai_compatible", "moonshot"}

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
        siliconflow_config = getattr(settings, "SILICONFLOW", {} or {})
        django_key = key.replace("SILICONFLOW_", "")
        raw_value = siliconflow_config.get(django_key, default)
        fallback_value = raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
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
                    return value
            except (KeyError, AttributeError, TypeError):
                logger.warning("[LLMConfig] 异步 SystemConfigService 读取失败", extra={"key": key})

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
        raw = cls._get_system_config("SILICONFLOW_DEFAULT_MODEL", "")
        if not raw:
            # 兼容历史配置键
            raw = cls._get_system_config("SILICONFLOW_MODEL", cls.DEFAULT_MODEL)
        return (raw or "").strip() or cls.DEFAULT_MODEL

    @classmethod
    async def get_default_model_async(cls) -> str:
        raw = await cls._get_system_config_async("SILICONFLOW_DEFAULT_MODEL", "")
        if not raw:
            raw = await cls._get_system_config_async("SILICONFLOW_MODEL", cls.DEFAULT_MODEL)
        return (raw or "").strip() or cls.DEFAULT_MODEL

    @classmethod
    def get_embedding_model(cls) -> str:
        raw = cls._get_system_config("SILICONFLOW_EMBEDDING_MODEL", "")
        if not raw:
            return cls.get_default_model()
        return (raw or "").strip() or cls.get_default_model()

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

    @classmethod
    def get_openai_compatible_api_key(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_API_KEY", "")
        if raw:
            return cls._normalize_api_key(raw)
        return cls.get_moonshot_api_key()

    @classmethod
    async def get_openai_compatible_api_key_async(cls) -> str:
        raw = await cls._get_system_config_async("OPENAI_COMPATIBLE_API_KEY", "")
        if raw:
            return cls._normalize_api_key(raw)
        raw = await cls._get_system_config_async("MOONSHOT_API_KEY", "")
        if raw:
            return cls._normalize_api_key(raw)
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("API_KEY", "")
        if isinstance(fallback, str):
            return cls._normalize_api_key(fallback)
        return ""

    @classmethod
    def get_openai_compatible_base_url(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)
        return cls.get_moonshot_base_url()

    @classmethod
    async def get_openai_compatible_base_url_async(cls) -> str:
        raw = await cls._get_system_config_async("OPENAI_COMPATIBLE_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)
        raw = await cls._get_system_config_async("MOONSHOT_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("BASE_URL", cls.DEFAULT_MOONSHOT_BASE_URL)
        if isinstance(fallback, str):
            return cls._normalize_base_url(fallback)
        return cls.DEFAULT_MOONSHOT_BASE_URL

    @classmethod
    def get_openai_compatible_model(cls) -> str:
        raw = cls._get_system_config("OPENAI_COMPATIBLE_DEFAULT_MODEL", "")
        if raw:
            return (raw or "").strip() or cls.DEFAULT_OPENAI_COMPATIBLE_MODEL
        return cls.get_moonshot_default_model()

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
        return cls.get_moonshot_timeout()

    @classmethod
    async def get_openai_compatible_timeout_async(cls) -> int:
        timeout_str = await cls._get_system_config_async("OPENAI_COMPATIBLE_TIMEOUT", "")
        if timeout_str:
            try:
                return int(timeout_str)
            except (ValueError, TypeError):
                return cls.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT
        timeout_str = await cls._get_system_config_async("MOONSHOT_TIMEOUT", "")
        if timeout_str:
            try:
                return int(timeout_str)
            except (ValueError, TypeError):
                return cls.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("TIMEOUT", cls.DEFAULT_MOONSHOT_TIMEOUT)
        try:
            return int(fallback)
        except (ValueError, TypeError):
            return cls.DEFAULT_MOONSHOT_TIMEOUT

    @classmethod
    def get_moonshot_api_key(cls) -> str:
        raw = cls._get_system_config("MOONSHOT_API_KEY", "")
        if raw:
            return cls._normalize_api_key(raw)
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("API_KEY", "")
        if isinstance(fallback, str):
            return cls._normalize_api_key(fallback)
        return ""

    @classmethod
    def get_moonshot_base_url(cls) -> str:
        raw = cls._get_system_config("MOONSHOT_BASE_URL", "")
        if raw:
            return cls._normalize_base_url(raw)
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("BASE_URL", cls.DEFAULT_MOONSHOT_BASE_URL)
        if isinstance(fallback, str):
            return cls._normalize_base_url(fallback)
        return cls.DEFAULT_MOONSHOT_BASE_URL

    @classmethod
    def get_moonshot_default_model(cls) -> str:
        raw = cls._get_system_config("MOONSHOT_MODEL", "")
        if raw and raw.strip():
            return raw.strip()
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("DEFAULT_MODEL", cls.DEFAULT_MOONSHOT_MODEL)
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return cls.DEFAULT_MOONSHOT_MODEL

    @classmethod
    def get_moonshot_timeout(cls) -> int:
        raw = cls._get_system_config("MOONSHOT_TIMEOUT", "")
        if raw:
            try:
                return int(raw)
            except (ValueError, TypeError):
                return cls.DEFAULT_MOONSHOT_TIMEOUT
        moonshot_config = getattr(settings, "MOONSHOT", {} or {})
        fallback = moonshot_config.get("TIMEOUT", cls.DEFAULT_MOONSHOT_TIMEOUT)
        try:
            return int(fallback)
        except (ValueError, TypeError):
            return cls.DEFAULT_MOONSHOT_TIMEOUT

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
        return "siliconflow"

    @classmethod
    def get_backend_configs(cls) -> dict[str, BackendConfig]:
        from apps.core.llm.backends.base import BackendConfig

        def enabled_key(name: str) -> str:
            return f"LLM_BACKEND_{name.upper()}_ENABLED"

        def priority_key(name: str) -> str:
            return f"LLM_BACKEND_{name.upper()}_PRIORITY"

        default_priorities = {"siliconflow": 1, "ollama": 2, "openai_compatible": 3}
        default_enabled = {"siliconflow": True, "ollama": True, "openai_compatible": False}

        def _read_with_legacy_keys(
            key_builder: Any,
            backend_name: str,
            *,
            legacy_name: str | None = None,
        ) -> str:
            value = cls._get_system_config(key_builder(backend_name), "")
            if value:
                return value
            if legacy_name:
                return cls._get_system_config(key_builder(legacy_name), "")
            return ""

        configs: dict[str, BackendConfig] = {}
        for name in ("siliconflow", "ollama", "openai_compatible"):
            legacy_name = "moonshot" if name == "openai_compatible" else None
            enabled_raw = _read_with_legacy_keys(enabled_key, name, legacy_name=legacy_name)
            enabled = cls._parse_bool(enabled_raw, default_enabled[name])

            priority_raw = _read_with_legacy_keys(priority_key, name, legacy_name=legacy_name)
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
                    embedding_model=cls.get_embedding_model(),
                )
            elif name == "ollama":
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
                # 兼容历史后端名 moonshot（与 openai_compatible 共享同一配置）
                configs["moonshot"] = BackendConfig(
                    name="moonshot",
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
        - 模型名含 "/" → siliconflow（如 Qwen/Qwen2.5-7B-Instruct）
        - 模型名含 ":" → ollama（如 qwen3:0.6b）
        - 其余 → openai_compatible（如 Qwen3.5-397B-A17B、moonshot-v1-8k）

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
                models.append({
                    "id": model_id,
                    "name": model_id.split("/")[-1].split(":")[-1],
                    "backend": cls.resolve_backend_for_model(model_id),
                })

        # 从 SystemConfig 额外模型收集
        extra_raw = cls._get_system_config("LLM_EXTRA_MODELS", "")
        if extra_raw:
            for part in extra_raw.split(","):
                model_id = part.strip()
                if model_id and model_id not in seen:
                    seen.add(model_id)
                    models.append({
                        "id": model_id,
                        "name": model_id.split("/")[-1].split(":")[-1],
                        "backend": cls.resolve_backend_for_model(model_id),
                    })

        # 各后端的默认模型也加入列表（确保当前配置的默认模型可选）
        for backend_name, default_model in [
            ("siliconflow", cls.get_default_model()),
            ("ollama", cls.get_ollama_model()),
            ("openai_compatible", cls.get_openai_compatible_model()),
        ]:
            if default_model and default_model not in seen:
                seen.add(default_model)
                models.append({
                    "id": default_model,
                    "name": default_model.split("/")[-1].split(":")[-1],
                    "backend": backend_name,
                })

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
