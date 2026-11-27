"""qoder 的 BYOK（Bring Your Own Key）：把**律所网关**注册成它的一个自定义 provider。

## 为什么需要这一步（实测结论，不是推测）

文档的「模型选择」只教 `resolve_model` 返回**模型 id**；要把自家地址接进去必须走
BYOK 配置（CLI 里是 `/model` → Custom 向导，SDK 里是 ``Daemon.create_byok_config``）。
直接在 `resolve_model` 里返回 ``{url, api_key}`` 的自定义模型会被拒：

    RESULT errors: ['BYOK is disabled by your enterprise admin. Please contact them for details.']

而**注册过** provider 之后同一个账号就正常了：``create_byok_config`` 返回
``{'providerId': 'fachuan-gw'}``，``qodercli --list-models`` 立刻多出一行
``kimi-2.6 (fachuan-gw/kimi-2.6)``——那个 ``fachuan-gw/kimi-2.6`` 就是选模型时该传的 id。

## 一个不能省的坑：内网网关必须**清代理**

实测（本机 Clash）：带 ``HTTPS_PROXY`` 直连内网网关 → ``502`` 空 body；清掉代理 → ``200``。
所以 BYOK 模型的那一轮必须把代理变量清空（见 ``qoder_backend.build_env`` 的 ``direct``）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 我们注册的自定义 provider 的 id（进 Qoder 的 settings.json，也进模型 id 前缀）。
PLATFORM_PROVIDER_ID = "fachuan-gw"
#: 显示名（给用户在 `/model` 里看）。
PLATFORM_DISPLAY_NAME = "法穿网关"


def _daemon_options(config_dir: Any) -> Any:
    from qoder_agent_sdk import qodercli_auth
    from qoder_agent_sdk.daemon import DaemonOptions

    return DaemonOptions(auth=qodercli_auth(), env={"QODER_CONFIG_DIR": str(config_dir)})


async def list_saved(config_dir: Any) -> list[dict[str, Any]]:
    """已保存的 BYOK 条目（凭据已脱敏，只有 providerId / baseUrl / models）。"""
    from qoder_agent_sdk.daemon import Daemon

    async with Daemon(options=_daemon_options(config_dir)) as daemon:
        saved = await daemon.list_byok_configs()
    return [dict(item) for item in saved]


async def register_platform(config_dir: Any, settings: Any, *, target: Any) -> dict[str, Any]:
    """把律所网关注册成自定义 provider（幂等：已存在则先删再建）。

    Args:
        settings: ``GatewaySettings``（取模型白名单，注册时一并告诉 Qoder）。
        target: ``GatewayTarget``（base_url + 一把可用的 key）。

    Returns:
        ``{"provider_id": ..., "models": [...]}``
    """
    from qoder_agent_sdk.daemon import Daemon

    models = list(getattr(settings, "models", ()) or ())
    if target.model and target.model not in models:
        models.insert(0, target.model)
    from qoder_agent_sdk.daemon_types import CustomByokProviderConfigInput

    payload: CustomByokProviderConfigInput = {
        "providerId": PLATFORM_PROVIDER_ID,
        "baseUrl": target.base_url,
        "apiKey": target.api_key,
        "type": "openai-compatible",
        "protocol": "openai",
        "displayName": PLATFORM_DISPLAY_NAME,
        "model": target.model,
        "models": [{"model": name} for name in models],
    }
    async with Daemon(options=_daemon_options(config_dir)) as daemon:
        # 幂等：先删旧的（更新 api key / base_url 也走这条路，避免两条逻辑漂移）
        from qoder_agent_sdk._errors import QoderSDKError

        try:
            await daemon.delete_byok_config({"providerId": PLATFORM_PROVIDER_ID})
        except QoderSDKError:
            # 不存在时删除会报错，这是正常路径（首次注册 / 上次已删）。
            logger.debug("qoder BYOK 旧 provider 不存在，直接新建")
        check = await daemon.check_byok_config(payload)
        if not check.get("success"):
            logger.info(
                "qoder BYOK 校验未通过（仍然保存，运行时再看真实报错）: %s", json.dumps(check, ensure_ascii=False)[:300]
            )
        created = await daemon.create_byok_config(payload)
    from . import qoder_models

    qoder_models.invalidate()
    return {"provider_id": PLATFORM_PROVIDER_ID, "models": models, "result": dict(created)}


async def unregister(config_dir: Any, provider_id: str = PLATFORM_PROVIDER_ID) -> None:
    from qoder_agent_sdk.daemon import Daemon

    async with Daemon(options=_daemon_options(config_dir)) as daemon:
        await daemon.delete_byok_config({"providerId": provider_id})
    from . import qoder_models

    qoder_models.invalidate()


def is_byok_model(model: str | None) -> bool:
    """选中的模型是不是 BYOK 自定义模型（id 形如 ``fachuan-gw/kimi-2.6``）。

    判据用「含 ``/``」：Qoder 自己的模型 id 都是单词（``auto`` / ``ultimate`` …），
    自定义 provider 的模型 id 一定是 ``<providerId>/<model>``。
    """
    return bool(model and "/" in model)


__all__ = [
    "PLATFORM_DISPLAY_NAME",
    "PLATFORM_PROVIDER_ID",
    "is_byok_model",
    "list_saved",
    "settings_payload",
    "register_platform",
    "unregister",
]


def settings_payload(config_dir: Any) -> str:
    """把 CLI 写下的 ``settings.json`` 里的 **providers** 抽出来，作为 ``--settings`` 内联给 SDK。

    ## 为什么必须有这一步（实测）

    BYOK 的 provider 存在 ``<config dir>/settings.json`` 里，而 qoder 后端为了「不继承
    用户设置里的 ``permissions.allow``」一直传 ``setting_sources=[]``——于是**连自己
    刚注册的 provider 也读不到**，症状是模型选中了却报
    ``The request could not be completed. Please try again.``（CLI 直跑同一个模型是正常的，
    差别就在这两个参数）。

    只抽 ``providers`` 一个键：其余设置（权限白名单、hooks、telemetry …）一律不带，
    安全边界不因此放宽。
    """
    import json
    from pathlib import Path

    try:
        raw = Path(config_dir, "settings.json").read_text(encoding="utf-8")
    except OSError:
        return ""
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, dict) or not providers:
        return ""
    return json.dumps({"providers": providers}, ensure_ascii=False)
