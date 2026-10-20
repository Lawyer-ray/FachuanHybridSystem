"""CaseFolderBrowseService 单测：子路径规范化安全、目录枚举契约、绑定与 ACL 分支。"""

from __future__ import annotations

from pathlib import Path

import pytest

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
        with pytest.raises(ValidationException, match="不在案件绑定目录内"):
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

        out = svc.list_entries(case_id=case.id, subpath="", perm_open_access=True)

        assert out["browsable"] is True
        assert out["subpath"] == "" and out["parent_subpath"] == ""
        assert out["folders"] == [{"name": "2-邮件往来", "subpath": "2-邮件往来"}]
        assert [f["name"] for f in out["files"]] == ["root-note.txt"]
        assert out["files"][0]["subpath"] == "root-note.txt"
        assert out["files"][0]["size"] == 2

    def test_subfolder_drilldown(self, svc, tmp_path):
        mail = tmp_path / "2-邮件往来" / "2026.09.29-收到法院裁定书"
        mail.mkdir(parents=True)
        (mail / "裁定书.pdf").write_bytes(b"%PDF-1.4")
        case = self._bind(tmp_path)

        out = svc.list_entries(case_id=case.id, subpath="2-邮件往来", perm_open_access=True)

        assert out["subpath"] == "2-邮件往来"
        assert out["parent_subpath"] == ""
        assert out["folders"][0]["subpath"] == "2-邮件往来/2026.09.29-收到法院裁定书"
        assert out["files"] == []

        deeper = svc.list_entries(
            case_id=case.id, subpath="2-邮件往来/2026.09.29-收到法院裁定书", perm_open_access=True
        )
        assert [f["name"] for f in deeper["files"]] == ["裁定书.pdf"]
        assert deeper["parent_subpath"] == "2-邮件往来"

    def test_missing_subfolder_not_browsable(self, svc, tmp_path):
        case = self._bind(tmp_path)
        out = svc.list_entries(case_id=case.id, subpath="不存在", perm_open_access=True)
        assert out["browsable"] is False
        assert "不存在" in (out["message"] or "")

    def test_no_binding_raises_not_found(self, svc, tmp_path):
        case = CaseFactory()
        with pytest.raises(NotFoundError, match="未绑定文件夹"):
            svc.list_entries(case_id=case.id, perm_open_access=True)

    def test_inaccessible_root(self, svc, tmp_path):
        case = self._bind(tmp_path / "gone")
        out = svc.list_entries(case_id=case.id, perm_open_access=True)
        assert out["browsable"] is False
        assert "不可达" in (out["message"] or "")

    def test_resolve_file(self, svc, tmp_path):
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
        case = self._bind(tmp_path)
        resolved = svc.resolve_file(case_id=case.id, subpath="a.pdf", perm_open_access=True)
        assert resolved == (tmp_path / "a.pdf").resolve()

    def test_resolve_file_missing_404(self, svc, tmp_path):
        case = self._bind(tmp_path)
        with pytest.raises(NotFoundError, match="文件不存在"):
            svc.resolve_file(case_id=case.id, subpath="ghost.pdf", perm_open_access=True)

    def test_acl_fail_closed_without_access(self, svc, tmp_path):
        """无 user / 无开放授权：fail-closed（归属过滤 user=None 陷阱的回归闸）。"""
        case = self._bind(tmp_path)
        with pytest.raises((PermissionDenied, NotFoundError)):
            svc.list_entries(case_id=case.id)
