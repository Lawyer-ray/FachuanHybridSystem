"""金诚同达 OA 纯 HTTP 会话基建（常量 / 登录 / 失效判定 / 客户端工厂）。

收敛历史散点：auth.service.http_login、case_import.http_client、
client_import.service、case_guid.service 四处各写一份的登录与请求构造。

会话策略以 case_guid 为基准：磁盘缓存 cookies 优先（SSO 扫码登录的产物，
兼容仅扫码账号）→ 失效回退 http_login 账密登录 → 均不可用报友好错误。

注意：本模块不得 import auth.service（auth.service 反向依赖本模块的失效
判定），auth 实例一律以参数传入（鸭子类型），保持单向依赖。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .auth.constants import _DEFAULT_HTTP_TIMEOUT, _HTTP_HEADERS, _LOGIN_URL

logger = logging.getLogger("apps.oa_filing.jtn_http_session")

# ── 会话失效特征 ──────────────────────────────────────────────
# ① 302 / 停留在 member/login.aspx（登录页）
# ② ~441 字节 location.replace 占位页（网关踢回登录）
# ③ 同页渲染的登录失败文案（账密错误）
_LOGIN_URL_MARKER = "member/login.aspx"
_LOCATION_REPLACE_MARKER = "location.replace"
_SESSION_PLACEHOLDER_MAX_LEN = 2048
_LOGIN_FORM_HEAD_LEN = 2500
_LOGIN_ERROR_TEXT_TOKENS = ("账号或密码错误", "用户名或密码错误", "invalid password", "login failed")

# cookies 注入 Playwright context 时缺失 domain 的兜底（ims.jtn.com 同源会话）
_DEFAULT_COOKIE_DOMAIN = "ims.jtn.com"


# ── 失效判定（小件组合，调用方按语义拼装） ─────────────────────


def is_login_url(url: Any) -> bool:
    """URL 指向 OA 登录页。"""
    return _LOGIN_URL_MARKER in str(url).lower()


def is_session_placeholder(html_text: str) -> bool:
    """网关踢回登录的 location.replace 占位页（短页面 + 标记）。"""
    return len(html_text) < _SESSION_PLACEHOLDER_MAX_LEN and _LOCATION_REPLACE_MARKER in html_text


def has_login_form(html_text: str) -> bool:
    """页面头部含账密表单（userid + password 输入框）。

    只看前段：登录页结构在前，避免正文长文里的巧合命中。
    """
    head = html_text.lower()[:_LOGIN_FORM_HEAD_LEN]
    has_userid = 'name="userid"' in head or "name='userid'" in head
    has_password = 'name="password"' in head or "name='password'" in head
    return has_userid and has_password


def has_login_error_text(html_text: str) -> bool:
    """正文含登录失败文案。"""
    text_lower = html_text.lower()
    return any(token in text_lower for token in _LOGIN_ERROR_TEXT_TOKENS)


def is_oa_login_page(url: Any, html_text: str) -> bool:
    """响应是否为登录页 / 会话占位页（用于页面访问时的会话有效性判定）。"""
    return is_login_url(url) or is_session_placeholder(html_text) or has_login_error_text(html_text)


# ── 会话获取 ─────────────────────────────────────────────────


def cached_cookies(auth: Any) -> dict[str, str] | None:
    """读取磁盘缓存 cookies（playwright 格式）并转为 name→value 扁平 dict（httpx 用）。

    httpx 对无 domain 的 cookies 不做域过滤、随请求全量携带，
    与既有 http_login 扁平 dict 的语义一致。
    """
    cached = auth.load_cookies()
    if not cached:
        return None
    return {str(c["name"]): str(c["value"]) for c in cached}


def cached_cookies_raw(auth: Any) -> list[dict[str, Any]] | None:
    """读取磁盘缓存 cookies 原样（playwright 格式，保留 domain/path，注入 context 用）。"""
    cached = auth.load_cookies()
    if not cached:
        return None
    return list(cached)


async def http_login_cookies(auth: Any) -> dict[str, str]:
    """HTTP 账密登录获取会话 cookies；对仅扫码账号转译为友好错误。"""
    try:
        cookies: dict[str, str] = await auth.http_login()
    except Exception as exc:
        raise RuntimeError(
            "OA 会话无效，且该账号无法通过账密 HTTP 登录（可能仅支持扫码登录）；"
            "请先在 OA 立案/盖章等功能中完成一次登录刷新会话后重试"
        ) from exc
    return cookies


async def resolve_session_cookies(auth: Any) -> dict[str, str]:
    """缓存优先的会话 cookie 解析：磁盘缓存可用直接用，否则 HTTP 登录。"""
    cached = cached_cookies(auth)
    if cached is not None:
        return cached
    return await http_login_cookies(auth)


# ── 客户端构造 ───────────────────────────────────────────────


def build_client(
    cookies: dict[str, str] | None = None,
    *,
    timeout: float | None = None,
    connection_close: bool = False,
) -> httpx.AsyncClient:
    """构建 OA HTTP 客户端（统一 headers / trust_env=False 防代理环境变量劫持）。

    connection_close=True：串行分片场景禁用 keepalive（client_import 详情抓取先例）。
    """
    headers = {**_HTTP_HEADERS}
    if connection_close:
        headers["Connection"] = "close"
    kwargs: dict[str, Any] = {
        "headers": headers,
        "follow_redirects": True,
        "timeout": _DEFAULT_HTTP_TIMEOUT if timeout is None else timeout,
        "cookies": cookies or None,
        "trust_env": False,
    }
    if connection_close:
        kwargs["limits"] = httpx.Limits(max_connections=1, max_keepalive_connections=0)
    return httpx.AsyncClient(**kwargs)


def to_context_cookie_list(cookies: dict[str, str]) -> list[dict[str, str]]:
    """扁平 cookies → Playwright add_cookies 格式（无 domain 信息时兜底 ims.jtn.com）。"""
    return [
        {"name": name, "value": value, "domain": _DEFAULT_COOKIE_DOMAIN, "path": "/"} for name, value in cookies.items()
    ]
