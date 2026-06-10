"""Documents Evidence Admin Views Mixin 测试 - 覆盖 documents/admin/evidence/mixins/views.py"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.http import JsonResponse, Http404
from django.contrib.auth import get_user_model

from apps.documents.admin.evidence.mixins.views import (
    EvidenceListAdminViewsMixin,
    EvidenceListAdminServiceMixin,
)
from apps.documents.models import EvidenceList

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
class TestDocumentsEvidenceServiceMixin:
    def test_get_admin_service(self):
        mixin = EvidenceListAdminServiceMixin()
        service = mixin._get_admin_service()
        assert service is not None


@pytest.mark.django_db
class TestDocumentsEvidenceViewsMixinDisplay:
    def test_total_pages_display_empty(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.total_pages = None
        assert mixin.total_pages_display(obj) == ""

    def test_total_pages_display_with_value(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.total_pages = 20
        assert mixin.total_pages_display(obj) == 20

    def test_case_display(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.case.name = "案件A"
        assert mixin.case_display(obj) == "案件A"

    def test_item_count_display_with_attr(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.item_count = 5
        assert mixin.item_count_display(obj) == 5

    def test_item_count_display_without_attr(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock(spec=EvidenceList)
        obj.items.count.return_value = 3
        assert mixin.item_count_display(obj) == 3

    def test_page_range_display(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.page_range_display = "1-20"
        assert mixin.page_range_display(obj) == "1-20"

    def test_order_range_display(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.order_range_display = "1-10"
        assert mixin.order_range_display(obj) == "1-10"

    def test_has_merged_pdf_processing(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "processing"
        obj.merge_progress = 50
        obj.merge_current = 5
        obj.merge_total = 10
        obj.merge_message = "合并中"
        result = str(mixin.has_merged_pdf_display(obj))
        assert "合并中" in result

    def test_has_merged_pdf_failed(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "failed"
        obj.merge_error = "错误"
        result = str(mixin.has_merged_pdf_display(obj))
        assert "失败" in result

    def test_has_merged_pdf_merged(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "completed"
        obj.merged_pdf = "path.pdf"
        result = str(mixin.has_merged_pdf_display(obj))
        assert "已合并" in result

    def test_has_merged_pdf_not_merged(self):
        mixin = EvidenceListAdminViewsMixin()
        obj = MagicMock()
        obj.merge_status = "pending"
        obj.merged_pdf = None
        result = str(mixin.has_merged_pdf_display(obj))
        assert "未合并" in result


@pytest.mark.django_db
class TestDocumentsEvidenceViewsMixinNextListType:
    def test_next_list_type_has_next(self):
        mixin = EvidenceListAdminViewsMixin()
        request = _make_request()
        with patch("apps.documents.admin.evidence.mixins.views.EvidenceList") as MockEL:
            MockEL.objects.filter.return_value.values_list.return_value = []
            result = mixin.next_list_type_view(request, case_id=1)
            assert result.status_code == 200


@pytest.mark.django_db
class TestDocumentsEvidenceViewsMixinReorder:
    def test_reorder_not_post(self):
        mixin = EvidenceListAdminViewsMixin()
        request = _make_request(method="GET")
        result = mixin.reorder_view(request, pk=1)
        assert result.status_code == 405

    def test_reorder_success(self):
        import json as json_mod

        mixin = EvidenceListAdminViewsMixin()
        factory = RequestFactory()
        request = factory.post(
            "/admin/reorder/",
            data=json_mod.dumps({"item_ids": [1, 2]}),
            content_type="application/json",
        )
        request.user = User(is_superuser=True, is_staff=True)
        with patch.object(mixin, "_get_admin_service") as mock_svc:
            mock_svc.return_value.reorder_items = MagicMock()
            result = mixin.reorder_view(request, pk=1)
            assert result.status_code == 200
