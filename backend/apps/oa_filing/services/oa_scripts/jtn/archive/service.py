"""JTN OA 归档材料提交 — 门面服务。"""

from __future__ import annotations

from apps.core.services.browser import BrowserSessionHandle

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

    async def open_page(
        self,
        oa_case_number: str,
        description: str = "详见卷宗",
        file_paths: list[str] | None = None,
        project_id: str | None = None,
    ) -> BrowserSessionHandle:
        """打开归档页面并填写，返回浏览器会话句柄（长生命周期，交给用户操作）。

        project_id（律所ID/GUID）非空时直达带 keyid 的归档申请页（跳过弹窗
        查案件，填充逻辑不变）；否则按 oa_case_number 弹窗搜索（备用方案）。
        """
        return await self._open_page(oa_case_number, description, file_paths or [], project_id=project_id)
