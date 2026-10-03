"""Tests for express_query/signals.py - post_delete file cleanup."""

from unittest.mock import MagicMock, patch

import pytest


class TestDeleteTaskFiles:
    """Test delete_task_files signal handler."""

    def test_deletes_waybill_and_result_files(self):
        """Deleting ExpressQueryTask cleans up both waybill_image and result_pdf."""
        from apps.express_query.signals import delete_task_files

        mock_waybill = MagicMock()
        mock_waybill.name = "waybill.jpg"
        mock_waybill.delete = MagicMock()

        mock_pdf = MagicMock()
        mock_pdf.name = "result.pdf"
        mock_pdf.delete = MagicMock()

        instance = MagicMock()
        instance.waybill_image = mock_waybill
        instance.result_pdf = mock_pdf

        with patch("apps.express_query.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            delete_task_files(sender=MagicMock, instance=instance)

        mock_waybill.delete.assert_called_once_with(save=False)
        mock_pdf.delete.assert_called_once_with(save=False)

    def test_handles_empty_file_fields(self):
        """Handles case where file fields are empty/None."""
        from apps.express_query.signals import delete_task_files

        instance = MagicMock()
        instance.waybill_image = None
        instance.result_pdf = None

        with (
            patch("apps.express_query.signals.transaction") as mock_txn,
            patch("apps.express_query.signals._safe_delete_file_field") as mock_del,
        ):
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise: 两个空字段都进入安全删除分支（各自早退）
            assert delete_task_files(sender=MagicMock, instance=instance) is None
        assert mock_del.call_count == 2
        mock_del.assert_any_call(None, "邮单文件")
        mock_del.assert_any_call(None, "结果PDF")

    def test_handles_file_not_found(self):
        """Handles FileNotFoundError gracefully."""
        from apps.express_query.signals import delete_task_files

        mock_waybill = MagicMock()
        mock_waybill.name = "waybill.jpg"
        mock_waybill.delete.side_effect = FileNotFoundError("File not found")

        mock_pdf = MagicMock()
        mock_pdf.name = "result.pdf"

        instance = MagicMock()
        instance.waybill_image = mock_waybill
        instance.result_pdf = mock_pdf

        with patch("apps.express_query.signals.transaction") as mock_txn:
            mock_txn.on_commit.side_effect = lambda fn: fn()
            # Should not raise
            delete_task_files(sender=MagicMock, instance=instance)
        mock_pdf.delete.assert_called_once_with(save=False)


class TestSafeDeleteFileField:
    """Test _safe_delete_file_field helper."""

    def test_deletes_file_with_name(self):
        """Deletes file when it has a name."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.delete = MagicMock()

        _safe_delete_file_field(mock_file, "test description")
        mock_file.delete.assert_called_once_with(save=False)

    def test_skips_none_field(self):
        """Skips None field."""
        from apps.express_query.signals import _safe_delete_file_field

        # Should not raise: None 早退
        assert _safe_delete_file_field(None, "test description") is None

    def test_skips_field_without_name(self):
        """Skips field without name attribute."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = type("NoName", (), {})()
        # 无 name 属性 → 早退
        assert _safe_delete_file_field(mock_file, "test description") is None
        assert not hasattr(mock_file, "delete")

    def test_skips_field_with_empty_name(self):
        """Skips field with empty name."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = MagicMock()
        mock_file.name = ""
        assert _safe_delete_file_field(mock_file, "test description") is None
        # 空 name 早退：不应触发删除
        mock_file.delete.assert_not_called()

    def test_handles_generic_exception(self):
        """Handles generic exceptions during deletion."""
        from apps.express_query.signals import _safe_delete_file_field

        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.delete.side_effect = Exception("unexpected error")

        # Should not raise: 异常被捕获记 warning，但删除确实被尝试过
        assert _safe_delete_file_field(mock_file, "test description") is None
        mock_file.delete.assert_called_once_with(save=False)
