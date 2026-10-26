"""过期画布不得覆盖外部写入（AI 直改）——数据丢失防线。

**真机血泪**：AI 划词直改走后端直接改 docx 落盘，而编辑器画布还停在旧内容。
律师随后关闭编辑器（DS status=2）或点保存（status=6），DS 交回的是**编辑器
内存里的旧画布**——`_adopt_edited` 拿 `expect_mtime=None` 直接覆写，AI 刚落的
`w:ins`/`w:del` 被整篇静默盖掉。用户看到的现象就是：

    AI 说「已改好，可在审阅里看到修订」
    → 关掉编辑器再打开，又变回旧文

这份测试锁死三点：
1. 外部写入抬高文档级代次后，**旧代次会话**的保存被判为过期（不落盘）；
2. 重新签发 key（= 浏览器重拉磁盘内容）后，保存恢复正常；
3. 代次是**文档级**的：别的文件被 AI 改不影响这份。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from apps.onlyoffice.models import EditorSession
from apps.onlyoffice.services.callback_service import (
    bump_external_write,
    get_or_refresh_session,
    session_id_for_path,
    stale_canvas_reason,
)

SOURCE = "/api/v1/contracts/393/folder-file?subpath=a%2Fb.docx"


@pytest.fixture
def user(db: Any) -> Any:
    return get_user_model().objects.create_user(username=f"u{uuid4().hex[:8]}", password="x")


def _open(user: Any, version: str = "v1") -> tuple[EditorSession, str]:
    """走真实签发路径开一份文档（folder 域，id 从路径派生）。"""
    return get_or_refresh_session(
        task_id=session_id_for_path(SOURCE),
        user=user,
        source_path=SOURCE,
        version=version,
        task_type="contract_folder",
    )


class TestStaleCanvasGuard:
    def test_fresh_session_is_not_stale(self, user: Any) -> None:
        session, _ = _open(user)
        assert stale_canvas_reason(session) == ""

    def test_external_write_makes_canvas_stale(self, user: Any) -> None:
        session, _ = _open(user)
        # AI 直改落盘 → 后端抬代次
        bumped = bump_external_write(SOURCE, task_type="contract_folder")
        assert bumped > 0
        # 画布还用着旧 key，必须判过期
        assert stale_canvas_reason(session) != ""

    def test_reason_mentions_reopen(self, user: Any) -> None:
        """文案要给出可操作指引：光说「失败」律师不知道下一步做什么。"""
        session, _ = _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        reason = stale_canvas_reason(session)
        assert "重新打开" in reason or "重开" in reason

    def test_reopening_clears_stale(self, user: Any) -> None:
        """重新签发 key（浏览器重拉磁盘内容）后，保存必须恢复正常。"""
        _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        # 版本身份变了 → 新 key → 会话代次对齐文档级
        session2, key2 = _open(user, version="v2")
        assert session2.document_key == key2
        assert stale_canvas_reason(session2) == ""

    def test_multiple_external_writes_accumulate(self, user: Any) -> None:
        _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        bump_external_write(SOURCE, task_type="contract_folder")
        session = EditorSession.objects.get(task_type="contract_folder", task_id=session_id_for_path(SOURCE))
        assert int(session.external_write_seq) >= 2

    def test_other_document_unaffected(self, user: Any) -> None:
        """代次是文档级的：别的文件被 AI 改，不应把这份判成过期。"""
        mine, _ = _open(user)
        bump_external_write("/api/v1/contracts/999/folder-file?subpath=other.docx", task_type="contract_folder")
        assert stale_canvas_reason(mine) == ""

    def test_no_session_means_no_rotation(self, user: Any) -> None:
        """没人开过这份文档：外部写入无需轮换（返回 0），下次打开自然取新内容。"""
        assert bump_external_write("/api/v1/contracts/1/folder-file?subpath=never.docx") == 0
