"""AI 就地落修订之后，律师在同一画布上的保存**不得**被静默丢弃。

## 这条 bug 为什么必须整链测

单独看每一步都是「对的」，叠起来才是数据事故：

| 步骤 | 代码 | 单独看合理吗 |
|---|---|---|
| 1 | 打开文档 → `canvas_seq = N` | ✔ 登记「这份画布按第几代签发」 |
| 2 | AI 直改落盘 → `bump_external_write()` → `external_write_seq = N+1`（**故意不动 canvas_seq**） | ✔ 不然守门人恒假（`models.py` 的注释记过这次踩坑） |
| 3 | 插件桥把修订**就地**落进画布 → 前端**不重载**（免 5–15 秒白屏，产品明确要的体验） | ✔ 免重载是体验关键 |
| 4 | 律师继续手改 → forcesave → `handle_save_callback` → `stale_canvas_reason()` 命中 → **丢弃**，且为不让 DS 无限重试仍应答 `error:0` | ✔ 弃旧画布是对的；`error:0` 也是对的 |

于是第 4 步之后：**律师看到「已保存」，内容和永久丢失**。
第 3 步结束时画布其实已经和磁盘一致了，只是没人把这个事实告诉后端。

## 修法与本文的守则

- 插件回执 `ok` 后，前端调 `ack_canvas_synced()` 把 `canvas_seq` **单向上对齐**
  到文档级外写代次；
- 丢弃必须留下 `last_save_dropped_at`，让前端能把它说出来（`canvas_state_for`）。

因此本文件一律走**生产路径**：真实签发 → 真实 `bump_external_write` →
`load_session_by_key()`（DS 回调就是这么拿会话的）→ `handle_save_callback`
真实落盘；只把「哪个目录」换成临时目录，不替换任何行为。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import get_user_model

from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.onlyoffice.models import EditorSession
from apps.onlyoffice.services import callback_service
from apps.onlyoffice.services.callback_service import (
    ack_canvas_synced,
    bump_external_write,
    canvas_state_for,
    get_or_refresh_session,
    load_session_by_key,
    session_id_for_path,
)

CONTRACT_ID = 377
SOURCE_SUBPATH = "1-合同/a.docx"
# 与前端 folderFileUrl 口径一致（subpath 里只有一个字符，编码后仍是它自己）
SOURCE_PATH = f"/api/v1/contracts/{CONTRACT_ID}/folder-file?subpath={SOURCE_SUBPATH}"
TASK_TYPE = "contract_folder"
ORIGINAL = b"original-content"
AI_REWRITTEN = b"ai-rewritten-content"
LAWYER_EDITED = b"lawyer-edited-content"


class _Service(BoundFolderBrowseService):
    """最小可用实现：绑定临时目录、无 ACL（权限口径由 API 层用例覆盖）。"""

    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


@pytest.fixture
def folder_root(tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    (d / "a.docx").write_bytes(ORIGINAL)
    return tmp_path


@pytest.fixture
def wired(monkeypatch: Any, folder_root: Path) -> Path:
    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(folder_root))
    return folder_root


@pytest.fixture
def user(db: Any) -> Any:
    return get_user_model().objects.create_user(username="lawyer-canvas-ack", password="x")


def _open(user: Any, version: str = "v1") -> str:
    """走真实签发路径开一份文档，返回 document key。"""
    _, key = get_or_refresh_session(
        task_id=session_id_for_path(SOURCE_PATH),
        user=user,
        source_path=SOURCE_PATH,
        version=version,
        task_type=TASK_TYPE,
    )
    return key


def _load(key: str) -> EditorSession:
    session = load_session_by_key(key)
    assert session is not None
    return session


def _session_for(user: Any) -> EditorSession:
    """按用户取会话行。

    **多人场景不能用 `load_session_by_key`**：同一文档同版本对所有用户算出
    **同一个 document key**（DS 实时协同的前提），按 key 查只会拿到最近更新的
    那一行（很可能是别人的）。要断言「某人的画布」就必须按 user 取。
    """
    session = (
        EditorSession.objects.filter(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        .order_by("-updated_at")
        .first()
    )
    assert session is not None
    return session


def _run_callback(monkeypatch: Any, key: str, data: bytes) -> bool:
    """跑一遍 DS 保存回调（只打桩「下载」这一步，其余全走生产代码）。"""
    monkeypatch.setattr(callback_service, "_download_edited_docx", lambda _url: data)
    return callback_service.handle_save_callback(_load(key), "http://ds/cache/edited", status=6)


def _disk(folder_root: Path) -> bytes:
    return (folder_root / "1-合同" / "a.docx").read_bytes()


def _ai_live_apply(user: Any) -> None:
    """模拟「AI 直改落盘 + 插件就地落笔成功」：磁盘变了、画布也变了。"""
    (user,)  # 只有签名一致性的作用，无额外语义
    bump_external_write(SOURCE_PATH, task_type=TASK_TYPE)


class TestSilentDropReproduction:
    """修复前的行为，用测试钉住它不会再回来。"""

    def test_without_ack_lawyer_save_is_dropped(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """复现：就地落笔后不 ack，律师的保存被丢弃，且文件**一个字节都没变**。"""
        key = _open(user)
        _ai_live_apply(user)

        # 回调应答 True（不让 DS 重试），但内容没有落盘——这就是「静默」
        assert _run_callback(monkeypatch, key, LAWYER_EDITED) is True
        assert _disk(wired) == ORIGINAL
        assert LAWYER_EDITED not in _disk(wired)

    def test_dropped_save_leaves_a_marker(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """丢弃必须留痕：没有这个时间戳，前端无法把它说出来。"""
        key = _open(user)
        _ai_live_apply(user)

        assert _load(key).last_save_dropped_at is None
        _run_callback(monkeypatch, key, LAWYER_EDITED)
        assert _load(key).last_save_dropped_at is not None

    def test_marker_is_cleared_after_a_real_save(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """真正的保存成功后标记要清掉（它不是一次性信号，不该永远留着）。"""
        key = _open(user)
        _ai_live_apply(user)
        _run_callback(monkeypatch, key, LAWYER_EDITED)  # 被丢弃，留下标记
        assert ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH) is True
        assert _load(key).last_save_dropped_at is None


class TestAckRestoresSaving:
    """修复后的行为：画布已同步 → 律师的保存必须真的落盘。"""

    def test_ack_makes_lawyer_save_land(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        """核心回归：就地落笔成功并 ack 之后，保存必须写进文件。"""
        key = _open(user)
        _ai_live_apply(user)
        # 插件回执 ok → 前端登记「画布已同步」
        assert ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH) is True

        assert _run_callback(monkeypatch, key, LAWYER_EDITED) is True
        assert _disk(wired) == LAWYER_EDITED

    def test_ack_aligns_canvas_seq_to_document_seq(self, wired: Path, user: Any) -> None:
        """对齐是**单向**的：canvas_seq 追到文档级外写代次，之后自己不再涨。"""
        key = _open(user)
        _ai_live_apply(user)
        before = _load(key)
        assert before.canvas_seq < before.external_write_seq  # 这就是被拦的原因

        ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        after = _load(key)
        assert after.canvas_seq == after.external_write_seq
        assert callback_service.stale_canvas_reason(after) == ""

    def test_ack_does_not_rotate_document_key(self, wired: Path, user: Any) -> None:
        """ack 只是登记事实，不能顺手换 key——换了等于把画布拽去重载，白费免重载。"""
        key = _open(user)
        _ai_live_apply(user)
        ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert _load(key).document_key == key

    def test_new_external_write_makes_canvas_stale_again(self, wired: Path, user: Any) -> None:
        """守门人不能被 ack 拆掉：再来一次 AI 外写，画布必须重新判过期。"""
        key = _open(user)
        _ai_live_apply(user)
        ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert callback_service.stale_canvas_reason(_load(key)) == ""

        _ai_live_apply(user)  # 第二次 AI 外写
        assert callback_service.stale_canvas_reason(_load(key)) != ""


class TestAckBoundaries:
    def test_ack_without_session_returns_false(self, db: Any, user: Any) -> None:
        """从来没打开过文档：ack 无从登记，如实返回 False（前端据此降级重载）。"""
        assert ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH) is False

    def test_ack_is_idempotent(self, wired: Path, user: Any) -> None:
        """连点两次不该报错、也不该把代次推错。"""
        _open(user)
        _ai_live_apply(user)
        assert ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH) is True
        first = _session_for(user).canvas_seq
        assert ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH) is True
        assert _session_for(user).canvas_seq == first

    def test_ack_only_touches_the_caller_session(self, wired: Path, user: Any, db: Any) -> None:
        """两人同开同一份：A 的画布同步不该改 B 的画布代次。

        B 的画布确实可能还是旧的（他没拿到那次 AI 修订），替他对齐会让他
        用旧画布覆盖掉 A/AI 写的内容。
        """
        _open(user)
        other = get_user_model().objects.create_user(username="lawyer-canvas-ack-b", password="x")
        _open(other)
        _ai_live_apply(user)

        ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)

        assert callback_service.stale_canvas_reason(_session_for(user)) == ""
        # B 确实没拿到那次 AI 修订，替他对齐会让他用旧画布覆盖掉 AI 写的内容
        assert callback_service.stale_canvas_reason(_session_for(other)) != ""


class TestSaveBackSnapshots:
    """编辑器保存回写也要先留底。

    AI 落笔与编辑器保存是仅有的两条能静默毁掉内容的写路径；只给前者做快照，
    律师手滑全选删掉再保存一次就没救了。
    """

    def test_save_back_snapshots_previous_content(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        from apps.doc_workspace.services import snapshot_service

        key = _open(user)
        assert _run_callback(monkeypatch, key, LAWYER_EDITED) is True

        snap = snapshot_service.latest(kind="contract", owner_id=CONTRACT_ID, subpath=SOURCE_SUBPATH)
        assert snap is not None
        assert snapshot_service.read_bytes(snap) == ORIGINAL
        assert snap.reason == "editor_save"
        assert _disk(wired) == LAWYER_EDITED


class TestCanvasState:
    def test_no_session_reports_not_stale(self, db: Any, user: Any) -> None:
        state = canvas_state_for(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert state.stale is False
        assert state.reason == ""
        assert state.dropped_at is None

    def test_stale_is_reported_with_actionable_reason(self, wired: Path, user: Any) -> None:
        _open(user)
        _ai_live_apply(user)
        state = canvas_state_for(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert state.stale is True
        # 前端会把这句直接展示给律师，必须给出可操作指引
        assert "重新打开" in state.reason or "重开" in state.reason

    def test_dropped_at_is_reported_until_acked(self, wired: Path, user: Any, monkeypatch: Any) -> None:
        key = _open(user)
        _ai_live_apply(user)
        _run_callback(monkeypatch, key, LAWYER_EDITED)

        state = canvas_state_for(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert state.dropped_at is not None

        ack_canvas_synced(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert canvas_state_for(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH).dropped_at is None

    def test_healthy_canvas_reports_not_stale(self, wired: Path, user: Any) -> None:
        _open(user)
        state = canvas_state_for(task_type=TASK_TYPE, user=user, source_path=SOURCE_PATH)
        assert state.stale is False
        assert state.dropped_at is None
