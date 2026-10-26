"""过期画布不得覆盖外部写入（AI 直改）——数据丢失防线。

**真机血泪**：AI 划词直改走后端直接改 docx 落盘，而编辑器画布还停在旧内容。
律师随后关闭编辑器（DS status=2）或点保存（status=6），DS 交回的是**编辑器
内存里的旧画布**——`_adopt_edited` 用 `expect_mtime=None` 直接覆写，AI 刚落的
`w:ins`/`w:del` 被整篇静默盖掉。用户看到的现象就是：

    AI 说「已改好，可在审阅里看到修订」
    → 关掉编辑器再打开，又变回旧文

## 这些用例为什么必须走「生产路径」

上一版守卫被写成「文档级 max 代次 vs 会话自己的 external_write_seq」，而
`bump_external_write` 恰好在**同一行**上把后者一起抬了，于是判据恒为
`doc_seq <= 自身值` → 恒假。单测当时只拿**未刷新的内存对象**去比，所以一直
是绿的，而线上守卫是死代码。

因此本文件**一律通过 `load_session_by_key()` 取会话**（DS 回调就是这么拿的），
并对关键路径额外断言 `refresh_from_db()` 后的结果——只有两条路径都判过期，
守卫才算真的生效。
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
    load_session_by_key,
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


def _load(key: str) -> EditorSession:
    """按 DS 回调的方式取会话（**生产路径**，不是内存里那个旧对象）。"""
    session = load_session_by_key(key)
    assert session is not None
    return session


class TestStaleCanvasGuard:
    def test_fresh_session_is_not_stale(self, user: Any) -> None:
        _, key = _open(user)
        assert stale_canvas_reason(_load(key)) == ""

    def test_external_write_makes_canvas_stale_on_production_path(self, user: Any) -> None:
        """核心回归：DS 回调按 key 重新 load 后，判据**必须**命中。

        这正是上一版失效的地方——bump 把 external_write_seq 抬到同一行，
        拿它跟「文档级 max」比就永远相等，守卫变死代码。
        """
        _, key = _open(user)
        bumped = bump_external_write(SOURCE, task_type="contract_folder")
        assert bumped > 0
        assert stale_canvas_reason(_load(key)) != ""

    def test_stale_after_refresh_from_db(self, user: Any) -> None:
        """从库里刷新出来也必须判过期（防止再退回「只认内存对象」）。"""
        session, _ = _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        session.refresh_from_db()
        assert stale_canvas_reason(session) != ""

    def test_counter_advances_but_canvas_snapshot_does_not(self, user: Any) -> None:
        """两个字段职责必须分离：计数器涨、画布快照不涨。

        它们一旦一起涨，判据就恒假。这条断言直接锁住数据模型语义。
        """
        _, key = _open(user)
        before = _load(key)
        bump_external_write(SOURCE, task_type="contract_folder")
        after = _load(key)
        assert after.external_write_seq > before.external_write_seq
        assert after.canvas_seq == before.canvas_seq

    def test_reason_mentions_reopen(self, user: Any) -> None:
        """文案要给出可操作指引：光说「失败」律师不知道下一步做什么。"""
        _, key = _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        reason = stale_canvas_reason(_load(key))
        assert "重新打开" in reason or "重开" in reason

    def test_reopening_clears_stale(self, user: Any) -> None:
        """重新签发 key（浏览器重拉磁盘内容）后，那扇新画布必须可保存。"""
        _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        # 版本身份变了 → 新 key → 新画布快照对齐文档级
        _, key2 = _open(user, version="v2")
        assert stale_canvas_reason(_load(key2)) == ""

    def test_old_key_after_reopen_cannot_resolve(self, user: Any) -> None:
        """重开之后，**老 key 直接解析不到会话**——回调会 fail-closed 回 error 1。

        为什么不是「仍判 stale」：`get_or_refresh_session` 会把该行（每用户一条）
        的 document_key 改写成新 key（官方要求：保存/外部写后必须换 key，
        否则 DS 继续用旧缓存）。于是老 key 在库里已不存在，
        `load_session_by_key` 返回 None，`document_callback` 命中
        `session is None` 分支直接 `{"error": 1}`——**旧画布同样无法落地**，
        只是拦在比 stale 判据更早的一道。两道叠加才是完整防线。
        """
        _, key1 = _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        _, key2 = _open(user, version="v2")
        assert key1 != key2
        # 老 key 已无从解析，回调必然拒绝（fail-closed，不会误落盘）
        assert load_session_by_key(key1) is None
        # 新 key 可正常保存
        assert stale_canvas_reason(_load(key2)) == ""

    def test_multiple_external_writes_accumulate(self, user: Any) -> None:
        _open(user)
        bump_external_write(SOURCE, task_type="contract_folder")
        bump_external_write(SOURCE, task_type="contract_folder")
        session = EditorSession.objects.get(task_type="contract_folder", task_id=session_id_for_path(SOURCE))
        assert int(session.external_write_seq) >= 2

    def test_other_document_unaffected(self, user: Any) -> None:
        """代次是文档级的：别的文件被 AI 改，不应把这份判成过期。"""
        _, key = _open(user)
        bump_external_write("/api/v1/contracts/999/folder-file?subpath=other.docx", task_type="contract_folder")
        assert stale_canvas_reason(_load(key)) == ""

    def test_no_session_means_no_rotation(self, user: Any) -> None:
        """没人开过这份文档：外部写入无需轮换（返回 0），下次打开自然取新内容。"""
        assert bump_external_write("/api/v1/contracts/1/folder-file?subpath=never.docx") == 0
