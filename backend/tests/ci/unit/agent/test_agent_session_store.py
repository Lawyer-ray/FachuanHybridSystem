"""pi 原生 session 存储与生命周期（P2-1）。

把上下文管理交还 pi 之后，有四件事必须成立（也就是本文件覆盖的四组）：

1. 同一会话的 cwd 稳定 —— `--session-id` 按 cwd 隔离，换目录就丢记忆；
2. session 文件能按 Django 会话定位；
3. 删除 Django 会话时 pi session 一并清理（否则用户以为删干净了）；
4. 目录里不落明文 MCP 凭证。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from apps.agent.pi import session_store

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 FACHUAN_AGENT_HOME 指到临时目录，避免污染真实 ~/.fachuan-agent。"""
    home = Path(str(tmp_path)) / "agent-home"
    monkeypatch.setenv(session_store.ROOT_ENV, str(home))
    return home


class TestLayout:
    def test_layout_is_stable_across_calls(self) -> None:
        """关键约束：cwd 必须稳定。临时目录方案会让 pi 认为是另一个 project。"""
        first = session_store.layout()
        second = session_store.layout()
        assert first == second
        assert first[0].name == "work"

    def test_layout_creates_three_dirs(self) -> None:
        work, config, sessions = session_store.layout()
        for path in (work, config, sessions):
            assert path.is_dir()

    def test_config_dir_is_separate_from_work(self) -> None:
        """models.json（含 API key）不该落在 cwd 里，避免被当成项目文件。"""
        work, config, _ = session_store.layout()
        assert work != config

    def test_home_permission_is_private(self, _isolated_home: Path) -> None:
        session_store.agent_home()
        mode = oct(os.stat(_isolated_home).st_mode & 0o777)
        assert mode == "0o700", f"agent 根目录权限过宽: {mode}"


class TestSessionFiles:
    def test_session_dir_is_per_session(self) -> None:
        a = session_store.session_dir_for("11111111-1111-1111-1111-111111111111")
        b = session_store.session_dir_for("22222222-2222-2222-2222-222222222222")
        assert a != b
        assert a.is_dir() and b.is_dir()

    def test_has_session_false_before_any_file(self) -> None:
        sid = "33333333-3333-3333-3333-333333333333"
        assert session_store.has_session(sid) is False

    def test_has_session_true_after_file(self) -> None:
        sid = "44444444-4444-4444-4444-444444444444"
        directory = session_store.session_dir_for(sid)
        (directory / "2026-01-01T00-00-00-000Z_x.jsonl").write_text("{}\n", encoding="utf-8")
        assert session_store.has_session(sid) is True
        assert len(session_store.session_files(sid)) == 1

    def test_delete_session_removes_files(self) -> None:
        sid = "55555555-5555-5555-5555-555555555555"
        directory = session_store.session_dir_for(sid)
        (directory / "a.jsonl").write_text("{}\n", encoding="utf-8")
        (directory / "b.jsonl").write_text("{}\n", encoding="utf-8")

        removed = session_store.delete_session(sid)
        assert removed == 2
        assert not directory.exists()
        assert session_store.has_session(sid) is False

    def test_delete_missing_session_is_noop(self) -> None:
        assert session_store.delete_session("66666666-6666-6666-6666-666666666666") == 0

    def test_purge_orphans_keeps_valid(self) -> None:
        keep = "77777777-7777-7777-7777-777777777777"
        drop = "88888888-8888-8888-8888-888888888888"
        for sid in (keep, drop):
            (session_store.session_dir_for(sid) / "x.jsonl").write_text("{}\n", encoding="utf-8")

        removed = session_store.purge_orphans({keep})
        assert removed == 1
        assert session_store.has_session(keep) is True
        assert session_store.has_session(drop) is False


class TestNoCredentialOnDisk:
    def test_session_dir_writes_no_secrets(self) -> None:
        """回归：session 目录里不能出现明文 token / API key。"""
        sid = "99999999-9999-9999-9999-999999999999"
        directory = session_store.session_dir_for(sid)
        (directory / "s.jsonl").write_text(json.dumps({"type": "session"}) + "\n", encoding="utf-8")

        leaked = []
        for path in directory.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                for marker in ("Bearer ", "sk-", "FACHUAN_USER_TOKEN", "apiKey"):
                    if marker in text:
                        leaked.append((path.name, marker))
        assert not leaked, f"session 目录出现疑似凭证: {leaked}"


class TestDjangoSessionAlignment:
    """跨层对齐：删会话要连 pi 上下文一起删，越权者不能删。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_delete_session_removes_pi_context(self) -> None:
        from asgiref.sync import sync_to_async

        from apps.agent.models import AgentSession as Model
        from apps.agent.services.session_service import delete_session
        from apps.organization.models import LawFirm, Lawyer

        def _mk_user() -> Any:
            firm = LawFirm.objects.create(name="session-store-del-律所")
            return Lawyer.objects.create_user(username="ss-del", password=TEST_PASSWORD, law_firm=firm)

        owner = await sync_to_async(_mk_user)()
        session = await Model.objects.acreate(title="待删", user=owner)
        sid = str(session.session_id)
        directory = session_store.session_dir_for(sid)
        (directory / "s.jsonl").write_text("{}\n", encoding="utf-8")

        deleted = await delete_session(session_id=sid, user_id=owner.pk)
        assert deleted == 1
        assert not session_store.has_session(sid), "删了 Django 会话但 pi 上下文还在"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_cross_user_delete_does_not_touch_pi_context(self) -> None:
        """越权删除必须什么都不做——尤其不能清掉别人会话的模型上下文。"""
        from asgiref.sync import sync_to_async

        from apps.agent.models import AgentSession as Model
        from apps.agent.services.session_service import delete_session
        from apps.organization.models import LawFirm, Lawyer

        def _mk_user() -> Any:
            firm = LawFirm.objects.create(name="session-store-律所")
            return Lawyer.objects.create_user(username="ss-owner", password=TEST_PASSWORD, law_firm=firm)

        from asgiref.sync import sync_to_async as _s2a

        owner = await _s2a(_mk_user)()
        session = await Model.objects.acreate(title="别人的", user=owner)
        sid = str(session.session_id)
        (session_store.session_dir_for(sid) / "s.jsonl").write_text("{}\n", encoding="utf-8")

        # 用 None（未登录视角）尝试删除
        deleted = await delete_session(session_id=sid, user_id=None)
        assert deleted == 0
        assert session_store.has_session(sid) is True, "越权删除清掉了他人 pi 上下文"
