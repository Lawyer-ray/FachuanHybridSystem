"""JTN OA 盖章申请 — 门面服务。"""

from __future__ import annotations

from .playwright_stamp import PlaywrightStampMixin
from .stamp_models import StampFormData


class JtnStampScript(PlaywrightStampMixin):
    """金诚同达 OA 盖章申请门面类。"""

    def __init__(self, account: str, password: str) -> None:
        from ..auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def run(self, form_data: StampFormData) -> None:
        """执行盖章申请全流程。"""
        await self._run_stamp_application(form_data)
