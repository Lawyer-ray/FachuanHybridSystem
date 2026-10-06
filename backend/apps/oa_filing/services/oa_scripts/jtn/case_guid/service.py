"""金诚同达 OA 案号查 GUID —— 方法一：案件管理页搜索，纯 HTTP。

依据《案号查GUID方法文档.md》（授权 JCWD-GZ-2026-033 5.8 读取复制条款，只读）：

① GET  案件管理列表页，提取 __VIEWSTATE / __VIEWSTATEGENERATOR（每次现取，勿缓存）
② POST 同 URL：project_no=<案号> + currentPage=1（子串包含匹配）
③ 从结果 HTML 提取行内 projectView 链接的 keyid=<GUID>

无浏览器、无 Playwright 兜底（区别于 case_import 的 HTTP+Playwright 双链路）。
覆盖范围仅当前 OA 账号可见的案件；0 命中是合法结果（案件不存在或账号不可见）。
会话策略走 jtn/http_session 共享层：磁盘缓存 cookies 优先，失效回退 http_login。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from lxml import html as lxml_html

from ..auth.service import JtnAuthService
from ..http_session import build_client, cached_cookies, http_login_cookies, is_oa_login_page
from .constants import (
    _CASE_LIST_URL,
    _CURRENT_PAGE_FIELD,
    _KEYID_REGEX,
    _SEARCH_CASE_NO_FIELD,
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

        会话策略（共享层同款）：缓存 cookies 优先（SSO 扫码登录的产物，部分
        账号不支持账密 HTTP 登录）；失效则尝试 http_login 账密登录后重试。
        """
        keyword = str(case_no or "").strip()
        if not keyword:
            return []

        cached = cached_cookies(self._auth)
        if cached is not None:
            try:
                return await self._lookup_with_cookies(cookies=cached, case_no=keyword)
            except _SessionExpiredError:
                logger.info("缓存 OA 会话已失效，改走 HTTP 登录重试案号查 GUID: %s", keyword)
        return await self._lookup_after_login(keyword)

    async def _lookup_after_login(self, keyword: str) -> list[str]:
        """用 http_login 新会话执行查询；中途失效再整体重试一次。"""
        cookies = await http_login_cookies(self._auth)

        try:
            return await self._lookup_with_cookies(cookies=cookies, case_no=keyword)
        except _SessionExpiredError:
            logger.info("OA 会话中途失效，重新登录后重试案号查 GUID: %s", keyword)
            return await self._lookup_with_cookies(cookies=await self._auth.http_login(), case_no=keyword)

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

    def _build_client(self, *, cookies: dict[str, str]) -> Any:
        """构建 httpx 客户端（实例级接缝，测试可替换 transport）。"""
        return build_client(cookies=cookies)


class _SessionExpiredError(RuntimeError):
    """OA 会话失效（登录页/占位页），触发整体重试一次。"""
