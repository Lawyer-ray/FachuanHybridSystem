"""qoder 登录 API —— 状态查询、发起浏览器授权、轮询结果。

端点前缀：``/api/v1/agent``（qoder 子域）。

## 为什么要这三个端点（而不是让用户自己跑 ``qodercli login``）

用户全是律师，没有服务器 shell。他们能做的只有「点一下」。所以：

1. ``GET  /agent/qoder/auth``       —— 切换器要能提前知道「这家还没登录」（置灰 + 提示）
2. ``POST /agent/qoder/login``      —— 点按钮 → 后端起 ``qodercli login`` → 把授权链接交回
3. ``GET  /agent/qoder/login/{id}`` —— 前端轮询，授权完成后自动刷新清单

## 授权是**部署级**的，不是每个律师一套

Qoder 账号是全所共用的一份（Credits 也记在那一个账号上）。谁点了登录，全所都能用——
这一点必须在前端文案里说清（见 ``BackendOptionOut.action_label``），否则第二个律师
会以为自己没权限。

业务数据权限**不受影响**：工具调用走共享 MCP 的律师本人 token（``qoder_backend`` 的
``build_mcp_servers``），Qoder 账号只用来跑模型。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from ..backends import qoder_accounts, qoder_byok, qoder_login
from ..schemas.qoder_auth_schemas import QoderAccountOut, QoderAuthOut, QoderByokOut, QoderLoginIn, QoderLoginOut
from ._helpers import _user_id

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 后端登录"], auth=JWTOrSessionAuth())


def _mode() -> str:
    """凭据来源（``token`` / ``login`` / ``none``）。"""
    from ..backends.qoder_backend import ACCESS_TOKEN_ENV, SA_KEY_ENV

    if (os.environ.get(ACCESS_TOKEN_ENV, "") or os.environ.get(SA_KEY_ENV, "")).strip():
        return "token"
    if qoder_login.has_credential():
        return "login"
    return "none"


def _to_login_out(payload: dict[str, Any]) -> QoderLoginOut:
    return QoderLoginOut(
        login_id=str(payload.get("login_id") or ""),
        state=str(payload.get("state") or "waiting"),
        url=str(payload.get("url") or ""),
        message=str(payload.get("message") or ""),
        account=str(payload.get("account") or ""),
        account_id=str(payload.get("account_id") or ""),
    )


@router.get("/qoder/auth", response=QoderAuthOut)
def qoder_auth(request: Any) -> QoderAuthOut:
    """当前 qoder 登录态（只读本地凭据文件，不起进程、不联网）。"""
    authenticated = qoder_login.is_authenticated()
    accounts = [
        QoderAccountOut(
            id=account.id,
            name=account.name,
            usable=account.has_credential and account.healthy,
            last_error=account.last_error,
        )
        for account in qoder_accounts.list_accounts()
    ]
    return QoderAuthOut(
        authenticated=authenticated,
        account=accounts[0].name if accounts else "",
        mode=_mode(),
        message="" if authenticated else "未登录 Qoder：点「登录 Qoder」完成浏览器授权。",
        accounts=accounts,
    )


@router.post("/qoder/login", response=QoderLoginOut)
async def qoder_login_start(request: Any, payload: QoderLoginIn | None = None) -> QoderLoginOut:
    """发起一次浏览器授权，返回授权链接。

    Raises:
        HttpError 503: CLI 找不到 / 启动失败 / 30 秒内没给出链接（``BackendError``
            会被 Ninja 转成 500，那样前端只能显示「服务器错误」，所以这里显式转 503）。
    """
    from ninja.errors import HttpError

    from ..backends.base import BackendError

    try:
        out = await qoder_login.start_login((payload.account_id if payload else "") or None)
    except BackendError as exc:
        logger.warning("qoder 登录启动失败 user=%s: %s", _user_id(request), exc, exc_info=True)
        raise HttpError(503, exc.message) from exc
    logger.info("qoder 登录已发起 user=%s login=%s", _user_id(request), out.get("login_id"))
    return _to_login_out(out)


@router.get("/qoder/login/{login_id}", response=QoderLoginOut)
def qoder_login_status(request: Any, login_id: str) -> QoderLoginOut:
    """轮询某次授权的状态（未知 id 返回 ``state=expired``，不抛 404）。"""
    return _to_login_out(qoder_login.login_status(login_id))


@router.delete("/qoder/accounts/{account_id}", response=QoderAuthOut)
def qoder_account_remove(request: Any, account_id: str) -> QoderAuthOut:
    """把一个账号从池子里移除（凭据 + CLI 配置目录一起删）。

    为什么要能删：账号池是「额度容器」，加了新号之后旧号（离职、换套餐）留着只会
    让轮转把请求分给一个没额度的账号——每次都要多试一轮才落到能用的那个。
    """
    qoder_login.logout(account_id)
    logger.info("qoder 账号已移除 user=%s account=%s", _user_id(request), account_id)
    return qoder_auth(request)


@router.get("/qoder/byok", response=QoderByokOut)
def qoder_byok_state(request: Any) -> QoderByokOut:
    """平台模型（LLMProvider）有没有接进 qoder（BYOK 自定义 provider）。

    只读 ``settings.json``（BYOK 配置就存在那儿），不起进程。
    """
    from ..backends.qoder_accounts import LEGACY_ACCOUNT_ID, account_config_dir

    config_dir = account_config_dir(LEGACY_ACCOUNT_ID)
    try:
        import json

        raw = (config_dir / "settings.json").read_text(encoding="utf-8")
        providers = json.loads(raw).get("providers") or {}
    except (OSError, ValueError):
        providers = {}
    entry = providers.get(qoder_byok.PLATFORM_PROVIDER_ID) if isinstance(providers, dict) else None
    return QoderByokOut(
        registered=bool(entry),
        provider_id=qoder_byok.PLATFORM_PROVIDER_ID,
        display_name=qoder_byok.PLATFORM_DISPLAY_NAME,
        base_url=str((entry or {}).get("baseUrl") or ""),
    )


@router.post("/qoder/byok/platform", response=QoderByokOut)
async def qoder_byok_register(request: Any) -> QoderByokOut:
    """把「AI 平台」里配的网关注册成 qoder 的自定义 provider（一键接自己的模型）。

    Raises:
        HttpError 400: 平台没配（没有 base_url / key）。
        HttpError 502: Qoder 侧拒绝（例如账号没开通自定义模型）。
    """
    from ninja.errors import HttpError

    from ..backends.gateway_cache import get_gateway_settings, resolve_gateway_target
    from ..backends.qoder_accounts import LEGACY_ACCOUNT_ID, account_config_dir

    settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(None)
    target = resolve_gateway_target(settings, None)
    if settings is None or target is None:
        raise HttpError(400, "还没有可用的 AI 平台（base_url / api_key），请先在后台配置 LLMProvider")
    from qoder_agent_sdk._errors import QoderSDKError

    try:
        await qoder_byok.register_platform(account_config_dir(LEGACY_ACCOUNT_ID), settings, target=target)
    except (QoderSDKError, OSError) as exc:
        # Qoder 侧拒绝（账号没开通 / 目录不可写）→ 502 带原文，别让 500 把原因吞掉
        logger.warning("qoder BYOK 注册失败 user=%s: %s", _user_id(request), exc, exc_info=True)
        raise HttpError(502, f"Qoder 侧拒绝注册自有模型：{exc}") from exc
    logger.info("qoder BYOK 已注册平台网关 user=%s", _user_id(request))
    return qoder_byok_state(request)


@router.delete("/qoder/byok/platform", response=QoderByokOut)
async def qoder_byok_unregister(request: Any) -> QoderByokOut:
    """取消接入（把 qoder 的 settings.json 里那条 provider 删掉）。"""
    from ..backends.qoder_accounts import LEGACY_ACCOUNT_ID, account_config_dir

    await qoder_byok.unregister(account_config_dir(LEGACY_ACCOUNT_ID))
    logger.info("qoder BYOK 已取消接入 user=%s", _user_id(request))
    return qoder_byok_state(request)
