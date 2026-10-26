"""外部覆写后的文档 key 轮换（`bump_external_write`）单测。

**为什么必须有这层**：AI 划词直改把修订写回原文件是「编辑器之外」的写入，
DS 按 document.key 缓存内容、不轮换 key 的话画布永远显示旧缓存——
「AI 说已改好、编辑器却没有任何改动痕迹」的直接原因。轮换口径必须与
保存回写一致（文档级 saved_version 抬到 max+1），否则两人同开同一文档时
一人看到新内容、另一人还停在旧 key 上。
"""

from __future__ import annotations

import pytest
from django.db.models import Max

from apps.onlyoffice.models import EditorSession
from apps.onlyoffice.services.callback_service import bump_external_write, get_or_refresh_session, session_id_for_path
from apps.onlyoffice.services.signing import make_document_key
from apps.testing.factories import LawyerFactory

pytestmark = pytest.mark.django_db

# 与前端 folderFileUrl 逐字同源（encodeURIComponent 口径），任何一边漂移
# 都会派生出不同 task_id、轮换到「另一个文档」上
SOURCE = "/api/v1/contracts/393/folder-file?subpath=1-%E5%BE%8B%E5%B8%88%E8%B5%84%E6%96%99/x.docx"


def _make_session(username: str, saved_version: int = 0) -> EditorSession:
    return EditorSession.objects.create(
        task_type="contract_folder",
        task_id=session_id_for_path(SOURCE),
        user=LawyerFactory(username=username),
        source_path=SOURCE,
        version="",
        saved_version=saved_version,
    )


def _doc_max() -> int:
    agg = EditorSession.objects.filter(task_type="contract_folder", task_id=session_id_for_path(SOURCE)).aggregate(
        m=Max("saved_version")
    )
    return int(agg["m"] or 0)


class TestBumpExternalWrite:
    def test_bumps_all_sessions_of_same_doc(self) -> None:
        """两名律师同开同一文档：一次外部覆写把两人的会话都抬到 max+1。"""
        _make_session("bump_a")
        _make_session("bump_b", saved_version=2)

        assert bump_external_write(SOURCE) == 3
        assert _doc_max() == 3
        assert EditorSession.objects.filter(task_type="contract_folder", saved_version=3).count() == 2

    def test_next_signed_key_changes(self) -> None:
        """轮换后同一用户再签配置，key 必须换（DS 才会重新拉文件）。"""
        session = _make_session("bump_key")
        _, key_before = get_or_refresh_session(
            task_id=session.task_id, user=session.user, source_path=SOURCE, version="", task_type="contract_folder"
        )

        bump_external_write(SOURCE)

        _, key_after = get_or_refresh_session(
            task_id=session.task_id, user=session.user, source_path=SOURCE, version="", task_type="contract_folder"
        )
        assert key_after != key_before
        assert key_after == make_document_key(SOURCE, "", 1)

    def test_no_sessions_returns_zero(self) -> None:
        """没人打开过的文档无需轮换（下次签配置本来就会取到新内容）。"""
        assert bump_external_write("/api/v1/contracts/999/folder-file?subpath=a.docx") == 0

    def test_does_not_touch_other_docs(self) -> None:
        """同 task_id 不同业务域（review 任务可能算出同 UUID）不被误伤。"""
        session = _make_session("bump_iso")
        EditorSession.objects.create(
            task_type="contract_review",
            task_id=session.task_id,
            user=session.user,
            source_path="/api/v1/contract-review/x/download",
            version="",
            saved_version=7,
        )

        bump_external_write(SOURCE)

        review = EditorSession.objects.get(task_type="contract_review", task_id=session.task_id)
        assert review.saved_version == 7
