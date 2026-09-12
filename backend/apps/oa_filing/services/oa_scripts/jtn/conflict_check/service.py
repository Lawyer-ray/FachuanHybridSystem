"""金诚同达 OA 利冲检查 — 门面服务。"""

from __future__ import annotations

from .playwright_conflict_check import PlaywrightConflictCheckMixin


class JtnConflictCheckScript(PlaywrightConflictCheckMixin):
    """金诚同达 OA 利益冲突信息预检门面类。"""

    def __init__(self, account: str, password: str) -> None:
        from ..auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def open_page(self, keyword: str) -> tuple:
        """打开利冲检查页面并搜索当事人名称，返回 (playwright, browser)。"""
        return await self._open_page(keyword)
