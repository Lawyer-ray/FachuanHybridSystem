"""金诚同达 OA 立案脚本 —— SSO 扫码登录 + Cookie 持久化。

实际逻辑已迁移至 jtn.auth.service.JtnAuthService，
本模块保留 SsoLoginMixin 供 JtnFilingScript 继承使用。
"""

from __future__ import annotations

import logging
from typing import Any

from ..auth.service import JtnAuthService

logger = logging.getLogger("apps.oa_filing.jtn")


class SsoLoginMixin:  # pragma: no cover
    """SSO 扫码登录 + Cookie 管理。

    委托给 self._auth: JtnAuthService 实例（由 JtnFilingScript.__init__ 创建）。
    """

    _auth: JtnAuthService

    # ------------------------------------------------------------------
    # Cookie 持久化（委托）
    # ------------------------------------------------------------------

    @staticmethod
    def _save_cookies(cookies: list[dict[str, Any]]) -> None:  # pragma: no cover
        """保存 cookies 到磁盘。"""
        JtnAuthService.save_cookies(cookies)

    @staticmethod
    def _load_cookies() -> list[dict[str, Any]] | None:  # pragma: no cover
        """从磁盘加载 cookies，过滤已过期的。"""
        return JtnAuthService.load_cookies()

    # ------------------------------------------------------------------
    # SSO 扫码登录（委托）
    # ------------------------------------------------------------------

    async def _login_via_sso(self) -> list[dict[str, Any]]:  # pragma: no cover
        """完整的 SSO 扫码 + 凭证登录流程。"""
        return await self._auth.sso_login()

    # ------------------------------------------------------------------
    # 获取有效 cookies（委托）
    # ------------------------------------------------------------------

    async def _ensure_cookies(self) -> list[dict[str, Any]]:
        """确保有有效的 cookies，优先使用缓存。"""
        return await self._auth.ensure_cookies()
