"""金诚同达 OA 案号查 GUID —— 方法一：案件管理页搜索，纯 HTTP。

依据《案号查GUID方法文档.md》（授权 JCWD-GZ-2026-033 5.8 读取复制条款，只读）：

① GET  案件管理列表页，提取 __VIEWSTATE / __VIEWSTATEGENERATOR（每次现取，勿缓存）
② POST 同 URL：project_no=<案号> + currentPage=1（子串包含匹配）
③ 从结果 HTML 提取行内 projectView 链接的 keyid=<GUID>

无浏览器、无 Playwright 兜底（区别于 case_import 的 HTTP+Playwright 双链路）。
覆盖范围仅当前 OA 账号可见的案件；0 命中是合法结果（案件不存在或账号不可见）。

会话建立（单 client 顺序自愈，实测 2026-10-06）：
ims.jtn.com 前置飞连/SSO 网关，缓存 cookies 失效时页面请求会被弹到
corplink/agw/callback（该回调响应会 Set-Cookie 下发新网关会话
corplink_at/it），网关放行后再弹到 OA 应用层 member/login.aspx——
在同一 httpx client 内吃下回调 Set-Cookie 后执行账密 POST 登录即可
建立完整会话。因此不能像旧实现那样「新建 client 单独登录」（会被
弹到 access.jtn.com SSO 门户而假成功/误报缺 VIEWSTATE）。
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
    _SEARCH_CASE_NO_FIELD,
    _VIEWSTATE_FIELD,
    _VIEWSTATE_GENERATOR_FIELD,
)

logger = logging.getLogger("apps.oa_filing.jtn_case_guid")

# 会话建立的最大 GET 轮数：网关回调（吃 Set-Cookie）→ 应用层登录 → 各一轮，留一轮余量
_MAX_SESSION_ROUNDS = 4
_SESSION_ROUND_GAP_SECONDS = 0.3


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


def extract_case_guids(html_text: str, case_no: str) -> list[str]:
    """从搜索结果 HTML 提取命中案件的 GUID（按出现顺序去重）。

    主路径按行解析：结果行文本包含案号且行内有 projectView.aspx?keyid= 链接；
    仅当 lxml 解析失败时回退文档同款整页正则。行解析成功但 0 命中视为真 0 命中
    （服务端已按案号过滤，不再整页捞回，避免误提页面其他区域的 keyid）。
    传完整案号通常唯一命中，部分案号可得多候选。
    """
    guid_index: dict[str, None] = {}
    try:
        root = lxml_html.fromstring(html_text)
    except Exception:
        logger.debug("lxml 解析搜索结果失败，回退整页正则: %s", case_no, exc_info=True)
        return list(dict.fromkeys(guid.lower() for guid in _KEYID_REGEX.findall(html_text)))

    for row in root.xpath("//tr"):
        if case_no not in "".join(row.itertext()):
            continue
        for link in row.xpath('.//a[contains(@href, "projectView.aspx") and contains(@href, "keyid=")]'):
            href = str(link.get("href") or "")
            for guid in _KEYID_REGEX.findall(href):
                guid_index.setdefault(guid.lower(), None)
    return list(guid_index)


class JtnCaseGuidScript:
    """金诚同达 OA 案号查 GUID 门面（纯 HTTP，方法一）。"""

    def __init__(self, account: str, password: str) -> None:
        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def lookup_case_guids(self, case_no: str) -> list[str]:
        """按案号查询 OA 案件 GUID 列表（只读；仅当前账号可见的案件）。

        会话：缓存 cookies 打底 + 单 client 顺序自愈（网关回调 Set-Cookie
        → 应用层账密登录，见模块 docstring）。会话中途失效整体重试一次。
        """
        keyword = str(case_no or "").strip()
        if not keyword:
            return []

        try:
            return await self._lookup_via_session(cookies=cached_cookies(self._auth), case_no=keyword)
        except _SessionExpiredError:
            logger.info("OA 会话中途失效，重建会话后重试案号查 GUID: %s", keyword)
            return await self._lookup_via_session(cookies=cached_cookies(self._auth), case_no=keyword)

    async def _lookup_via_session(self, *, cookies: dict[str, str] | None, case_no: str) -> list[str]:
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
                _SEARCH_CASE_NO_FIELD: case_no,
            }
            search_resp = await client.post(_CASE_LIST_URL, data=payload)
            search_resp.raise_for_status()
            if is_oa_login_page(search_resp.url, search_resp.text):
                raise _SessionExpiredError("OA 会话无效（搜索结果跳转登录）")

            guids = extract_case_guids(search_resp.text, case_no)
            logger.info("案号查 GUID 完成: case_no=%s hits=%d", case_no, len(guids))
            return guids

    async def _ensure_list_session(self, client: httpx.AsyncClient) -> httpx.Response:
        """在单 client 内顺序自愈，直到拿到带 VIEWSTATE 的列表页。

        轮次行为（每轮一个 GET）：
        - 响应即列表页（有 VIEWSTATE）→ 返回；
        - 落在 OA 应用层登录页（member/login.aspx，rurl 指向列表页）→
          提取 CSRFToken POST 账密登录（每轮至多一次），登录成功响应通常
          直接就是 302 回跳后的列表页；
        - 落在 SSO 门户 / 网关回调（access.jtn.com、corplink/agw）→ 继续
          下一轮：回调响应会 Set-Cookie 下发网关会话，下一轮即被放行到
          应用层登录页；
        - 其他无 VIEWSTATE 形态 → 抛错（不能确定会话状态，宁可报错）。
        """
        logged_in = False
        for round_index in range(_MAX_SESSION_ROUNDS):
            if round_index:
                # 网关回调/登录跳转之间留出间隙，降低连续授权被网关侧限流的概率
                await asyncio.sleep(_SESSION_ROUND_GAP_SECONDS)
            resp = await client.get(_CASE_LIST_URL)
            resp.raise_for_status()

            if _VIEWSTATE_FIELD in extract_viewstate_fields(resp.text):
                return resp

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
