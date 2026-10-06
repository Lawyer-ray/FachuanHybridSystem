"""金诚同达 OA 案号查 GUID —— 方法一：案件管理页搜索，纯 HTTP。

依据《案号查GUID方法文档.md》（授权 JCWD-GZ-2026-033 5.8 读取复制条款，只读）：

① GET  案件管理列表页，提取 __VIEWSTATE / __VIEWSTATEGENERATOR（每次现取，勿缓存）
② POST 同 URL：project_no=<案号> + currentPage=1（子串包含匹配）
③ 从结果 HTML 提取行内 projectView 链接的 keyid=<GUID>

无浏览器、无 Playwright 兜底（区别于 case_import 的 HTTP+Playwright 双链路）。
覆盖范围仅当前 OA 账号可见的案件；0 命中是合法结果（案件不存在或账号不可见）。
会话来源：JtnAuthService.http_login() 纯 HTTP 登录（client_import 同款，无需扫码）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from lxml import html as lxml_html

from ..auth.service import JtnAuthService
from .constants import (
    _CASE_LIST_URL,
    _CURRENT_PAGE_FIELD,
    _DEFAULT_HTTP_TIMEOUT,
    _KEYID_REGEX,
    _LOCATION_REPLACE_MARKER,
    _LOGIN_URL_MARKER,
    _SEARCH_CASE_NO_FIELD,
    _SESSION_PLACEHOLDER_MAX_LEN,
    _VIEWSTATE_FIELD,
    _VIEWSTATE_GENERATOR_FIELD,
)

logger = logging.getLogger("apps.oa_filing.jtn_case_guid")


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


def is_oa_login_page(url: Any, html_text: str) -> bool:
    """判断响应是否为会话失效特征（登录页或 location.replace 占位页）。"""
    if _LOGIN_URL_MARKER in str(url).lower():
        return True
    return len(html_text) < _SESSION_PLACEHOLDER_MAX_LEN and _LOCATION_REPLACE_MARKER in html_text


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

        会话策略：缓存 cookies 优先（SSO 扫码登录的产物，部分账号不支持账密
        HTTP 登录）；失效则尝试 http_login() 纯 HTTP 登录后重试。
        """
        keyword = str(case_no or "").strip()
        if not keyword:
            return []

        cached = self._cookies_from_cache()
        if cached is not None:
            try:
                return await self._lookup_with_cookies(cookies=cached, case_no=keyword)
            except _SessionExpiredError:
                logger.info("缓存 OA 会话已失效，改走 HTTP 登录重试案号查 GUID: %s", keyword)
        return await self._lookup_after_login(keyword)

    async def _lookup_after_login(self, keyword: str) -> list[str]:
        """用 http_login() 新会话执行查询；中途失效再整体重试一次。"""
        try:
            cookies = await self._auth.http_login()
        except Exception as exc:
            raise RuntimeError(
                "OA 会话无效，且该账号无法通过账密 HTTP 登录（可能仅支持扫码登录）；"
                "请先在 OA 立案/盖章等功能中完成一次登录刷新会话后重试"
            ) from exc

        try:
            return await self._lookup_with_cookies(cookies=cookies, case_no=keyword)
        except _SessionExpiredError:
            logger.info("OA 会话中途失效，重新登录后重试案号查 GUID: %s", keyword)
            return await self._lookup_with_cookies(cookies=await self._auth.http_login(), case_no=keyword)

    def _cookies_from_cache(self) -> dict[str, str] | None:
        """读取磁盘缓存 cookies（playwright 格式）并转为 name→value 扁平 dict。"""
        cached = self._auth.load_cookies()
        if not cached:
            return None
        return {str(c["name"]): str(c["value"]) for c in cached}

    async def _lookup_with_cookies(self, *, cookies: dict[str, str], case_no: str) -> list[str]:
        """单次完整流程：GET 取 VIEWSTATE → POST 搜索 → 提取 GUID。"""
        async with self._build_client(cookies=cookies) as client:
            list_resp = await client.get(_CASE_LIST_URL)
            list_resp.raise_for_status()
            if is_oa_login_page(list_resp.url, list_resp.text):
                raise _SessionExpiredError("OA 会话无效（列表页跳转登录）")

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

    def _build_client(self, *, cookies: dict[str, str]) -> httpx.AsyncClient:
        """构建 httpx 客户端（trust_env=False 防代理环境变量劫持，测试可替换 transport）。"""
        return httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            follow_redirects=True,
            timeout=_DEFAULT_HTTP_TIMEOUT,
            cookies=cookies,
            trust_env=False,
        )


class _SessionExpiredError(RuntimeError):
    """OA 会话失效（登录页/占位页），触发整体重试一次。"""
