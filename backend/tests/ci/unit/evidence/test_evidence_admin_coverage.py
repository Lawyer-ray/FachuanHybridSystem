"""Evidence Admin Views Mixin 测试 - 覆盖 EvidenceListAdminViewsMixin"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.http import JsonResponse, Http404

from apps.evidence.admin.evidence.mixins.views import (
    EvidenceListAdminViewsMixin,
    EvidenceListAdminServiceMixin,
)
from apps.evidence.models import EvidenceList

User = get_user_model()


def _make_request(method="GET", path="/admin/", data=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {})
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestEvidenceListAdminServiceMixin:
    """测试 _get_admin_service"""

    def test_get_admin_service(self):
        mixin = EvidenceListAdminServiceMixin()
        service = mixin._get_admin_service()
        assert service is not None


@pytest.mark.django_db
class TestEvidenceListAdminViewsMixinDisplayMethods:
    """测试 display 方法"""

    def test_total_pages_display_empty(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.total_pages = None
        assert mixin.total_pages_display(obj) == ""

    def test_total_pages_display_with_value(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.total_pages = 42
        assert mixin.total_pages_display(obj) == 42

    def test_case_display(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.case.name = "测试案件"
        assert mixin.case_display(obj) == "测试案件"

    def test_item_count_display_with_attr(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.item_count = 15
        assert mixin.item_count_display(obj) == 15

    def test_item_count_display_without_attr(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock(spec=EvidenceList)
        obj.items.count.return_value = 8
        result = mixin.item_count_display(obj)
        assert result == 8

    def test_page_range_display(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.page_range_display = "1-10"
        assert mixin.page_range_display(obj) == "1-10"

    def test_order_range_display(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.order_range_display = "1-5"
        assert mixin.order_range_display(obj) == "1-5"

    def test_has_merged_pdf_display_processing(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "processing"
        obj.merge_progress = 50
        obj.merge_current = 5
        obj.merge_total = 10
        obj.merge_message = "合并中"
        result = str(mixin.has_merged_pdf_display(obj))
        assert "合并中" in result

    def test_has_merged_pdf_display_failed(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "failed"
        obj.merge_error = "磁盘空间不足"
        result = str(mixin.has_merged_pdf_display(obj))
        assert "失败" in result

    def test_has_merged_pdf_display_merged(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "completed"
        obj.merged_pdf = "/some/path.pdf"
        result = str(mixin.has_merged_pdf_display(obj))
        assert "已合并" in result

    def test_has_merged_pdf_display_not_merged(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "pending"
        obj.merged_pdf = None
        result = str(mixin.has_merged_pdf_display(obj))
        assert "未合并" in result


@pytest.mark.django_db
class TestEvidenceListAdminViewsMixinNextListType:
    """测试 next_list_type_view"""

    def test_next_list_type_view_has_next(self):
        import json

        mixin = EvidenceListAdminViewsMixin()
        request = _make_request()
        with patch("apps.evidence.admin.evidence.mixins.views.EvidenceList") as MockEL:
            MockEL.objects.filter.return_value.values_list.return_value = []
            result = mixin.next_list_type_view(request, case_id=1)
            assert result.status_code == 200
            data = json.loads(result.content)
            assert data["success"] is True

    def test_next_list_type_view_all_used(self):
        import json

        mixin = EvidenceListAdminViewsMixin()
        request = _make_request()
        with patch("apps.evidence.admin.evidence.mixins.views.EvidenceList") as MockEL:
            from apps.evidence.models import ListType

            all_types = [t[0] for t in ListType.choices]
            MockEL.objects.filter.return_value.values_list.return_value = all_types
            result = mixin.next_list_type_view(request, case_id=1)
            assert result.status_code == 200
            data = json.loads(result.content)
            assert data["success"] is False


@pytest.mark.django_db
class TestEvidenceListAdminViewsMixinReorder:
    """测试 reorder_view"""

    def test_reorder_view_not_post(self):
        mixin = EvidenceListAdminViewsMixin()
        request = _make_request(method="GET")
        result = mixin.reorder_view(request, pk=1)
        assert result.status_code == 405

    def test_reorder_view_success(self):
        import json as json_mod

        mixin = EvidenceListAdminViewsMixin()
        factory = RequestFactory()
        request = factory.post(
            "/admin/reorder/",
            data=json_mod.dumps({"item_ids": [1, 2, 3]}),
            content_type="application/json",
        )
        request.user = User(is_superuser=True, is_staff=True)
        with patch.object(mixin, "_get_admin_service") as mock_svc:
            mock_svc.return_value.reorder_items = MagicMock()
            result = mixin.reorder_view(request, pk=1)
            assert result.status_code == 200


@pytest.mark.django_db
class TestEvidenceListAdminViewsMixinMergeStatus:
    """测试 merge_status_view"""

    def test_merge_status_view_not_found(self):
        mixin = EvidenceListAdminViewsMixin()
        request = _make_request()
        with patch("apps.evidence.admin.evidence.mixins.views.EvidenceList") as MockEL:
            MockEL.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockEL.objects.select_related.return_value.get.side_effect = MockEL.DoesNotExist()
            result = mixin.merge_status_view(request, pk=999999)
            assert result.status_code == 404
