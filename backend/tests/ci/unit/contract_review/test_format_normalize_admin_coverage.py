"""Tests for contract_review.admin.format_normalize_admin — increase coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.contract_review.admin.format_normalize_admin import FormatNormalizeAdmin


class TestFormatNormalizeAdminAttributes:
    def _make_admin(self):
        from apps.contract_review.models import FormatNormalize

        return FormatNormalizeAdmin(FormatNormalize, MagicMock())

    def test_list_display(self) -> None:
        admin = self._make_admin()
        assert "contract_title" in admin.list_display
        assert "status" in admin.list_display
        assert "format_action" in admin.list_display

    def test_list_filter(self) -> None:
        admin = self._make_admin()
        assert "status" in admin.list_filter

    def test_search_fields(self) -> None:
        admin = self._make_admin()
        assert "contract_title" in admin.search_fields

    def test_readonly_fields(self) -> None:
        admin = self._make_admin()
        assert "id" in admin.readonly_fields
        assert "status" in admin.readonly_fields
        assert "created_at" in admin.readonly_fields

    def test_has_add_permission(self) -> None:
        admin = self._make_admin()
        assert admin.has_add_permission(MagicMock()) is False

    def test_has_change_permission(self) -> None:
        admin = self._make_admin()
        assert admin.has_change_permission(MagicMock()) is False

    def test_has_delete_permission(self) -> None:
        admin = self._make_admin()
        assert admin.has_delete_permission(MagicMock()) is False


class TestFormatNormalizeAdminDisplayMethods:
    def _make_admin(self):
        from apps.contract_review.models import FormatNormalize

        return FormatNormalizeAdmin(FormatNormalize, MagicMock())

    def test_format_action_no_original_file(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.original_file = None
        result = admin.format_action(obj)
        assert result == "—"

    def test_format_action_with_output_file(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.original_file = "test.docx"
        obj.output_file = "test_normalized.docx"
        result = admin.format_action(obj)
        result_str = str(result)
        assert "下载" in result_str
        assert "重新格式化" in result_str

    def test_format_action_without_output_poi_available(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.original_file = "test.docx"
        obj.output_file = None
        with patch("apps.core.services.poi_client.get_poi_client") as mock_poi:
            mock_poi.return_value.health_check.return_value = True
            result = admin.format_action(obj)
            result_str = str(result)
            assert "格式化" in result_str

    def test_format_action_without_output_poi_unavailable(self) -> None:
        admin = self._make_admin()
        obj = MagicMock()
        obj.pk = 1
        obj.original_file = "test.docx"
        obj.output_file = None
        with patch("apps.core.services.poi_client.get_poi_client") as mock_poi:
            mock_poi.return_value.health_check.return_value = False
            result = admin.format_action(obj)
            result_str = str(result)
            assert "Python" in result_str

    def test_get_fieldsets(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        fieldsets = admin.get_fieldsets(request)
        assert isinstance(fieldsets, list)
        assert len(fieldsets) == 3
        # Check names
        assert fieldsets[0][0] is None
        assert fieldsets[1][0] == "文件"
        assert fieldsets[2][0] == "时间"


class TestFormatNormalizeAdminFindReferenceDocument:
    def _make_admin(self):
        from apps.contract_review.models import FormatNormalize

        return FormatNormalizeAdmin(FormatNormalize, MagicMock())

    def test_find_reference_no_dir(self) -> None:
        admin = self._make_admin()
        test_path = Path("/some/path/电脑维护合同[测试集].docx")
        with patch("apps.contract_review.admin.format_normalize_admin.Path") as mock_path_cls:
            # Simulate that the verification dir doesn't exist
            mock_home = MagicMock()
            mock_downloads = MagicMock()
            mock_verification = MagicMock()
            mock_verification.exists.return_value = False
            mock_home.__truediv__ = MagicMock(return_value=mock_downloads)
            mock_downloads.__truediv__ = MagicMock(return_value=mock_verification)
            mock_path_cls.home.return_value = mock_home
            result = admin._find_reference_document(test_path)
            assert result is None

    def test_find_reference_no_bracket_match(self) -> None:
        admin = self._make_admin()
        test_path = Path("/some/path/电脑维护合同.docx")
        result = admin._find_reference_document(test_path)
        # This should return None because there's no bracket match
        assert result is None

    def test_find_reference_with_candidates(self) -> None:
        admin = self._make_admin()
        test_path = Path("/some/path/电脑维护合同[测试集].docx")
        mock_candidate = MagicMock()
        mock_candidate.name = "电脑维护合同[验证集].docx"
        mock_candidate.stat.return_value.st_mtime = 1000
        with patch("apps.contract_review.admin.format_normalize_admin.Path") as mock_path_cls:
            mock_verification = MagicMock()
            mock_verification.exists.return_value = True
            mock_verification.glob.return_value = [mock_candidate]
            mock_downloads = MagicMock()
            mock_downloads.__truediv__ = MagicMock(return_value=mock_verification)
            mock_home = MagicMock()
            mock_home.__truediv__ = MagicMock(return_value=mock_downloads)
            mock_path_cls.home.return_value = mock_home
            result = admin._find_reference_document(test_path)
            assert result == mock_candidate


class TestFormatNormalizeAdminViews:
    def _make_admin(self):
        from apps.contract_review.models import FormatNormalize

        return FormatNormalizeAdmin(FormatNormalize, MagicMock())

    def test_execute_view_task_not_found(self) -> None:
        from apps.contract_review.models import ReviewTask as RT

        admin = self._make_admin()
        request = MagicMock()
        with patch("apps.contract_review.models.ReviewTask.objects.get", side_effect=RT.DoesNotExist("not found")):
            result = admin.execute_view(request, "fake-id")
            assert result.status_code == 302

    def test_add_annotation_view_task_not_found(self) -> None:
        from apps.contract_review.models import ReviewTask as RT

        admin = self._make_admin()
        request = MagicMock()
        request.method = "POST"
        request.POST = {"annotation_content": "test annotation"}
        request.user = MagicMock()
        request.user.get_full_name.return_value = "Test User"
        request.user.username = "testuser"
        with patch("apps.contract_review.models.ReviewTask.objects.get", side_effect=RT.DoesNotExist("not found")):
            result = admin.add_annotation_view(request, "fake-id")
            assert result.status_code == 302

    def test_delete_view_task_not_found(self) -> None:
        from apps.contract_review.models import ReviewTask as RT

        admin = self._make_admin()
        request = MagicMock()
        with patch("apps.contract_review.models.ReviewTask.objects.get", side_effect=RT.DoesNotExist("not found")):
            result = admin.delete_view(request, "fake-id")
            assert result.status_code == 302

    def test_batch_execute_view_no_tasks(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        with patch("apps.contract_review.models.ReviewTask.objects.filter") as mock_filter:
            mock_filter.return_value.exists.return_value = False
            result = admin.batch_execute_view(request)
            assert result.status_code == 302

    def test_batch_delete_view_no_tasks(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        with patch("apps.contract_review.models.ReviewTask.objects.filter") as mock_filter:
            mock_filter.return_value.exists.return_value = False
            result = admin.batch_delete_view(request)
            assert result.status_code == 302

    def test_health_check_view(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        with patch("apps.core.services.poi_client.get_poi_client") as mock_poi:
            mock_poi.return_value.health_check.return_value = True
            result = admin.health_check_view(request)
            data = json.loads(result.content)
            assert data["poi_service"]["available"] is True
            assert data["poi_service"]["status"] == "online"

    def test_health_check_view_offline(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        with patch("apps.core.services.poi_client.get_poi_client") as mock_poi:
            mock_poi.return_value.health_check.return_value = False
            result = admin.health_check_view(request)
            data = json.loads(result.content)
            assert data["poi_service"]["available"] is False
            assert data["poi_service"]["status"] == "offline"

    def test_upload_view_not_post(self) -> None:
        admin = self._make_admin()
        request = MagicMock()
        request.method = "GET"
        request.FILES = {}
        request.POST = {}
        with patch("apps.core.services.poi_client.get_poi_client") as mock_poi:
            mock_poi.return_value.health_check.return_value = True
            with patch.object(admin, "admin_site") as mock_site:
                mock_site.each_context.return_value = {}
                mock_site.name = "admin"
                result = admin.upload_view(request)
                # GET returns TemplateResponse
                assert result.status_code == 200
