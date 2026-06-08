"""Unit tests for contracts.admin.mixins.archive_mixin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestContractArchiveMixinPermissionChecks:
    """测试归档 mixin 的权限检查"""

    def _make_mixin(self):
        from apps.contracts.admin.mixins.archive_mixin import ContractArchiveMixin

        mixin = ContractArchiveMixin()
        mixin.has_view_permission = MagicMock(return_value=True)
        mixin.has_change_permission = MagicMock(return_value=True)
        mixin.admin_site = MagicMock()
        mixin.model = MagicMock()
        return mixin

    def test_generate_archive_docs_no_permission(self) -> None:
        mixin = self._make_mixin()
        mixin.has_change_permission.return_value = False
        request = MagicMock()
        result = mixin.generate_archive_docs_view(request, 1)
        assert result.status_code == 403

    def test_generate_single_archive_doc_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.generate_single_archive_doc_view(request, 1, "code")
        assert result.status_code == 405

    def test_generate_single_archive_doc_no_permission(self) -> None:
        mixin = self._make_mixin()
        mixin.has_change_permission.return_value = False
        request = MagicMock()
        request.method = "POST"
        result = mixin.generate_single_archive_doc_view(request, 1, "code")
        assert result.status_code == 403

    def test_download_archive_item_no_permission(self) -> None:
        mixin = self._make_mixin()
        mixin.has_view_permission.return_value = False
        request = MagicMock()
        with pytest.raises(Exception):  # PermissionDenied  # noqa: B017
            mixin.download_archive_item_view(request, 1, "code")

    def test_detect_supervision_card_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.detect_supervision_card_view(request, 1)
        assert result.status_code == 405

    def test_detect_supervision_card_no_permission(self) -> None:
        mixin = self._make_mixin()
        mixin.has_change_permission.return_value = False
        request = MagicMock()
        request.method = "POST"
        result = mixin.detect_supervision_card_view(request, 1)
        assert result.status_code == 403

    def test_sync_case_materials_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.sync_case_materials_view(request, 1)
        assert result.status_code == 405

    def test_reset_and_resync_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.reset_and_resync_case_materials_view(request, 1)
        assert result.status_code == 405

    def test_toggle_compact_archive_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.toggle_compact_archive_view(request, 1)
        assert result.status_code == 405

    def test_scale_to_a4_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.scale_to_a4_view(request, 1)
        assert result.status_code == 405

    def test_reorder_archive_materials_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.reorder_archive_materials_view(request, 1)
        assert result.status_code == 405

    def test_move_archive_material_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.move_archive_material_view(request, 1)
        assert result.status_code == 405

    def test_upload_archive_item_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.upload_archive_item_view(request, 1, "code")
        assert result.status_code == 405

    def test_delete_archive_material_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.delete_archive_material_view(request, 1, 1)
        assert result.status_code == 405

    def test_clear_all_archive_materials_wrong_method(self) -> None:
        mixin = self._make_mixin()
        request = MagicMock()
        request.method = "GET"
        result = mixin.clear_all_archive_materials_view(request, 1)
        assert result.status_code == 405

    def test_case_material_match_map_no_permission(self) -> None:
        mixin = self._make_mixin()
        mixin.has_view_permission.return_value = False
        request = MagicMock()
        with pytest.raises(Exception):  # noqa: B017
            mixin.case_material_match_map_view(request, 1)

    def test_preview_archive_material_no_permission(self) -> None:
        mixin = self._make_mixin()
        mixin.has_view_permission.return_value = False
        request = MagicMock()
        with pytest.raises(Exception):  # noqa: B017
            mixin.preview_archive_material_view(request, 1, 1)
