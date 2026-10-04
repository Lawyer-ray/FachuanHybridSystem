"""金诚同达 OA 发票申请 — 门面服务。"""

from __future__ import annotations

from apps.core.services.browser import BrowserSessionHandle

from .playwright_invoice import PlaywrightInvoiceMixin


class JtnInvoiceScript(PlaywrightInvoiceMixin):
    """金诚同达 OA 发票申请门面类。"""

    def __init__(self, account: str, password: str) -> None:
        from ..auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def open_page(self, oa_case_number: str) -> BrowserSessionHandle:
        """打开发票页面并填写，返回浏览器会话句柄（长生命周期，交给用户操作）。"""
        return await self._open_page(oa_case_number)
