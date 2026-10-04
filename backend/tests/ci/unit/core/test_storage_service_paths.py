"""storage_service 路径安全回归测试（CodeQL py/path-injection #5953 修复验证）。

覆盖 ``to_media_abs`` / ``normalize_to_media_rel`` / ``delete_media_file`` 的
路径收敛校验，三类必测场景：

1. 合法路径通过：相对路径（拼接到 MEDIA_ROOT 下）与 MEDIA_ROOT 内的绝对路径；
2. ``../`` 穿越拒绝：折叠后越界一律 FILE_PATH_OUTSIDE_MEDIA_ROOT；
3. 绝对路径注入拒绝：``/etc/passwd`` 等绝对路径输入不在 MEDIA_ROOT 内即拒绝。

另覆盖符号链接逃逸、同前缀目录混淆（``media-evil`` vs ``media``）等变体。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from django.test import override_settings

from apps.core.exceptions import ValidationException
from apps.core.services.storage_service import delete_media_file, normalize_to_media_rel, to_media_abs


@pytest.fixture
def media_root(tmp_path: Any) -> Path:
    """隔离的 MEDIA_ROOT，内含一个真实样例文件。"""
    media = tmp_path / "media"
    (media / "cases" / "docs").mkdir(parents=True)
    sample = media / "cases" / "docs" / "sample.txt"
    sample.write_text("sample", encoding="utf-8")
    return media


def _settings(media: Path) -> Any:
    return override_settings(MEDIA_ROOT=str(media))


# ── 1. 合法路径通过 ──────────────────────────────────────────────────────────


class TestLegalPathPasses:
    def test_relative_path_resolved_inside_root(self, media_root: Path) -> None:
        with _settings(media_root):
            result = to_media_abs("cases/docs/sample.txt")
        assert result.is_absolute()
        assert result == media_root / "cases" / "docs" / "sample.txt"
        assert result.read_text(encoding="utf-8") == "sample"

    def test_absolute_path_within_root_accepted(self, media_root: Path) -> None:
        abs_file = media_root / "cases" / "docs" / "sample.txt"
        with _settings(media_root):
            result = to_media_abs(str(abs_file))
        assert result == abs_file.resolve()

    def test_dot_segments_within_root_collapsed(self, media_root: Path) -> None:
        with _settings(media_root):
            result = to_media_abs("cases/docs/../docs/./sample.txt")
        assert result == media_root / "cases" / "docs" / "sample.txt"

    def test_directory_path_within_root_accepted(self, media_root: Path) -> None:
        with _settings(media_root):
            result = to_media_abs("cases/docs")
        assert result == media_root / "cases" / "docs"
        assert result.is_dir()

    def test_normalize_to_media_rel_absolute_within_root(self, media_root: Path) -> None:
        abs_path = str(media_root / "sub" / "file.txt")
        with _settings(media_root):
            result = normalize_to_media_rel(abs_path)
        assert result == "sub/file.txt"


# ── 2. ``../`` 穿越拒绝 ──────────────────────────────────────────────────────


class TestDotDotTraversalRejected:
    @pytest.mark.parametrize(
        "malicious",
        [
            "../../etc/passwd",
            "cases/../../../etc/passwd",
            "./.././..",
            "cases/docs/../../../../../../../../etc/hosts",
        ],
    )
    def test_traversal_raises(self, media_root: Path, malicious: str) -> None:
        with _settings(media_root):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                to_media_abs(malicious)

    def test_normalize_to_media_rel_traversal_raises(self, media_root: Path) -> None:
        with _settings(media_root):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                normalize_to_media_rel(str(media_root / ".." / "outside.txt"))


# ── 3. 绝对路径注入拒绝 ─────────────────────────────────────────────────────


class TestAbsoluteInjectionRejected:
    @pytest.mark.parametrize(
        "malicious",
        [
            "/etc/passwd",
            "/etc/../etc/passwd",
            "//etc/passwd",
            str(Path("/private/tmp/definitely-not-in-media.txt")),
        ],
    )
    def test_absolute_outside_root_raises(self, media_root: Path, malicious: str) -> None:
        with _settings(media_root):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                to_media_abs(malicious)

    def test_root_slash_rejected(self, media_root: Path) -> None:
        with _settings(media_root):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                to_media_abs("/")

    def test_prefix_confusion_sibling_directory_rejected(self, tmp_path: Any) -> None:
        """同前缀目录 ``media-evil`` 不得因字符串前缀相同被误放行。"""
        media = tmp_path / "media"
        evil = tmp_path / "media-evil"
        media.mkdir(parents=True)
        evil.mkdir()
        (evil / "secret.txt").write_text("secret", encoding="utf-8")
        with _settings(media):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                to_media_abs(str(evil / "secret.txt"))
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                to_media_abs("../media-evil/secret.txt")

    def test_normalize_to_media_rel_absolute_outside_raises(self, media_root: Path) -> None:
        with _settings(media_root):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                normalize_to_media_rel("/etc/hosts")


# ── 4. 变体与边界 ────────────────────────────────────────────────────────────


class TestEdgeVariants:
    def test_empty_path_raises(self, media_root: Path) -> None:
        with _settings(media_root):
            with pytest.raises(ValidationException, match="文件路径不能为空"):
                to_media_abs("")

    def test_media_root_not_configured_raises(self, tmp_path: Any, monkeypatch: Any) -> None:
        from apps.core.services import storage_service

        monkeypatch.setattr(storage_service, "_get_media_root", lambda: None)
        with pytest.raises(ValidationException, match="MEDIA_ROOT 未配置"):
            to_media_abs("some/file.txt")

    def test_symlink_escape_rejected(self, media_root: Path, tmp_path: Any) -> None:
        """MEDIA_ROOT 内的符号链接指向外部文件时，必须按真实目标校验并拒绝。"""
        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = media_root / "cases" / "escape.txt"
        link.symlink_to(outside)
        with _settings(media_root):
            with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
                to_media_abs("cases/escape.txt")

    def test_symlink_to_inside_root_accepted(self, media_root: Path) -> None:
        link = media_root / "cases" / "inside-link.txt"
        link.symlink_to(media_root / "cases" / "docs" / "sample.txt")
        with _settings(media_root):
            result = to_media_abs("cases/inside-link.txt")
        assert result == (media_root / "cases" / "docs" / "sample.txt").resolve()

    def test_media_root_prefix_ends_with_sep(self, media_root: Path) -> None:
        from apps.core.services.storage_service import _media_root_prefix

        with _settings(media_root):
            prefix = _media_root_prefix()
        assert prefix.endswith(os.sep)
        assert prefix == str(media_root.resolve()).rstrip(os.sep) + os.sep


# ── 5. delete_media_file 收敛校验 ───────────────────────────────────────────


class TestDeleteMediaFile:
    def test_deletes_file_inside_root(self, media_root: Path) -> None:
        target = media_root / "cases" / "docs" / "sample.txt"
        with _settings(media_root):
            assert delete_media_file("cases/docs/sample.txt") is True
        assert not target.exists()

    def test_traversal_rejected_without_delete(self, media_root: Path, tmp_path: Any) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with _settings(media_root):
            assert delete_media_file("../../outside.txt") is False
        assert outside.exists()

    def test_absolute_outside_rejected_without_delete(self, tmp_path: Any) -> None:
        outside = tmp_path / "etc-passwd.txt"
        outside.write_text("x", encoding="utf-8")
        with override_settings(MEDIA_ROOT=str(tmp_path / "nonexistent-media")):
            assert delete_media_file(str(outside)) is False
        assert outside.exists()

    def test_empty_path_returns_false(self, media_root: Path) -> None:
        with _settings(media_root):
            assert delete_media_file("") is False
