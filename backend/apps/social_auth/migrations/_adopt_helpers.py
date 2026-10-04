"""SystemConfig → SocialAuthProvider 的收养逻辑。

放在独立模块（迁移文件名以数字开头无法被单测 import），签名沿用迁移
``RunPython(apps, schema_editor)`` 约定——迁移执行时传 historical models 的
registry，单测可直接传 ``django.apps.apps``。
"""

from __future__ import annotations

from typing import Any

# (平台标识, 显示名, SystemConfig 键前缀, 登录页排序)
# priority 沿用迁移前的登录页按钮顺序（代码注册的字母序）。
# 平台映射在此**固化**（不 import 运行时的 PROVIDER_SPECS），保证迁移行为不随代码演进变化。
_PROVIDER_ROWS: list[tuple[str, str, str, int]] = [
    ("feishu", "飞书", "SOCIAL_AUTH_FEISHU_", 10),
    ("github", "GitHub", "SOCIAL_AUTH_GITHUB_", 20),
    ("google", "Google", "SOCIAL_AUTH_GOOGLE_", 30),
    ("wechat", "微信", "SOCIAL_AUTH_WECHAT_", 40),
]

_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})


def _to_plaintext_secret(raw: str) -> str:
    """SystemConfig 的 secret 值统一解密成明文（密文/明文兼容）。"""
    if not raw:
        return ""
    from apps.core.security.secret_codec import SecretCodec

    codec = SecretCodec()
    if not codec.is_encrypted(raw):
        return raw
    try:
        return codec.try_decrypt(raw)
    except Exception:
        # 解密失败按「未配置」处理，绝不能把密文搬进新表当明文用
        return ""


def adopt_social_auth_configs(apps: Any, schema_editor: Any) -> None:
    """把 SystemConfig 里 category='social_auth' 的 KV 组收养成 SocialAuthProvider 行。

    收养完成后删除旧 KV 行，避免双源。secret 统一解密成明文后交给
    ``client_secret``，由 ``EncryptedTextField.get_prep_value`` 重新加密落库。
    """
    SystemConfig = apps.get_model("core", "SystemConfig")
    SocialAuthProvider = apps.get_model("social_auth", "SocialAuthProvider")

    rows = {
        str(row.key): str(row.value or "")
        for row in SystemConfig.objects.filter(category="social_auth").values_list("key", "value", named=True)
    }
    if not rows:
        return

    for name, display_name, prefix, priority in _PROVIDER_ROWS:
        if not any(key.startswith(prefix) for key in rows):
            continue

        enabled_raw = rows.get(f"{prefix}ENABLED", "true").strip().lower()
        SocialAuthProvider.objects.update_or_create(
            name=name,
            defaults={
                "display_name": display_name,
                "client_id": rows.get(f"{prefix}APP_ID", "").strip(),
                "client_secret": _to_plaintext_secret(rows.get(f"{prefix}APP_SECRET", "")),
                "redirect_uri": rows.get(f"{prefix}REDIRECT_URI", "").strip(),
                "scope": rows.get(f"{prefix}SCOPE", "").strip(),
                "enabled": enabled_raw not in _DISABLED_VALUES,
                "priority": priority,
            },
        )

    # 旧 KV 行已完成收养，删除避免双源（SystemConfig 页面不再显示该分类）
    SystemConfig.objects.filter(category="social_auth").delete()
