"""JTN OA 归档材料提交 — 门面服务。"""

from __future__ import annotations

from .archive_models import ArchiveFormData
from .playwright_archive import PlaywrightArchiveMixin


class JtnArchiveScript(PlaywrightArchiveMixin):
    """金诚同达 OA 归档材料提交门面类。"""

    def __init__(self, account: str, password: str) -> None:
        from ..auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    async def run(self, form_data: ArchiveFormData) -> None:
        """执行归档材料提交全流程。"""
        await self._run_archive_submission(form_data)
