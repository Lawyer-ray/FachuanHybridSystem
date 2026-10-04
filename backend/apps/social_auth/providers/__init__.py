"""Provider 注册表与配置解析。

配置来源为 ``SocialAuthProvider`` 表（一行一个平台，密钥走 ``EncryptedTextField``
模型层透明加解密），而非 Django settings：密钥不落环境变量，改完不用重启；
上线后换域名只需 admin 改 ``redirect_uri``。

历史上配置存 ``SystemConfig`` 的 19 行 ``SOCIAL_AUTH_*`` KV，读取层用适配表
拼回结构体；独立成表后本模块只做「查一行 → 构造 ProviderConfig」。
为了让新平台接入只加代码不加判断，``PROVIDER_SPECS`` 保留纯代码侧的注册
信息（显示名默认值 + 可借用的共用凭证定义）。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.core.models import SystemConfig
from apps.social_auth.models import SocialAuthProvider

from .base import ProviderConfig

logger = logging.getLogger(__name__)

# 配置缓存 TTL：信号失效只在「写配置的那个进程」内生效（Admin 保存 → 同进程信号），
# 但 DB 也会被其它进程改——manage.py 脚本直写、多 worker 部署里其它 worker 的 Admin 写入
# ——运行中进程收不到任何信号，缓存将永久滞留在写入前（实测：绑定页长期显示
# 「该登录方式暂未开放」，只能重启）。TTL 让缓存最多滞后这么久后自动重建。
_CONFIG_TTL_SECONDS = 30.0

# 每个 Provider 的代码侧注册信息。新增 Provider 只在这里加一行 + 一个 provider 文件。
PROVIDER_SPECS: dict[str, dict[str, Any]] = {
    "feishu": {
        "display_name": "飞书",
        # 扫码登录与 IM 群聊共用同一个飞书自建应用，凭证留空时直接借「飞书配置」
        # 分类下的 FEISHU_APP_ID / FEISHU_APP_SECRET，避免同一个密钥填两遍、
        # 改的时候漏一边。填了自己的 client_id/client_secret 则优先用（应对将来
        # 扫码改用独立应用的场景）。
        "fallback_credentials": {"FEISHU_APP_ID": "client_id", "FEISHU_APP_SECRET": "client_secret"},
    },
    "wechat": {
        "display_name": "微信",
    },
    "github": {
        "display_name": "GitHub",
        # 无可复用的共用凭证分类，必须填 client_id / client_secret，
        # 否则视为未配置完成（不出现在登录页）
    },
    "google": {
        "display_name": "Google",
        # 无可复用的共用凭证分类，必须填 client_id / client_secret，
        # 否则视为未配置完成（不出现在登录页）
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
        """从 SocialAuthProvider 表读取全部 Provider 配置。

        ``provider_configs`` 参数已废弃（保留以兼容旧调用方），
        传了会记一条 warning 并忽略——真实来源只有数据库，
        否则会出现「admin 改了一份、代码里还有一份」的双源不一致。
        """
        if provider_configs:
            logger.warning(
                "ProviderRegistry.load_configs 的 provider_configs 参数已废弃，配置请从 SocialAuthProvider 读取"
            )

        cls._configs.clear()
        for name in list(cls._providers):
            config = cls._build_config(name)
            if config is not None and config.is_enabled:
                cls._configs[name] = config
        cls._configs_loaded_at = time.monotonic()

    @classmethod
    def _build_config(cls, name: str) -> ProviderConfig | None:
        """查一行 SocialAuthProvider，构造 ProviderConfig；未配置该平台返回 None。"""
        spec = PROVIDER_SPECS.get(name)
        if spec is None:
            return None

        row = SocialAuthProvider.objects.filter(name=name).first()
        if row is None:
            return None

        client_id = str(row.client_id or "").strip()
        # client_secret 由 EncryptedTextField 在模型层解密，读到的已是明文
        client_secret = str(row.client_secret or "").strip()
        if not client_id or not client_secret:
            borrowed_id, borrowed_secret = cls._borrow_credentials(spec)
            client_id = client_id or borrowed_id
            client_secret = client_secret or borrowed_secret

        extra: dict[str, str] = {}
        if row.redirect_uri:
            extra["redirect_uri"] = str(row.redirect_uri).strip()
        if row.scope:
            extra["scope"] = str(row.scope).strip()

        # 缺 client_id 视为未配置完成，从前端列表隐藏（enabled=False 也能隐藏，
        # 但那样 admin 里看不出是「没填」还是「主动关掉」）
        return ProviderConfig(
            name=name,
            display_name=str(row.display_name or spec["display_name"]),
            client_id=client_id,
            client_secret=client_secret,
            is_enabled=row.enabled and bool(client_id),
            priority=row.priority,
            extra=extra,
        )

    @staticmethod
    def _decrypt_secret(value: str) -> str:
        """解密 SystemConfig 中可能被 Admin 表单加密的 secret。

        借用「飞书配置」共用凭证时仍从 SystemConfig 读取，**必须调用本方法**：
        Admin 保存 ``is_secret=True`` 的配置项时会走 ``SecretCodec.encrypt``
        （见 ``SystemConfigAdminForm.clean_value``），库里落的是密文。直接把密文
        当密钥发给 Provider 会得到 ``invalid_client``，而且现象隐蔽——授权页能
        正常打开，直到回调换 token 才失败。

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
        """从 SystemConfig 共用分类借凭证（飞书扫码登录复用 IM 群聊的飞书应用）。

        借用失败不能影响登录功能本身，静默返回空串交由上层判定「未配置」。
        """
        mapping = spec.get("fallback_credentials") or {}
        if not mapping:
            return "", ""

        try:
            rows = {
                str(row.key): str(row.value or "")
                for row in SystemConfig.objects.filter(key__in=list(mapping), is_active=True)
            }
        except Exception as exc:  # pragma: no cover - 兜底，不该影响主流程
            logger.warning("读取共用飞书凭证失败: %s", exc)
            return "", ""

        return rows.get("FEISHU_APP_ID", ""), cls._decrypt_secret(rows.get("FEISHU_APP_SECRET", ""))

    @classmethod
    def ensure_configs_fresh(cls) -> None:
        """缓存为空或超过 TTL 时重建，读取方统一走这里。

        裸的「缓存非空就不重建」守卫对**同进程**写入是对的——SocialAuthProvider
        保存/删除的信号会即时清缓存；但对**跨进程**写入（manage.py 脚本直写、
        多 worker 部署里其它 worker 的 Admin 保存）收不到任何信号，缓存会永久
        滞留在写入前，实测表现为绑定页长期「该登录方式暂未开放」、只能重启后端。
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
            # 允许运行中新增配置（例如刚在 admin 建好一行）而无需重启
            config = cls._build_config(name)
            if config is None:
                raise KeyError(f"No config for provider: {name}")
            if not config.is_enabled:
                raise KeyError(f"Provider not enabled: {name}")
            cls._configs[name] = config
        return cls._configs[name]

    @classmethod
    def enabled_list(cls) -> list[dict[str, Any]]:
        """返回已启用的 Provider 列表（供前端渲染），按 priority 升序。"""
        cls.ensure_configs_fresh()

        result: list[dict[str, Any]] = []
        ordered = sorted(
            cls._providers, key=lambda n: (cls._configs[n].priority, n) if n in cls._configs else (9999, n)
        )
        for name in ordered:
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
from . import feishu, github, google, wechat
