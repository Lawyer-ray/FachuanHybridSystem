"""金诚同达 OA 案号查 GUID —— 案件管理页搜索，纯 HTTP（含飞连一键登录自愈）。

搜索机制（方法一）：案件管理列表页 WebForms postback——GET 列表页提取
__VIEWSTATE，POST 过滤字段（project_no/project_name/project_cust_name 三选一，
子串包含匹配），从结果行 projectView 链接提取 keyid=<GUID>。传完整案号通常
唯一命中。**不用 searchdlg 对话框**：2026-10-12 实测对话框对表单登录会话
恒返回 TotalCount=0（只认浏览器 SSO 派生会话），列表页对同一会话正常。

会话自愈（单 client 顺序恢复，实测 2026-10-06 / 2026-10-12）：

① 网关层：ims.jtn.com 前置飞连网关，首个 GET 被弹 corplink/agw/callback，
   回调响应 Set-Cookie 下发新网关会话（body 是 JS location.replace 回跳页）；
② SSO 门户层：缓存里的 access.jtn.com SSO 会话过期时，authorize 被弹到
   access.jtn.com/login（飞连 SPA，JTN 租户无账密表单）——此时走「桌面一键
   登录」纯 HTTP 复刻：本机飞连客户端（127.0.0.1:31080）签发一次性 token，
   POST 门户 /api/quick-login 恢复 SSO 会话。**一键登录身份=本机飞连客户端
   当前登录用户**（单机部署即机主本人）；OA 应用层仍用各律师自己的凭证登录，
   案件可见性按凭证账号过滤，两层身份不混用；
③ 应用层：网关放行后弹到 member/login.aspx，提取 CSRFToken POST 账密登录。

铁律沿用 v27.3.4：网关自愈、门户恢复、账密登录必须在**同一个 httpx client**
内完成（新建 client = 丢弃中途 Set-Cookie = 假失败）。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from lxml import html as lxml_html

from ..auth.service import JtnAuthService
from ..http_session import (
    build_client,
    cached_cookies,
    has_login_error_text,
    is_login_url,
    is_oa_login_page,
    is_sso_gateway_url,
)
from .constants import (
    _CASE_LIST_URL,
    _CURRENT_PAGE_FIELD,
    _KEYID_REGEX,
    _LOCAL_QUICK_LOGIN_ORIGIN,
    _LOCAL_QUICK_LOGIN_URL,
    _PORTAL_SESSION_COOKIE_NAMES,
    _SEARCH_CASE_NAME_FIELD,
    _SEARCH_CASE_NO_FIELD,
    _SEARCH_CUST_NAME_FIELD,
    _SSO_PORTAL_LOGIN_MARKER,
    _SSO_QUICK_LOGIN_SCENE,
    _SSO_QUICK_LOGIN_URL,
    _VIEWSTATE_FIELD,
    _VIEWSTATE_GENERATOR_FIELD,
)

logger = logging.getLogger("apps.oa_filing.jtn_case_guid")

# 会话恢复的最大 GET 轮数：门户一键恢复 → 网关回调 → 应用层登录 → 各留余量
_MAX_SESSION_ROUNDS = 6
_SESSION_ROUND_GAP_SECONDS = 0.3

# 本机飞连客户端探活的单端点超时（秒）
_LOCAL_QUICK_LOGIN_TIMEOUT = 5.0


def extract_viewstate_fields(html_text: str) -> dict[str, str]:
    """从列表页 HTML 提取 ASP.NET 回传所需的隐藏字段。

    VIEWSTATE 缺失说明拿到的是登录页/网关占位页，调用方应视为会话无效。
    """
    fields: dict[str, str] = {}
    for name in (_VIEWSTATE_FIELD, _VIEWSTATE_GENERATOR_FIELD):
        match = re.search(rf'id="{name}"[^>]*value="([^"]*)"', html_text)
        if match:
            fields[name] = match.group(1)
    return fields


def extract_case_guids(html_text: str, keyword: str) -> list[str]:
    """从搜索结果 HTML 提取命中案件的 GUID（按出现顺序去重）。

    主路径按行解析：结果行文本包含关键词且行内有 projectView.aspx?keyid= 链接；
    仅当 lxml 解析失败时回退文档同款整页正则。行解析成功但 0 命中视为真 0 命中
    （服务端已按关键词过滤，不再整页捞回，避免误提页面其他区域的 keyid）。
    传完整案号通常唯一命中，部分关键词可得多候选。
    """
    guid_index: dict[str, None] = {}
    try:
        root = lxml_html.fromstring(html_text)
    except Exception:
        logger.debug("lxml 解析搜索结果失败，回退整页正则: %s", keyword, exc_info=True)
        return list(dict.fromkeys(guid.lower() for guid in _KEYID_REGEX.findall(html_text)))

    for row in root.xpath("//tr"):
        if keyword not in "".join(row.itertext()):
            continue
        for link in row.xpath('.//a[contains(@href, "projectView.aspx") and contains(@href, "keyid=")]'):
            href = str(link.get("href") or "")
            for guid in _KEYID_REGEX.findall(href):
                guid_index.setdefault(guid.lower(), None)
    return list(guid_index)


def _is_sso_portal_login_page(url: Any) -> bool:
    """URL 停在飞连 SSO 门户登录页（需要恢复门户会话，而非仅吃回调 Set-Cookie）。"""
    return _SSO_PORTAL_LOGIN_MARKER in str(url).lower()


def _drop_flat_cookies(client: httpx.AsyncClient, names: frozenset[str]) -> None:
    """清除无 domain 的扁平缓存 cookies（存在才清）。

    缓存扁平值与门户/网关新下发的域 scoped 值同名共存时：请求头旧值在前压过
    新值（网关死循环），且 client.cookies.get() 直接抛 CookieConflict。
    """
    jar = client.cookies.jar
    for cookie in [c for c in jar if c.name in names and not c.domain]:
        try:
            jar.clear(cookie.domain, cookie.path, cookie.name)
        except KeyError:  # pragma: no cover - jar 迭代后已被清除的竞态
            continue


def _portal_csrf_token(client: httpx.AsyncClient) -> str:
    """取 access.jtn.com 域 scoped 的 csrf-token（门户登录 POST 的 CSRF 头）。"""
    for cookie in client.cookies.jar:
        if cookie.name == "csrf-token" and "access.jtn.com" in (cookie.domain or ""):
            return str(cookie.value)
    return ""


async def _fetch_local_quick_login_token() -> str | None:
    """从本机飞连客户端取一键登录一次性 token（客户端未运行/未登录返回 None）。"""
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=_LOCAL_QUICK_LOGIN_TIMEOUT) as client:
            resp = await client.get(
                _LOCAL_QUICK_LOGIN_URL,
                headers={"Origin": _LOCAL_QUICK_LOGIN_ORIGIN, "Referer": _LOCAL_QUICK_LOGIN_ORIGIN + "/"},
            )
        payload = resp.json()
        token = payload.get("data") if isinstance(payload, dict) else None
        return str(token) if isinstance(token, str) and token else None
    except Exception:
        logger.info("本机飞连客户端一键登录端点不可用: %s", _LOCAL_QUICK_LOGIN_URL, exc_info=True)
        return None


class JtnCaseGuidScript:
    """金诚同达 OA 案号查 GUID 门面（纯 HTTP，列表页搜索）。"""

    def __init__(self, account: str, password: str) -> None:
        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def lookup_case_guids(self, case_no: str) -> list[str]:
        """按案号查询 OA 案件 GUID 列表（project_no）。"""
        return await self._lookup_with_retry(field=_SEARCH_CASE_NO_FIELD, keyword=case_no)

    async def lookup_case_guids_by_name(self, case_name: str) -> list[str]:
        """按案名查询 OA 案件 GUID 列表（project_name）。"""
        return await self._lookup_with_retry(field=_SEARCH_CASE_NAME_FIELD, keyword=case_name)

    async def lookup_case_guids_by_customer_name(self, customer_name: str) -> list[str]:
        """按客户名称查询 OA 案件 GUID 列表（project_cust_name）。"""
        return await self._lookup_with_retry(field=_SEARCH_CUST_NAME_FIELD, keyword=customer_name)

    async def _lookup_with_retry(self, *, field: str, keyword: str) -> list[str]:
        """按过滤字段查询 GUID（只读；仅当前账号可见的案件）。

        会话：缓存 cookies 打底 + 单 client 顺序自愈（门户一键恢复 →
        网关回调 → 应用层账密登录，见模块 docstring）。会话中途失效整体重试一次。
        """
        value = str(keyword or "").strip()
        if not value:
            return []

        try:
            return await self._lookup_via_session(cookies=cached_cookies(self._auth), field=field, keyword=value)
        except _SessionExpiredError:
            logger.info("OA 会话中途失效，重建会话后重试查 GUID: field=%s keyword=%s", field, value)
            return await self._lookup_via_session(cookies=cached_cookies(self._auth), field=field, keyword=value)

    async def _lookup_via_session(self, *, cookies: dict[str, str] | None, field: str, keyword: str) -> list[str]:
        """单次完整流程：建立会话 → 取 VIEWSTATE → POST 搜索 → 提取 GUID。"""
        async with self._build_client(cookies=cookies) as client:
            list_resp = await self._ensure_list_session(client)

            viewstate = extract_viewstate_fields(list_resp.text)
            if _VIEWSTATE_FIELD not in viewstate:
                raise RuntimeError("OA 案件列表页缺少 __VIEWSTATE，无法执行案号查询（请确认已登录 OA）")

            payload = {
                _VIEWSTATE_FIELD: viewstate[_VIEWSTATE_FIELD],
                _VIEWSTATE_GENERATOR_FIELD: viewstate.get(_VIEWSTATE_GENERATOR_FIELD, ""),
                _CURRENT_PAGE_FIELD: "1",
                field: keyword,
            }
            search_resp = await client.post(_CASE_LIST_URL, data=payload)
            search_resp.raise_for_status()
            if is_oa_login_page(search_resp.url, search_resp.text):
                raise _SessionExpiredError("OA 会话无效（搜索结果跳转登录）")

            guids = extract_case_guids(search_resp.text, keyword)
            logger.info("案号查 GUID 完成: field=%s keyword=%s hits=%d", field, keyword, len(guids))
            return guids

    async def _ensure_list_session(self, client: httpx.AsyncClient) -> httpx.Response:
        """在单 client 内顺序自愈，直到拿到带 VIEWSTATE 的列表页。

        轮次行为（每轮一个 GET）：
        - 响应即列表页（有 VIEWSTATE）→ 返回；
        - 停在飞连 SSO 门户登录页（access.jtn.com/login）→ 本机飞连客户端
          一键登录恢复门户会话（至多一次），恢复失败抛友好错误；
        - 落在网关回调（corplink/agw，body 为 JS 回跳页）→ 下一轮：回调
          已 Set-Cookie 网关会话，即被放行到应用层；
        - 落在 OA 应用层登录页（member/login.aspx）→ 提取 CSRFToken POST
          账密登录（每轮至多一次），登录成功响应通常直接就是回跳后的列表页；
        - 其他无 VIEWSTATE 形态 → 抛错（不能确定会话状态，宁可报错）。

        前置清理：缓存里可能带着已被网关侧失效的 corplink_at/it（域名串
        与回调新下发的不同，httpx jar 同名共存），请求时旧值在前会被网关
        永远拒绝——先清掉，让网关授权链以干净状态重发。
        """
        _strip_stale_gateway_cookies(client)
        logged_in = False
        portal_recovered = False
        for round_index in range(_MAX_SESSION_ROUNDS):
            if round_index:
                # 网关回调/登录跳转之间留出间隙，降低连续授权被网关侧限流的概率
                await asyncio.sleep(_SESSION_ROUND_GAP_SECONDS)
            resp = await client.get(_CASE_LIST_URL)
            resp.raise_for_status()

            if _VIEWSTATE_FIELD in extract_viewstate_fields(resp.text):
                return resp

            if _is_sso_portal_login_page(resp.url):
                if portal_recovered:
                    break
                portal_recovered = True
                await self._recover_sso_via_local_client(client)
                logger.info("案号查 GUID 会话自愈: 飞连门户一键登录恢复完成")
                continue

            if is_sso_gateway_url(resp.url):
                logger.info("案号查 GUID 会话自愈: 网关层未放行（%s），吃回调 Set-Cookie 后重试", str(resp.url)[:60])
                continue

            if is_login_url(resp.url):
                if logged_in:
                    raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")
                logged_in = True
                resp = await self._login_via_form(client, resp)
                if _VIEWSTATE_FIELD in extract_viewstate_fields(resp.text):
                    return resp
                continue

            if has_login_error_text(resp.text):
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")

        raise _SessionExpiredError("OA 会话无法建立（网关/登录页循环），请稍后重试或先在浏览器完成一次 OA 登录")

    async def _recover_sso_via_local_client(self, client: httpx.AsyncClient) -> None:
        """飞连 SSO 门户会话恢复：本机客户端一次性 token → 门户 /api/quick-login。

        恢复的是**网关层**通行（一键登录身份=本机飞连客户端当前登录用户）；
        OA 应用层身份仍由 _login_via_form 按凭证登录。门户端点本身不可达或
        兑换失败时抛错（等外层整体重试一次后转友好错误）。
        """
        _drop_flat_cookies(client, _PORTAL_SESSION_COOKIE_NAMES)
        token = await _fetch_local_quick_login_token()
        if token is None:
            raise RuntimeError(
                "OA 会话已过期，且本机飞连客户端不可用（无法一键登录恢复）；"
                "请确认飞连客户端已启动并登录后重试，或在浏览器完成一次 OA 登录"
            )
        resp = await client.post(
            _SSO_QUICK_LOGIN_URL,
            headers={
                "csrf-token": _portal_csrf_token(client),
                "admin-csrf-token": "",
                "Referer": _LOCAL_QUICK_LOGIN_ORIGIN + "/",
            },
            json={"token": token, "login_scene": _SSO_QUICK_LOGIN_SCENE},
        )
        resp.raise_for_status()
        try:
            code = int(resp.json().get("code", -1))
        except (ValueError, TypeError):
            code = -1
        if code != 0:
            raise RuntimeError(f"飞连门户一键登录恢复失败（code={code}），请稍后重试或在浏览器完成一次 OA 登录")

    async def _login_via_form(self, client: httpx.AsyncClient, login_resp: httpx.Response) -> httpx.Response:
        """在 OA 应用层登录页提取 CSRFToken 并 POST 账密（rurl 参数使登录后 302 回原页）。"""
        csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', login_resp.text)
        resp = await client.post(
            str(login_resp.url),
            data={
                "CSRFToken": csrf_match.group(1) if csrf_match else "",
                "userid": self._account,
                "password": self._password,
            },
        )
        resp.raise_for_status()
        if is_sso_gateway_url(resp.url):
            raise RuntimeError(
                "OA 登录被 SSO 网关拦截（access.jtn.com），HTTP 账密登录不可用；"
                "请先在浏览器完成一次 OA 登录刷新会话后重试"
            )
        if is_login_url(resp.url) and has_login_error_text(resp.text):
            raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")
        logger.info("案号查 GUID 会话自愈: 应用层登录完成，落到 %s", str(resp.url)[:60])
        return resp

    def _build_client(self, *, cookies: dict[str, str] | None) -> Any:
        """构建 httpx 客户端（实例级接缝，测试可替换 transport）。"""
        return build_client(cookies=cookies)


class _SessionExpiredError(RuntimeError):
    """OA 会话失效（登录页/占位页），触发整体重试一次。"""


# 网关资源访问 token：回调每轮重发，旧值残留（域名串与新版不同）会在 jar 里
# 同名共存并压过新值，导致网关死循环——自愈前必须清掉（授权服务的 session
# cookie 不在清理之列，它有效时授权链才能直接发 code）。
_GATEWAY_TOKEN_COOKIE_NAMES = frozenset({"corplink_at", "corplink_it"})


def _strip_stale_gateway_cookies(client: httpx.AsyncClient) -> None:
    """从 client cookie jar 清除残留的网关 token cookies（存在才清）。"""
    jar = client.cookies.jar
    for cookie in [c for c in jar if c.name in _GATEWAY_TOKEN_COOKIE_NAMES]:
        try:
            jar.clear(cookie.domain, cookie.path, cookie.name)
        except KeyError:  # pragma: no cover - jar 迭代后已被清除的竞态
            continue
