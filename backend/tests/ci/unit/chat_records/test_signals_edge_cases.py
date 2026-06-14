"""Coverage tests for chat_records/signals.py — edge cases for _safe_prune_empty_parents."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSafePruneEdgeCases:
    def test_returns_on_non_absolute_path(self) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        # Relative path should return early
        _safe_prune_empty_parents("relative/path.mp4")

    def test_returns_when_not_under_media_root(self) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        _safe_prune_empty_parents("/tmp/some/file.mp4")

    def test_handles_path_resolve_exception(self) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        # Path that can't resolve
        _safe_prune_empty_parents(None)

    def test_handles_media_root_resolve_exception(self) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        with patch("apps.chat_records.signals.settings") as mock_settings:
            type(mock_settings).MEDIA_ROOT = MagicMock(side_effect=Exception("bad root"))
            _safe_prune_empty_parents("/some/absolute/path.mp4")

    def test_prunes_empty_dirs_up_to_stop_at(self, tmp_path: Path) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        media_root = tmp_path / "media"
        media_root.mkdir()
        chat_dir = media_root / "chat_records" / "sub" / "deep"
        chat_dir.mkdir(parents=True)
        file_path = str(chat_dir / "file.mp4")
        (chat_dir / "file.mp4").touch()

        with patch("apps.chat_records.signals.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(media_root)
            # After delete, file is gone; prune should walk up from deep/
            (chat_dir / "file.mp4").unlink()
            _safe_prune_empty_parents(file_path)

    def test_stops_at_chat_records_dir(self, tmp_path: Path) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        media_root = tmp_path / "media"
        media_root.mkdir()
        chat_dir = media_root / "chat_records"
        chat_dir.mkdir()
        sub_dir = chat_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "file.mp4").touch()

        with patch("apps.chat_records.signals.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(media_root)
            (sub_dir / "file.mp4").unlink()
            _safe_prune_empty_parents(str(sub_dir / "file.mp4"))
            # chat_records dir should still exist
            assert chat_dir.exists()

    def test_non_empty_dir_not_removed(self, tmp_path: Path) -> None:
        from apps.chat_records.signals import _safe_prune_empty_parents

        media_root = tmp_path / "media"
        media_root.mkdir()
        chat_dir = media_root / "chat_records" / "sub"
        chat_dir.mkdir(parents=True)
        (chat_dir / "other.txt").touch()
        file_path = str(chat_dir / "file.mp4")

        with patch("apps.chat_records.signals.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(media_root)
            _safe_prune_empty_parents(file_path)
            # sub dir should still exist because it has other.txt
            assert chat_dir.exists()


class TestDeleteFieldFileByNameEdgeCases:
    def test_nonexistent_file_not_deleted(self) -> None:
        from apps.chat_records.signals import _delete_field_file_by_name

        with (
            patch("django.core.files.storage.default_storage") as mock_storage,
            patch("apps.chat_records.signals._safe_prune_empty_parents"),
        ):
            mock_storage.exists.return_value = False
            _delete_field_file_by_name("nonexistent/file.mp4")
            mock_storage.delete.assert_not_called()

    def test_delete_exception_handled(self) -> None:
        from apps.chat_records.signals import _delete_field_file_by_name

        with patch("django.core.files.storage.default_storage") as mock_storage:
            mock_storage.exists.side_effect = Exception("storage error")
            # Should not raise
            _delete_field_file_by_name("test.mp4")

    def test_storage_has_no_path_method(self) -> None:
        from apps.chat_records.signals import _delete_field_file_by_name

        with (
            patch("django.core.files.storage.default_storage") as mock_storage,
            patch("apps.chat_records.signals._safe_prune_empty_parents") as mock_prune,
        ):
            mock_storage.exists.return_value = True
            mock_storage.path.side_effect = AttributeError("no path method")
            _delete_field_file_by_name("test.mp4")
            # Should still call delete but prune with None
            mock_storage.delete.assert_called_once_with("test.mp4")
