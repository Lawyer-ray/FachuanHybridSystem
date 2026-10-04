"""Provider 注册表与配置解析。

配置来源为 SystemConfig(加密存储、admin 可改)，而非 Django settings：
密钥不落环境变量，改完不用重启；上线后换域名只需 admin 改
``SOCIAL_AUTH_FEISHU_REDIRECT_URI``。

为了让新平台接入只加代码不加判断，这里用一张「适配表」把
SystemConfig 键名映射到 ProviderConfig。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.core.models import SystemConfig

from .base import ProviderConfig

logger = logging.getLogger(__name__)

# SystemConfig 分类名
CATEGORY = "social_auth"

# 配置缓存 TTL：信号失效只在「写配置的那个进程」内生效（Admin 保存 → 同进程信号），
# 但 DB 也会被其它进程改——manage.py 脚本直写、多 worker 部署里其它 worker 的 Admin 写入
# ——运行中进程收不到任何信号，缓存将永久滞留在写入前（实测：绑定页长期显示
# 「该登录方式暂未开放」，只能重启）。TTL 让缓存最多滞后这么久后自动重建。
_CONFIG_TTL_SECONDS = 30.0

# 每个 Provider 在 SystemConfig 中的键名前缀与字段映射。
# 新增 Provider 只在这里加一行 + 一个 provider 文件，无需改动其它代码。
PROVIDER_SPECS: dict[str, dict[str, Any]] = {
    "feishu": {
        "display_name": "飞书",
        "prefix": "SOCIAL_AUTH_FEISHU_",
        "enabled_key": "SOCIAL_AUTH_FEISHU_ENABLED",
        "extra_keys": ("REDIRECT_URI", "SCOPE"),
        # 扫码登录与 IM 群聊共用同一个飞书自建应用，凭证直接复用「飞书配置」
        # 分类下的 FEISHU_APP_ID / FEISHU_APP_SECRET，避免同一个密钥填两遍、
        # 改的时候漏一边。填了 SOCIAL_AUTH_FEISHU_APP_ID 则优先用它
        # （应对将来扫码改用独立应用的场景）。
        "fallback_credentials": {"FEISHU_APP_ID": "client_id", "FEISHU_APP_SECRET": "client_secret"},
    },
    "wechat": {
        "display_name": "微信",
        "prefix": "SOCIAL_AUTH_WECHAT_",
        "enabled_key": "SOCIAL_AUTH_WECHAT_ENABLED",
        "extra_keys": ("REDIRECT_URI",),
    },
    "github": {
        "display_name": "GitHub",
        "prefix": "SOCIAL_AUTH_GITHUB_",
        "enabled_key": "SOCIAL_AUTH_GITHUB_ENABLED",
        "extra_keys": ("REDIRECT_URI", "SCOPE"),
        # 与 google 相同：无可复用的共用凭证分类，必须在本分类填
        # APP_ID / APP_SECRET，否则视为未配置完成（不出现在登录页）
    },
    "google": {
        "display_name": "Google",
        "prefix": "SOCIAL_AUTH_GOOGLE_",
        "enabled_key": "SOCIAL_AUTH_GOOGLE_ENABLED",
        "extra_keys": ("REDIRECT_URI", "SCOPE"),
        # 无 fallback_credentials：Google 没有可复用的共用凭证分类，
        # 必须在本分类填 APP_ID / APP_SECRET，否则视为未配置完成（不出现在登录页）
    },
}


def get_provider_spec(name: str) -> dict[str, Any] | None:
    """返回 Provider 的配置描述；未登记返回 None。"""
    return PROVIDER_SPECS.get(name)


class ProviderRegistry:
    """Provider 注册表。通过 @ProviderRegistry.register("name") 注册。"""

    _providers: dict[str, type[Any]] = {}

    # 配置缓存：provider 名 → ProviderConfig，**只装已启用的**。
    # 正因如此，「缓存非空」不等于「已完整加载」——按名局部失效会让两者不一致，
    # 所以 clear_configs() 一律整体清空（见该方法注释）。
    _configs: dict[str, ProviderConfig] = {}

    # 上次 load_configs 的单调时钟戳，供 TTL 兜底判断（见 _CONFIG_TTL_SECONDS）
    _configs_loaded_at: float = 0.0

    @classmethod
    def register(cls, name: str) -> Any:
        def decorator(provider_cls: type[Any]) -> type[Any]:
            cls._providers[name] = provider_cls
            return provider_cls

        return decorator

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._providers)

    @classmethod
    def get(cls, name: str) -> type[Any]:
        if name not in cls._providers:
            raise KeyError(f"Unknown provider: {name}")
        return cls._providers[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._providers

    @classmethod
    def clear_configs(cls) -> None:
        """清除配置缓存。**一律整体清空，不做按名局部失效。**

        ``_configs`` 只装**已启用**的 Provider，所以按名 pop 会让该名字从缓存里
        消失；而读取方（``enabled_list`` / provider-catalog 端点）是以「缓存是否
        为空」判断要不要重建的 —— 缓存里还有别的 Provider 时就不重建，新启用的
        Provider 于是永远缺席。

        实测（2026-09-27）：运行中填入 Google 凭证后，绑定页始终显示「该登录方式
        暂未开放」，必须重启后端才恢复。整体失效的代价只是下一次读取多几次查询
        （Provider 只有个位数）。
        """
        cls._configs.clear()

    @classmethod
    def load_configs(cls, provider_configs: dict[str, dict] | None = None) -> None:
        """从 SystemConfig 读取全部 Provider 配置。

        ``provider_configs`` 参数已废弃（保留以兼容旧调用方），
        传了会记一条 warning 并忽略——真实来源只有 SystemConfig，
        否则会出现「admin 改了一份、settings 里还有一份」的双源不一致。
        """
        if provider_configs:
            logger.warning("ProviderRegistry.load_configs 的 provider_configs 参数已废弃，配置请从 SystemConfig 读取")

        cls._configs.clear()
        for name in list(cls._providers):
            config = cls._build_config(name)
            if config is not None and config.is_enabled:
                cls._configs[name] = config
        cls._configs_loaded_at = time.monotonic()

    @classmethod
    def _build_config(cls, name: str) -> ProviderConfig | None:
        """用分类查询一次性取回该 Provider 全部配置，拼成 ProviderConfig。"""
        spec = PROVIDER_SPECS.get(name)
        if spec is None:
            return None

        prefix: str = spec["prefix"]
        rows = {
            str(row.key): str(row.value or "")
            for row in SystemConfig.objects.filter(category=CATEGORY, is_active=True, key__startswith=prefix)
        }
        if not rows:
            return None

        # enabled 显式配成 false 才下线，缺失视为启用
        enabled_raw = rows.get(spec["enabled_key"], "true").strip().lower()
        is_enabled = enabled_raw not in ("false", "0", "no", "off")

        extra = {
            suffix.lower(): rows[f"{prefix}{suffix}"] for suffix in spec["extra_keys"] if rows.get(f"{prefix}{suffix}")
        }

        # 凭证：本分类没填时，回落到共用分类（如 IM 群聊的飞书应用）。
        # 必须解密后再判断——Admin 保存 is_secret 项时会加密（见
        # SystemConfigAdminForm.clean_value），库里存的是密文，若直接当密钥发出去
        # 会得到 invalid_client，且现象隐蔽：授权页能打开、回调才失败。
        client_id = rows.get(f"{prefix}APP_ID", "")
        client_secret = cls._decrypt_secret(rows.get(f"{prefix}APP_SECRET", ""))
        if not client_id or not client_secret:
            borrowed_id, borrowed_secret = cls._borrow_credentials(spec)
            client_id = client_id or borrowed_id
            client_secret = client_secret or borrowed_secret

        # 缺 app_id 视为未配置完成，从前端列表隐藏（is_enabled=False 也能隐藏，
        # 但那样 admin 里看不出是「没填」还是「主动关掉」）
        return ProviderConfig(
            name=name,
            display_name=str(spec["display_name"]),
            client_id=client_id,
            client_secret=client_secret,
            is_enabled=is_enabled and bool(client_id),
            extra=extra,
        )

    @staticmethod
    def _decrypt_secret(value: str) -> str:
        """解密 SystemConfig 中可能被 Admin 表单加密的 secret。

        **读取侧必须调用**：Admin 保存 ``is_secret=True`` 的配置项时会走
        ``SecretCodec.encrypt``（见 ``SystemConfigAdminForm.clean_value``），
        库里落的是密文。直接把密文当密钥发给 Provider 会得到 ``invalid_client``，
        而且现象隐蔽——授权页能正常打开，直到回调换 token 才失败。

        未加密的值原样返回；解密失败返回空串（视为「未配置」），绝不把密文当密钥用。
        """
        if not value:
            return ""
        try:
            from apps.core.security.secret_codec import SecretCodec

            codec = SecretCodec()
            if not codec.is_encrypted(value):
                return value
            return codec.try_decrypt(value)
        except Exception as exc:  # pragma: no cover - 兜底，不该影响主流程
            logger.warning("解密 SystemConfig secret 失败: %s", exc)
            return ""

    @classmethod
    def _borrow_credentials(cls, spec: dict[str, Any]) -> tuple[str, str]:
        """从共用分类借凭证（飞书扫码登录复用 IM 群聊的飞书应用）。

        借用失败不能影响登录功能本身，静默返回空串交由上层判定「未配置」。
        """
        mapping = spec.get("fallback_credentials") or {}
        if not mapping:
            return "", ""

        try:
            rows = {
                str(row.key): str(row.value or "")
                for row in SystemConfig.objects.filter(key__in=list(mapping), is_active=True).exclude(category=CATEGORY)
            }
        except Exception as exc:  # pragma: no cover - 兜底，不该影响主流程
            logger.warning("读取共用飞书凭证失败: %s", exc)
            return "", ""

        return rows.get("FEISHU_APP_ID", ""), cls._decrypt_secret(rows.get("FEISHU_APP_SECRET", ""))

    @classmethod
    def ensure_configs_fresh(cls) -> None:
        """缓存为空或超过 TTL 时重建，读取方统一走这里。

        裸的「缓存非空就不重建」守卫对**同进程**写入是对的——SystemConfig 信号
        会即时清缓存；但对**跨进程**写入（manage.py 脚本直写、多 worker 部署里
        其它 worker 的 Admin 保存）收不到任何信号，缓存会永久滞留在写入前，
        实测表现为绑定页长期「该登录方式暂未开放」、只能重启后端。
        TTL 是兜底而非主路径：同进程信号失效后缓存已空，这里立即重建，零额外代价。
        """
        if not cls._configs or (time.monotonic() - cls._configs_loaded_at) >= _CONFIG_TTL_SECONDS:
            cls.load_configs()

    @classmethod
    def get_config(cls, name: str) -> ProviderConfig:
        # 先做 TTL 兜底（见 ensure_configs_fresh）：跨进程改过凭证/开关时，
        # 已缓存的 Provider 也要拿到新值，而不是只照顾「缓存里还没有」的名字
        cls.ensure_configs_fresh()
        if name not in cls._configs:
            # 允许运行中新增配置（例如刚跑完「初始化默认配置」）而无需重启
            config = cls._build_config(name)
            if config is None:
                raise KeyError(f"No config for provider: {name}")
            if not config.is_enabled:
                raise KeyError(f"Provider not enabled: {name}")
            cls._configs[name] = config
        return cls._configs[name]

    @classmethod
    def enabled_list(cls) -> list[dict[str, Any]]:
        """返回已启用的 Provider 列表（供前端渲染）。"""
        cls.ensure_configs_fresh()

        result: list[dict[str, Any]] = []
        for name in cls._providers:
            config = cls._configs.get(name)
            if not (config and config.is_enabled):
                continue
            instance = cls._providers[name](config)
            client_config = instance.get_client_config() or {}
            client_config["login_mode"] = instance.login_mode.value
            result.append(
                {
                    "name": name,
                    "display_name": config.display_name,
                    "client_config": client_config,
                }
            )
        return result


# 导入所有 Provider 以触发 @register 装饰器。
# 顺序即 ProviderRegistry.names() 的顺序，也就是登录页按钮的先后（保持字母序，
# 与 isort 的排序一致，避免被 lint 重排后 UI 顺序悄悄变化）。
from . import feishu, github, google, wechat
