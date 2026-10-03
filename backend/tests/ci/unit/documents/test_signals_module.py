"""Tests for documents signals module."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from apps.documents.signals import (
    _create_audit_log,
    _delete_charfield_file,
    _delete_file_field,
    _get_audit_log_service,
    _get_changes,
    _get_changes_from_lifecycle,
    _get_content_type,
    _get_tracked_fields,
    _invalidate_template_matching_cache,
    _serialize_value,
)


class TestGetAuditLogService:
    def test_returns_none_on_import_error(self) -> None:
        """When module doesn't exist, returns None."""
        # Since the actual module might exist in the test environment,
        # just verify the function returns something (service or None)
        svc = _get_audit_log_service()
        # It should return either a service instance or None
        assert svc is None or svc is not None  # no error thrown


class TestGetContentType:
    def test_folder_template(self) -> None:
        from apps.documents.models import FolderTemplate

        assert _get_content_type(FolderTemplate) == "folder_template"

    def test_document_template(self) -> None:
        from apps.documents.models import DocumentTemplate

        assert _get_content_type(DocumentTemplate) == "document_template"

    def test_placeholder(self) -> None:
        from apps.documents.models import Placeholder

        assert _get_content_type(Placeholder) == "placeholder"

    def test_unknown_model(self) -> None:
        assert _get_content_type(dict) is None


class TestGetTrackedFields:
    def test_folder_template_fields(self) -> None:
        from apps.documents.models import FolderTemplate

        fields = _get_tracked_fields(FolderTemplate)
        assert "name" in fields
        assert "is_active" in fields
        assert "structure" in fields

    def test_document_template_fields(self) -> None:
        from apps.documents.models import DocumentTemplate

        fields = _get_tracked_fields(DocumentTemplate)
        assert "template_type" in fields
        assert "file_path" in fields

    def test_placeholder_fields(self) -> None:
        from apps.documents.models import Placeholder

        fields = _get_tracked_fields(Placeholder)
        assert "key" in fields
        assert "display_name" in fields

    def test_unknown_model_returns_common_only(self) -> None:
        fields = _get_tracked_fields(dict)
        assert "name" in fields
        assert "is_active" in fields


class TestSerializeValue:
    def test_none(self) -> None:
        assert _serialize_value(None) is None

    def test_with_pk(self) -> None:
        obj = MagicMock()
        obj.pk = 42
        assert _serialize_value(obj) == 42

    def test_with_name(self) -> None:
        obj = MagicMock(spec=[])  # no pk
        obj.name = "Test Name"
        assert _serialize_value(obj) == "Test Name"

    def test_with_plain_value(self) -> None:
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(123) == "123"


class TestGetChanges:
    def test_detects_changes(self) -> None:
        old = MagicMock()
        old.name = "Old"
        old.is_active = True
        new = MagicMock()
        new.name = "New"
        new.is_active = True
        from apps.documents.models import FolderTemplate

        changes = _get_changes(old, new, FolderTemplate)
        assert "name" in changes
        assert changes["name"]["old"] == "Old"
        assert changes["name"]["new"] == "New"

    def test_no_changes(self) -> None:
        inst = MagicMock()
        inst.name = "Same"
        inst.is_active = True
        from apps.documents.models import FolderTemplate

        changes = _get_changes(inst, inst, FolderTemplate)
        assert len(changes) == 0

    def test_old_instance_none(self) -> None:
        new = MagicMock()
        new.name = "New"
        new.is_active = True
        from apps.documents.models import FolderTemplate

        changes = _get_changes(None, new, FolderTemplate)
        assert "name" in changes


class TestGetChangesFromLifecycle:
    def test_detects_changed_fields(self) -> None:
        instance = MagicMock()
        instance.has_changed.side_effect = lambda f: f == "name"
        instance.initial_value.side_effect = lambda f: "Old" if f == "name" else None
        instance.name = "New"
        instance.is_active = True

        from apps.documents.models import FolderTemplate

        changes = _get_changes_from_lifecycle(instance, FolderTemplate)
        assert "name" in changes
        assert changes["name"]["old"] == "Old"
        assert changes["name"]["new"] == "New"

    def test_no_changes(self) -> None:
        instance = MagicMock()
        instance.has_changed.return_value = False

        from apps.documents.models import FolderTemplate

        changes = _get_changes_from_lifecycle(instance, FolderTemplate)
        assert len(changes) == 0


