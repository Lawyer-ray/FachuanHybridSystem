"""原地保存 / 另存为 的磁盘语义测试。

**为什么要单独测**：这两条路与「拖拽上传」的契约**相反**——
`save_uploads` 是「同名自动加序号、绝不覆盖」（拖拽不能误盖旧稿），
而「原地保存」必须覆盖同一份（加序号就变成另存为，律师看到的还是旧内容）。
两者混淆就会：要么改了半天没生效，要么拖个文件把原稿盖了。

重点：
- 原地保存覆盖原路径、不加序号、原子替换；
- `expect_mtime` 不一致时报冲突（两人同开不静默丢掉前一个人的修改）；
- 另存为落到同目录、同名自动加序号、不覆盖原文件；
- 越界路径一律拒绝。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from apps.core.exceptions import ConflictError, NotFoundError, ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService


class _Service(BoundFolderBrowseService):
    """最小可用的具体实现：绑定到临时目录、无 ACL。"""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self._root


@pytest.fixture
def svc(tmp_path: Path) -> _Service:
    return _Service(tmp_path)


def _write(root: Path, rel: str, data: bytes = b"old") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class TestSaveFileContent:
    def test_overwrites_same_file(self, svc: _Service, tmp_path: Path) -> None:
        """原地保存必须覆盖同一份，不能另起一个带序号的新文件。"""
        f = _write(tmp_path, "a.docx", b"old")
        out = svc.save_file_content(owner_id=1, subpath="a.docx", data=b"new")

        assert f.read_bytes() == b"new"
        assert out["subpath"] == "a.docx"
        assert out["size"] == 3
        # 不能出现 a_1.docx
        assert not (tmp_path / "a_1.docx").exists()

    def test_nested_subpath(self, svc: _Service, tmp_path: Path) -> None:
        f = _write(tmp_path, "1-合同/a.docx")
        svc.save_file_content(owner_id=1, subpath="1-合同/a.docx", data=b"xyz")
        assert f.read_bytes() == b"xyz"

    def test_no_backup_left_behind(self, svc: _Service, tmp_path: Path) -> None:
        """产品决定不留备份：覆盖后目录里不应多出 _历史 / .bak 之类。"""
        _write(tmp_path, "a.docx")
        svc.save_file_content(owner_id=1, subpath="a.docx", data=b"new")

        names = {p.name for p in tmp_path.iterdir()}
        assert names == {"a.docx"}, f"不应产生额外文件，实际：{names}"

    def test_no_tmp_file_left_on_success(self, svc: _Service, tmp_path: Path) -> None:
        _write(tmp_path, "a.docx")
        svc.save_file_content(owner_id=1, subpath="a.docx", data=b"new")
        assert not any(p.name.endswith(tuple(f".tmp{os.getpid()}" for _ in [0])) for p in tmp_path.iterdir())

    def test_mtime_match_allows_save(self, svc: _Service, tmp_path: Path) -> None:
        f = _write(tmp_path, "a.docx")
        svc.save_file_content(owner_id=1, subpath="a.docx", data=b"new", expect_mtime=f.stat().st_mtime)
        assert f.read_bytes() == b"new"

    def test_mtime_mismatch_raises_conflict(self, svc: _Service, tmp_path: Path) -> None:
        """两人同开同一份：后保存的一方不能静默覆盖前一个人的修改。"""
        f = _write(tmp_path, "a.docx")
        stale = f.stat().st_mtime - 60  # 假装是 1 分钟前打开时的 mtime

        with pytest.raises(ConflictError):
            svc.save_file_content(owner_id=1, subpath="a.docx", data=b"new", expect_mtime=stale)
        assert f.read_bytes() == b"old", "冲突时不能动原文件"

    def test_missing_file_raises_not_found(self, svc: _Service, tmp_path: Path) -> None:
        with pytest.raises(NotFoundError):
            svc.save_file_content(owner_id=1, subpath="nope.docx", data=b"x")

    def test_directory_target_rejected(self, svc: _Service, tmp_path: Path) -> None:
        (tmp_path / "d").mkdir()
        with pytest.raises(ValidationException):
            svc.save_file_content(owner_id=1, subpath="d", data=b"x")

    def test_path_traversal_rejected(self, svc: _Service, tmp_path: Path) -> None:
        with pytest.raises(ValidationException):
            svc.save_file_content(owner_id=1, subpath="../escape.docx", data=b"x")


class TestSaveNewFile:
    def test_creates_new_file_keeping_original(self, svc: _Service, tmp_path: Path) -> None:
        src = _write(tmp_path, "a.docx", b"old")
        out = svc.save_new_file(owner_id=1, subpath="a.docx", name="a[修订版]V1_20261025.docx", data=b"new")

        assert src.read_bytes() == b"old", "另存为不能动原文件"
        assert (tmp_path / "a[修订版]V1_20261025.docx").read_bytes() == b"new"
        assert out["name"] == "a[修订版]V1_20261025.docx"

    def test_same_name_gets_suffix_not_overwrite(self, svc: _Service, tmp_path: Path) -> None:
        """同名已存在时加序号，保住已有文件（与上传同一套去重逻辑）。"""
        _write(tmp_path, "a.docx", b"old")
        _write(tmp_path, "a[修订版]V1_20261025.docx", b"existing")

        out = svc.save_new_file(
            owner_id=1, subpath="a.docx", name="a[修订版]V1_20261025.docx", data=b"new"
        )
        assert out["name"] == "a[修订版]V1_20261025_1.docx"
        assert (tmp_path / "a[修订版]V1_20261025.docx").read_bytes() == b"existing"

    def test_saves_into_source_directory(self, svc: _Service, tmp_path: Path) -> None:
        """另存为落在源文件所在目录，不是绑定根。"""
        _write(tmp_path, "1-合同/a.docx")
        svc.save_new_file(owner_id=1, subpath="1-合同/a.docx", name="b.docx", data=b"x")
        assert (tmp_path / "1-合同" / "b.docx").exists()
        assert not (tmp_path / "b.docx").exists()

    def test_directory_source_rejected(self, svc: _Service, tmp_path: Path) -> None:
        (tmp_path / "d").mkdir()
        with pytest.raises(ValidationException):
            svc.save_new_file(owner_id=1, subpath="d", name="x.docx", data=b"x")
