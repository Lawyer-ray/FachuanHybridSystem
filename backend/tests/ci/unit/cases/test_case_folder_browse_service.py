"""CaseFolderBrowseService 单测：子路径规范化安全、目录枚举契约、管理操作（新建/上传/重命名）与 ACL。"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cases.models import CaseFolderBinding
from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.testing.factories import CaseFactory


@pytest.fixture
def svc() -> CaseFolderBrowseService:
    return CaseFolderBrowseService()


# ── normalize_subpath（纯函数，零 DB） ──


class TestNormalizeSubpath:
    def test_empty_and_whitespace(self, svc):
        assert svc.normalize_subpath("") == ""
        assert svc.normalize_subpath("   ") == ""

    def test_simple_and_nested(self, svc):
        assert svc.normalize_subpath("2-邮件往来") == "2-邮件往来"
        assert svc.normalize_subpath("3-执行/2-邮件往来/2026.09.29-x") == "3-执行/2-邮件往来/2026.09.29-x"

    def test_backslash_normalized(self, svc):
        assert svc.normalize_subpath("a\\b") == "a/b"

    def test_dot_segments_stripped(self, svc):
        assert svc.normalize_subpath("./a/./b/") == "a/b"
        assert svc.normalize_subpath("./.") == ""

    @pytest.mark.parametrize("raw", ["/etc/passwd", "~/secret", "C:/Windows", "../escape", "a/../../b"])
    def test_illegal_forms_raise(self, svc, raw):
        with pytest.raises(ValidationException):
            svc.normalize_subpath(raw)


# ── 收敛与相对路径换算（tmp_path，零 DB） ──


class TestResolveAndSubpath:
    def test_resolve_within_root(self, svc, tmp_path):
        target = svc._resolve_subpath(tmp_path, "sub/file.txt")
        assert target == (tmp_path / "sub" / "file.txt").resolve()

    def test_resolve_root_when_empty(self, svc, tmp_path):
        assert svc._resolve_subpath(tmp_path, "") == tmp_path

    def test_symlink_escape_rejected(self, svc, tmp_path):
        """绑定目录内指向外部的符号链接：resolve 后越界必须拒绝。"""
        outside = tmp_path.parent / "outside-escape-target"
        outside.mkdir()
        (outside / "secret.txt").write_text("x")
        link = tmp_path / "jump"
        link.symlink_to(outside)
        with pytest.raises(ValidationException, match="不在绑定目录内"):
            svc._resolve_subpath(tmp_path, "jump/secret.txt")

    def test_subpath_of(self, svc, tmp_path):
        assert svc._subpath_of(tmp_path, tmp_path) == ""
        assert svc._subpath_of(tmp_path, tmp_path / "a" / "b.pdf") == "a/b.pdf"
        assert svc._subpath_of(tmp_path, tmp_path.parent) == ""


# ── 绑定 / ACL / 枚举（django_db） ──


@pytest.mark.django_db
class TestListEntriesAndResolveFile:
    def _bind(self, tmp_path: Path):
        case = CaseFactory()
        CaseFolderBinding.objects.create(case=case, folder_path=str(tmp_path))
        return case

    def test_root_listing_contract(self, svc, tmp_path):
        mail = tmp_path / "2-邮件往来" / "2026.09.29-收到法院裁定书"
        mail.mkdir(parents=True)
        (mail / "裁定书.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "root-note.txt").write_text("hi")
        (tmp_path / ".DS_Store").write_text("junk")
        case = self._bind(tmp_path)

        out = svc.list_entries(owner_id=case.id, subpath="", perm_open_access=True)

        assert out["browsable"] is True
        assert out["subpath"] == "" and out["parent_subpath"] == ""
        # file_count 是 2026-10 新增字段（常法页据它判「事项是否已交付」）：
        # 该子目录下没有直接文件（只有更深一层的 2026.09.29 目录），故为 0
        assert out["folders"] == [{"name": "2-邮件往来", "subpath": "2-邮件往来", "file_count": 0}]
        assert [f["name"] for f in out["files"]] == ["root-note.txt"]
        assert out["files"][0]["subpath"] == "root-note.txt"
        assert out["files"][0]["size"] == 2

    def test_subfolder_drilldown(self, svc, tmp_path):
        mail = tmp_path / "2-邮件往来" / "2026.09.29-收到法院裁定书"
        mail.mkdir(parents=True)
        (mail / "裁定书.pdf").write_bytes(b"%PDF-1.4")
        case = self._bind(tmp_path)

        out = svc.list_entries(owner_id=case.id, subpath="2-邮件往来", perm_open_access=True)

        assert out["subpath"] == "2-邮件往来"
        assert out["parent_subpath"] == ""
        assert out["folders"][0]["subpath"] == "2-邮件往来/2026.09.29-收到法院裁定书"
        assert out["files"] == []

        deeper = svc.list_entries(
            owner_id=case.id, subpath="2-邮件往来/2026.09.29-收到法院裁定书", perm_open_access=True
        )
        assert [f["name"] for f in deeper["files"]] == ["裁定书.pdf"]
        assert deeper["parent_subpath"] == "2-邮件往来"

    def test_missing_subfolder_404(self, svc, tmp_path):
        case = self._bind(tmp_path)
        with pytest.raises(NotFoundError, match="子文件夹不存在"):
            svc.list_entries(owner_id=case.id, subpath="不存在", perm_open_access=True)

    def test_no_binding_raises_not_found(self, svc, tmp_path):
        case = CaseFactory()
        with pytest.raises(NotFoundError, match="未绑定文件夹"):
            svc.list_entries(owner_id=case.id, perm_open_access=True)

    def test_inaccessible_root_404(self, svc, tmp_path):
        case = self._bind(tmp_path / "gone")
        with pytest.raises(NotFoundError, match="不可达"):
            svc.list_entries(owner_id=case.id, perm_open_access=True)

    def test_resolve_file(self, svc, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
        case = self._bind(tmp_path)
        resolved = svc.resolve_file(owner_id=case.id, subpath="a.pdf", perm_open_access=True)
        assert resolved == (tmp_path / "a.pdf").resolve()

    def test_resolve_file_missing_404(self, svc, tmp_path):
        case = self._bind(tmp_path)
        with pytest.raises(NotFoundError, match="文件不存在"):
            svc.resolve_file(owner_id=case.id, subpath="ghost.pdf", perm_open_access=True)

    def test_acl_fail_closed_without_access(self, svc, tmp_path):
        """无 user / 无开放授权：fail-closed（归属过滤 user=None 陷阱的回归闸）。"""
        case = self._bind(tmp_path)
        with pytest.raises((PermissionDenied, NotFoundError)):
            svc.list_entries(owner_id=case.id)


# ── 管理操作：mkdir / upload / rename（django_db） ──


@pytest.mark.django_db
class TestManageOperations:
    def _bind(self, tmp_path: Path):
        case = CaseFactory()
        CaseFolderBinding.objects.create(case=case, folder_path=str(tmp_path))
        return case

    def test_mkdir(self, svc, tmp_path):
        case = self._bind(tmp_path)
        out = svc.mkdir(owner_id=case.id, subpath="", name="2-邮件往来", perm_open_access=True)
        assert out == {"subpath": "2-邮件往来", "name": "2-邮件往来"}
        assert (tmp_path / "2-邮件往来").is_dir()

    def test_mkdir_duplicate_rejected(self, svc, tmp_path):
        case = self._bind(tmp_path)
        (tmp_path / "dup").mkdir()
        with pytest.raises(ValidationException, match="已存在"):
            svc.mkdir(owner_id=case.id, subpath="", name="dup", perm_open_access=True)

    def test_mkdir_illegal_names(self, svc, tmp_path):
        case = self._bind(tmp_path)
        for bad in ["", "  ", ".hidden", "..", "a/b", "a\\b", "x:y", "n" * 201]:
            with pytest.raises(ValidationException):
                svc.mkdir(owner_id=case.id, subpath="", name=bad, perm_open_access=True)

    def test_upload_writes_and_dedupes(self, svc, tmp_path):
        case = self._bind(tmp_path)
        (tmp_path / "inbox").mkdir()
        files = [
            SimpleUploadedFile("裁定书.pdf", b"%PDF-1.4-aaa"),
            SimpleUploadedFile("裁定书.pdf", b"%PDF-1.4-bbb"),  # 同名 → 序号错开
            SimpleUploadedFile("../escape.txt", b"x"),  # 文件名清洗：路径分隔符被处理
        ]
        out = svc.save_uploads(owner_id=case.id, subpath="inbox", files=files, perm_open_access=True)
        names = [s["name"] for s in out["saved"]]
        assert "裁定书.pdf" in names and "裁定书_1.pdf" in names
        assert (tmp_path / "inbox" / "裁定书.pdf").read_bytes() == b"%PDF-1.4-aaa"
        assert (tmp_path / "inbox" / "裁定书_1.pdf").read_bytes() == b"%PDF-1.4-bbb"
        # 清洗后的文件必须仍收敛在目标目录
        for p in (tmp_path / "inbox").iterdir():
            assert p.parent == tmp_path / "inbox"

    def test_upload_empty_rejected(self, svc, tmp_path):
        case = self._bind(tmp_path)
        with pytest.raises(ValidationException, match="未收到文件"):
            svc.save_uploads(owner_id=case.id, subpath="", files=[], perm_open_access=True)

    def test_rename_file_and_folder(self, svc, tmp_path):
        case = self._bind(tmp_path)
        folder = tmp_path / "草稿"
        folder.mkdir()
        (folder / "old.pdf").write_bytes(b"x")

        out = svc.rename(owner_id=case.id, subpath="草稿/old.pdf", new_name="new.pdf", perm_open_access=True)
        assert out == {"subpath": "草稿/new.pdf", "name": "new.pdf"}
        assert (folder / "new.pdf").exists() and not (folder / "old.pdf").exists()

        svc.rename(owner_id=case.id, subpath="草稿", new_name="定稿", perm_open_access=True)
        assert (tmp_path / "定稿" / "new.pdf").exists()

    def test_rename_duplicate_and_root_rejected(self, svc, tmp_path):
        case = self._bind(tmp_path)
        (tmp_path / "a.txt").write_text("1")
        (tmp_path / "b.txt").write_text("2")
        with pytest.raises(ValidationException, match="已存在"):
            svc.rename(owner_id=case.id, subpath="a.txt", new_name="b.txt", perm_open_access=True)
        with pytest.raises(ValidationException, match="绑定根"):
            svc.rename(owner_id=case.id, subpath="", new_name="改名", perm_open_access=True)

    def test_copy_file_and_dedupe_name(self, svc, tmp_path):
        case = self._bind(tmp_path)
        (tmp_path / "src.pdf").write_bytes(b"x")
        (tmp_path / "dst").mkdir()
        out = svc.copy_entry(owner_id=case.id, subpath="src.pdf", dest_subpath="dst", perm_open_access=True)
        assert out["subpath"] == "dst/src.pdf"
        again = svc.copy_entry(owner_id=case.id, subpath="src.pdf", dest_subpath="dst", perm_open_access=True)
        assert again["name"] == "src_1.pdf"  # 同名自动加序号，不覆盖

    def test_copy_folder_recursive(self, svc, tmp_path):
        case = self._bind(tmp_path)
        folder = tmp_path / "材料"
        (folder / "子").mkdir(parents=True)
        (folder / "子" / "a.pdf").write_bytes(b"a")
        (tmp_path / "归档").mkdir()
        out = svc.copy_entry(owner_id=case.id, subpath="材料", dest_subpath="归档", perm_open_access=True)
        assert (tmp_path / "归档" / "材料" / "子" / "a.pdf").read_bytes() == b"a"
        assert out["subpath"] == "归档/材料"

    def test_copy_into_itself_rejected(self, svc, tmp_path):
        case = self._bind(tmp_path)
        folder = tmp_path / "材料"
        (folder / "子").mkdir(parents=True)
        with pytest.raises(ValidationException, match="自身内部"):
            svc.copy_entry(owner_id=case.id, subpath="材料", dest_subpath="材料/子", perm_open_access=True)

    def test_delete_moves_to_recycle_dir(self, svc, tmp_path):
        case = self._bind(tmp_path)
        (tmp_path / "要删.pdf").write_bytes(b"x")
        out = svc.delete_entry(owner_id=case.id, subpath="要删.pdf", perm_open_access=True)
        assert out["subpath"].startswith("_已删除/")
        assert not (tmp_path / "要删.pdf").exists()
        trashed = list((tmp_path / "_已删除").iterdir())
        assert len(trashed) == 1 and trashed[0].name.endswith("-要删.pdf")

    def test_delete_root_and_trash_rejected(self, svc, tmp_path):
        case = self._bind(tmp_path)
        with pytest.raises(ValidationException, match="绑定根目录"):
            svc.delete_entry(owner_id=case.id, subpath="", perm_open_access=True)
        (tmp_path / "_已删除").mkdir()
        with pytest.raises(ValidationException, match="回收目录"):
            svc.delete_entry(owner_id=case.id, subpath="_已删除", perm_open_access=True)
