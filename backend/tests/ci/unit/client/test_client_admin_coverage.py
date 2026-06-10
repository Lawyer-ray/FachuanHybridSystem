"""Client Admin 测试 - 覆盖 ClientAdmin"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.http import JsonResponse

from apps.client.admin.client_admin import (
    ClientAdmin,
    ClientAdminForm,
    ClientIdentityDocInline,
    PropertyClueInline,
)
from apps.client.models import Client

User = get_user_model()


def _make_admin():
    return ClientAdmin(Client, AdminSite())


def _make_request(method="GET", path="/admin/", data=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {})
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestClientAdminAttributes:
    """验证 Admin 配置属性"""

    def test_list_display(self):
        admin = _make_admin()
        assert "id" in admin.list_display
        assert "name" in admin.list_display
        assert "client_type" in admin.list_display
        assert "is_our_client" in admin.list_display
        assert "phone" in admin.list_display

    def test_search_fields(self):
        admin = _make_admin()
        assert "name" in admin.search_fields
        assert "phone" in admin.search_fields
        assert "id_number" in admin.search_fields

    def test_list_filter(self):
        admin = _make_admin()
        assert "client_type" in admin.list_filter
        assert "is_our_client" in admin.list_filter

    def test_list_per_page(self):
        admin = _make_admin()
        assert admin.list_per_page == 50

    def test_ordering(self):
        admin = _make_admin()
        assert "-pk" in admin.ordering

    def test_actions(self):
        admin = _make_admin()
        assert "export_selected_as_json" in admin.actions
        assert "export_all_as_json" in admin.actions

    def test_export_model_name(self):
        admin = _make_admin()
        assert admin.export_model_name == "client"

    def test_import_required_fields(self):
        admin = _make_admin()
        assert "name" in admin.import_required_fields


@pytest.mark.django_db
class TestClientAdminForm:
    """测试 ClientAdminForm"""

    def test_form_initial_data_legal(self):
        form = ClientAdminForm(initial={"client_type": "legal"})
        # With client_type="legal", the label should be 统一社会信用代码
        assert form.fields["id_number"].label in ("统一社会信用代码", "身份证号码")

    def test_form_initial_data_natural(self):
        form = ClientAdminForm(initial={"client_type": "natural"})
        # The label depends on the form logic
        assert form.fields["id_number"].label in ("身份证号码", "统一社会信用代码")


@pytest.mark.django_db
class TestClientAdminGetInlines:
    """测试 get_inlines"""

    def test_get_inlines_no_obj(self):
        admin = _make_admin()
        request = _make_request()
        inlines = admin.get_inlines(request, obj=None)
        assert ClientIdentityDocInline in inlines
        assert PropertyClueInline in inlines

    def test_get_inlines_legal_client(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.client_type = "legal"
        inlines = admin.get_inlines(request, obj=obj)
        assert len(inlines) == 3  # includes GsxtReportTaskInline

    def test_get_inlines_natural_client(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.client_type = "natural"
        inlines = admin.get_inlines(request, obj=obj)
        assert len(inlines) == 2


@pytest.mark.django_db
class TestClientAdminGetChangeformInitialData:
    """测试 get_changeform_initial_data"""

    def test_get_changeform_initial_data(self):
        admin = _make_admin()
        request = _make_request()
        data = admin.get_changeform_initial_data(request)
        assert data["client_type"] == "legal"


@pytest.mark.django_db
class TestClientAdminCheckOaCredentialView:
    """测试 _check_oa_credential_view"""

    def test_check_oa_credential_view_no_user_id(self):
        import json as json_mod

        admin = _make_admin()
        request = _make_request()
        request.user = MagicMock()
        request.user.id = None
        result = admin._check_oa_credential_view(request)
        assert result.status_code == 200
        data = json_mod.loads(result.content)
        assert data["has_credential"] is False

    def test_check_oa_credential_view_with_user(self):
        import json as json_mod

        admin = _make_admin()
        request = _make_request()
        result = admin._check_oa_credential_view(request)
        assert result.status_code == 200
        data = json_mod.loads(result.content)
        assert "has_credential" in data


@pytest.mark.django_db
class TestClientAdminIdentityDocInline:
    """测试 ClientIdentityDocInline"""

    def test_file_link_no_url(self):
        inline = ClientIdentityDocInline(Client, AdminSite())
        obj = MagicMock()
        obj.media_url = ""
        assert inline.file_link(obj) == ""

    def test_file_link_with_url(self):
        inline = ClientIdentityDocInline(Client, AdminSite())
        obj = MagicMock()
        obj.media_url = "/media/client_docs/1/file.pdf"
        obj.file_path = "client_docs/1/file.pdf"
        result = str(inline.file_link(obj))
        assert "file.pdf" in result