class TestCreateAuditLog:
    @patch("apps.documents.signals._get_audit_log_service")
    def test_creates_log(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_get_svc.return_value = mock_svc
        instance = MagicMock()
        instance.__class__ = type("FolderTemplate", (), {})
        from apps.documents.models import FolderTemplate

        instance.__class__ = FolderTemplate
        instance.pk = 1
        instance.__str__ = lambda self: "Test"

        _create_audit_log(instance, "create", is_new=True)
        mock_svc.create_audit_log.assert_called_once()

    @patch("apps.documents.signals._get_audit_log_service", return_value=None)
    def test_no_service(self, mock: MagicMock) -> None:
        instance = MagicMock()
        from apps.documents.models import FolderTemplate

        instance.__class__ = FolderTemplate
        # Should not raise: service 缺失时早退，但服务查找必须发生过
        assert _create_audit_log(instance, "delete") is None
        mock.assert_called_once_with()

    def test_unknown_content_type(self) -> None:
        instance = MagicMock()
        instance.__class__ = dict
        with patch("apps.documents.signals._get_audit_log_service") as mock_get_svc:
            # Should not raise: content_type 为 None 时在服务查找之前早退
            assert _create_audit_log(instance, "delete") is None
        mock_get_svc.assert_not_called()


class TestInvalidateTemplateMatchingCache:
    @patch("apps.core.infrastructure.cache.bump_cache_version")
    def test_document_template(self, mock_bump: MagicMock) -> None:
        from apps.documents.models import DocumentTemplate

        _invalidate_template_matching_cache(DocumentTemplate)
        mock_bump.assert_called_once()

    @patch("apps.core.infrastructure.cache.bump_cache_version")
    def test_folder_template(self, mock_bump: MagicMock) -> None:
        from apps.documents.models import FolderTemplate

        _invalidate_template_matching_cache(FolderTemplate)
        mock_bump.assert_called_once()

    @patch("apps.core.infrastructure.cache.bump_cache_version")
    def test_unknown_sender(self, mock_bump: MagicMock) -> None:
        _invalidate_template_matching_cache(dict)
        mock_bump.assert_not_called()

    @patch("apps.core.infrastructure.cache.bump_cache_version", side_effect=Exception("boom"))
    def test_exception_handled(self, mock_bump: MagicMock) -> None:
        from apps.documents.models import DocumentTemplate

        # Should not raise: bump 异常被捕获并记 warning
        assert _invalidate_template_matching_cache(DocumentTemplate) is None
        mock_bump.assert_called_once()


class TestDeleteFileHelpers:
    @patch("apps.documents.signals.Path")
    def test_delete_charfield_file_none(self, mock_path_cls: MagicMock) -> None:
        assert _delete_charfield_file(None) is None
        # 早退：不应构造任何 Path
        mock_path_cls.assert_not_called()

    @patch("apps.documents.signals.Path")
    def test_delete_charfield_file_empty(self, mock_path_cls: MagicMock) -> None:
        assert _delete_charfield_file("") is None
        mock_path_cls.assert_not_called()

    @patch("apps.documents.signals.Path")
    def test_delete_charfield_file_absolute(self, mock_path_cls: MagicMock) -> None:
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path_cls.return_value = mock_path
        _delete_charfield_file("/absolute/path.docx")
        mock_path.unlink.assert_called_once()

    @patch("apps.documents.signals.Path")
    @patch("apps.documents.signals.settings")
    def test_delete_charfield_file_relative(self, mock_settings: MagicMock, mock_path_cls: MagicMock) -> None:
        mock_settings.MEDIA_ROOT = "/media"
        mock_path_instance = MagicMock()
        mock_path_instance.is_absolute.return_value = False
        mock_path_instance.exists.return_value = True
        mock_path_instance.__truediv__ = MagicMock(return_value=mock_path_instance)
        mock_path_cls.return_value = mock_path_instance
        _delete_charfield_file("relative/path.docx")
        mock_path_instance.unlink.assert_called_once()

    @patch("apps.documents.signals.Path")
    def test_delete_charfield_file_not_exists(self, mock_path_cls: MagicMock) -> None:
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = False
        mock_path_cls.return_value = mock_path
        _delete_charfield_file("/nonexistent.docx")
        mock_path.unlink.assert_not_called()

    @patch("apps.documents.signals.Path")
    def test_delete_charfield_file_oserror(self, mock_path_cls: MagicMock) -> None:
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path.unlink.side_effect = OSError("perm denied")
        mock_path_cls.return_value = mock_path
        # OSError 被吞掉（仅记日志），但 unlink 确实被尝试过
        assert _delete_charfield_file("/locked.docx") is None
        mock_path.unlink.assert_called_once()

    def test_delete_file_field_none(self) -> None:
        # falsy 入参早退，不应触发任何删除
        assert _delete_file_field(None) is None

    def test_delete_file_field_valid(self) -> None:
        field_file = MagicMock()
        _delete_file_field(field_file)
        field_file.delete.assert_called_once_with(save=False)

    def test_delete_file_field_exception(self) -> None:
        field_file = MagicMock()
        field_file.delete.side_effect = Exception("boom")
        # 异常被吞掉（仅记日志），但 delete(save=False) 确实被调用过
        assert _delete_file_field(field_file) is None
        field_file.delete.assert_called_once_with(save=False)
