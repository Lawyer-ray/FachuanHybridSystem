"""版本留底：每次覆盖之前先存一份旧内容，且回滚本身也可回滚。

## 这些断言各自守一件事

| 断言 | 不守会怎样 |
|---|---|
| 三次覆写 → seq = 1,2,3 连续 | 时间线断号 = 律师说不清「哪一版是哪一版」 |
| 同内容只占一份 blob | 反复保存同一份没改字的文件把磁盘吃满 |
| 回滚后字节 sha 与当时一致 | 「回滚成功」但内容不对，比回滚失败更糟 |
| 绑定文件夹里不长出快照文件 | 目录树变脏，且归档打包会把快照当正文材料抓走 |
| 并发覆写不撞 seq | 唯一约束抛异常 = 编辑器保存直接失败 |
| 回滚前先快照当前内容 | 点错版本就永久丢失当前稿 |
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings

from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.models import DocSnapshot, SnapshotReason
from apps.doc_workspace.services import snapshot_service, write_service

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 512
SUBPATH = "1-合同/a.docx"
V1 = b"version-one"
V2 = b"version-two"
V3 = b"version-three"


class _Service(BoundFolderBrowseService):
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
    (d / "a.docx").write_bytes(V1)
    return tmp_path


@pytest.fixture
def wired(monkeypatch: Any, folder_root: Path) -> Path:
    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(folder_root))
    return folder_root


@pytest.fixture
def media(tmp_path: Path) -> Any:
    """快照落在临时 MEDIA 下，别污染仓库的 media/。"""
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        yield tmp_path / "media"


def _capture(data: bytes, *, reason: str = SnapshotReason.EDITOR_SAVE) -> DocSnapshot:
    return snapshot_service.capture(
        kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, data=data, reason=reason, actor_kind="ai"
    )


class TestCapture:
    def test_three_overwrites_get_contiguous_seq(self, media: Path) -> None:
        seqs = [_capture(payload).seq for payload in (V1, V2, V3)]
        assert seqs == [1, 2, 3]

    def test_same_content_reuses_blob(self, media: Path) -> None:
        """同内容不重复占空间，但**每次覆盖都要留一行**——时间线不能因为去重而断。"""
        a = _capture(V1)
        b = _capture(V1)

        assert a.seq == 1
        assert b.seq == 2
        assert a.sha256 == b.sha256
        assert a.storage_path == b.storage_path

    def test_blob_is_content_addressed(self, media: Path) -> None:
        snap = _capture(V1)
        assert snap.storage_path.endswith(f"{snap.sha256}.docx")
        assert snap.storage_path.startswith("doc_snapshots/")
        assert default_storage.exists(snap.storage_path)

    def test_read_bytes_roundtrip(self, media: Path) -> None:
        snap = _capture(V2)
        assert snapshot_service.read_bytes(snap) == V2

    def test_read_bytes_detects_corruption(self, media: Path) -> None:
        """存储被动过就必须炸出来：悄悄回滚成别的内同比回滚失败更糟。"""
        snap = _capture(V2)
        with default_storage.open(snap.storage_path, "wb") as fh:
            fh.write(b"tampered")

        with pytest.raises(ValueError, match="损坏"):
            snapshot_service.read_bytes(snap)

    def test_list_is_newest_first(self, media: Path) -> None:
        for payload in (V1, V2, V3):
            _capture(payload)
        assert [s.seq for s in snapshot_service.list_snapshots(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH)] == [
            3,
            2,
            1,
        ]


class TestSnapshotsStayOutOfBoundFolder:
    def test_bound_folder_tree_is_untouched(self, wired: Path, media: Path) -> None:
        """绑定文件夹是律师要看的目录树，不许长出任何快照文件。"""
        # 只看绑定根这一棵子树：`media`（快照落盘处）与本 fixture 共用同一个
        # tmp_path，不去限定范围会把 MEDIA 里的 blob 也数进来
        root = wired / "1-合同"

        def tree() -> list[str]:
            return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))

        before = tree()
        for payload in (V1, V2, V3):
            _capture(payload)

        assert tree() == before
        assert before == ["a.docx"]


class TestRestore:
    def test_restore_writes_back_old_bytes(self, wired: Path, media: Path) -> None:
        (wired / "1-合同" / "a.docx").write_bytes(V2)
        snap = _capture(V1)

        result = snapshot_service.restore(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, seq=snap.seq)

        assert result["restored"] is True
        assert (wired / "1-合同" / "a.docx").read_bytes() == V1

    def test_restore_snapshots_current_content_first(self, wired: Path, media: Path) -> None:
        """回滚前必须先把**当前**内容存一份，否则点错版本就永久丢失当前稿。"""
        (wired / "1-合同" / "a.docx").write_bytes(V2)
        first = _capture(V1)

        result = snapshot_service.restore(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, seq=first.seq)

        # 回滚前的 V2 成了新的最新版
        latest = snapshot_service.latest(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH)
        assert latest is not None
        assert latest.seq == result["previous_seq"]
        assert snapshot_service.read_bytes(latest) == V2

    def test_restore_is_reversible(self, wired: Path, media: Path) -> None:
        """连点两次回滚必须能救回来：回滚动作本身可回滚。"""
        (wired / "1-合同" / "a.docx").write_bytes(V2)
        first = _capture(V1)

        r1 = snapshot_service.restore(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, seq=first.seq)
        assert (wired / "1-合同" / "a.docx").read_bytes() == V1

        snapshot_service.restore(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, seq=r1["previous_seq"])
        assert (wired / "1-合同" / "a.docx").read_bytes() == V2

    def test_restore_unknown_seq_is_a_soft_failure(self, wired: Path, media: Path) -> None:
        before = (wired / "1-合同" / "a.docx").read_bytes()
        result = snapshot_service.restore(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, seq=99)
        assert result["restored"] is False
        assert (wired / "1-合同" / "a.docx").read_bytes() == before


class TestWritePathIntegration:
    def test_apply_span_snapshots_the_previous_content(self, wired: Path, media: Path) -> None:
        """AI 落笔之前必须先给旧内容留底——这是「改坏了能救回来」的唯一保障。"""
        from docx import Document

        # 换成一份真 docx（apply_span 要解析它）
        doc = Document()
        doc.add_paragraph("甲方愿意支付人民币壹万元整。")
        import io

        buf = io.BytesIO()
        doc.save(buf)
        (wired / "1-合同" / "a.docx").write_bytes(buf.getvalue())
        original_bytes = (wired / "1-合同" / "a.docx").read_bytes()

        write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="甲方愿意支付人民币壹万元整。",
            suggested="甲方同意支付人民币壹万元整。",
        )

        snap = snapshot_service.latest(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH)
        assert snap is not None
        assert snapshot_service.read_bytes(snap) == original_bytes
        assert snap.reason == SnapshotReason.AI_REWRITE


class TestConcurrency:
    def test_parallel_capture_gets_unique_contiguous_seq(self, media: Path, transactional_db: Any) -> None:
        """并发覆写同一份文件：seq 不能撞（撞了编辑器保存会直接失败）。

        这里必须用 `transactional_db`：默认的 `db` fixture 把整个用例包在一个
        事务里，子线程看不到这个事务里的数据，测出来的并发是假的。
        """
        del transactional_db
        payloads = [f"v{i}".encode() for i in range(6)]

        def worker(payload: bytes) -> DocSnapshot:
            try:
                return _capture(payload)
            finally:
                # 子线程各自建了连接：不关掉会卡住测试库的 teardown
                from django.db import connection

                connection.close()

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(worker, payloads))

        seqs = sorted(
            DocSnapshot.objects.filter(owner_kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH).values_list(
                "seq", flat=True
            )
        )
        assert seqs == [1, 2, 3, 4, 5, 6]
