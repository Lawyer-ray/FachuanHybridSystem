"""金诚同达 OA 利冲检查 — 门面服务。"""

from __future__ import annotations

from apps.core.services.browser import BrowserSessionHandle

from .playwright_conflict_check import PlaywrightConflictCheckMixin


class JtnConflictCheckScript(PlaywrightConflictCheckMixin):
    """金诚同达 OA 利益冲突信息预检门面类。"""

    def __init__(self, account: str, password: str) -> None:
        from ..auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def open_page(self, keyword: str) -> BrowserSessionHandle:
        """打开利冲检查页面并搜索当事人名称，返回浏览器会话句柄（长生命周期，交给用户操作）。"""
        return await self._open_page(keyword)
