"""Cloud Storage Admin 测试 - 覆盖 CloudStorageAccountAdmin"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory

from apps.cloud_storage.admin import (
    CloudStorageAccountAdmin,
    _clear_dropbox_pending,
    _clear_onedrive_pending,
    _pending_auth,
    resume_pending_device_code_polls,
)
from apps.cloud_storage.models import CloudStorageAccount

User = get_user_model()


def _make_admin():
    return CloudStorageAccountAdmin(CloudStorageAccount, AdminSite())


def _make_request(method="GET", path="/admin/"):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path)
    else:
        request = factory.post(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestCloudStorageAccountAdminAttributes:
    """验证 Admin 配置属性"""

    def test_list_display(self):
        admin = _make_admin()
        assert "name" in admin.list_display
        assert "storage_type" in admin.list_display
        assert "is_active" in admin.list_display
        assert "onedrive_status" in admin.list_display
        assert "dropbox_status" in admin.list_display

    def test_list_filter(self):
        admin = _make_admin()
        assert "storage_type" in admin.list_filter
        assert "is_active" in admin.list_filter

    def test_search_fields(self):
        admin = _make_admin()
        assert "name" in admin.search_fields

    def test_fieldsets(self):
        admin = _make_admin()
        assert isinstance(admin.fieldsets, list)
        fieldset_titles = [f[0] for f in admin.fieldsets]
        assert "基本信息" in fieldset_titles
        assert "WebDAV 设置" in fieldset_titles
        assert "OneDrive" in fieldset_titles
        assert "S3 兼容存储" in fieldset_titles
        assert "Google Drive" in fieldset_titles
        assert "Dropbox" in fieldset_titles
        assert "本地文件系统" in fieldset_titles


@pytest.mark.django_db
class TestCloudStorageAccountAdminDisplayMethods:
    """测试 display 方法"""

    def test_onedrive_status_not_onedrive(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.storage_type = "webdav"
        assert admin.onedrive_status(obj) == "-"

    def test_onedrive_status_authorized(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.storage_type = "onedrive"
        obj.onedrive_refresh_token = "some_token"
        result = str(admin.onedrive_status(obj))
        assert "已授权" in result

    def test_onedrive_status_not_authorized(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.storage_type = "onedrive"
        obj.onedrive_refresh_token = ""
        result = str(admin.onedrive_status(obj))
        assert "未授权" in result

    def test_dropbox_status_not_dropbox(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.storage_type = "webdav"
        assert admin.dropbox_status(obj) == "-"

    def test_dropbox_status_authorized(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.storage_type = "dropbox"
        obj.dropbox_refresh_token = "some_token"
        result = str(admin.dropbox_status(obj))
        assert "已授权" in result

    def test_dropbox_status_not_authorized(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.storage_type = "dropbox"
        obj.dropbox_refresh_token = ""
        result = str(admin.dropbox_status(obj))
        assert "未授权" in result


@pytest.mark.django_db
class TestCloudStorageAccountAdminReadonlyFields:
    """测试 get_readonly_fields"""

    def test_get_readonly_fields_new(self):
        admin = _make_admin()
        request = _make_request()
        fields = admin.get_readonly_fields(request, obj=None)
        assert "storage_type" not in fields

    def test_get_readonly_fields_edit_onedrive(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.pk = 1
        obj.storage_type = "onedrive"
        fields = admin.get_readonly_fields(request, obj=obj)
        assert "storage_type" in fields
        assert "onedrive_token_expires_at" in fields

    def test_get_readonly_fields_edit_dropbox(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.pk = 1
        obj.storage_type = "dropbox"
        fields = admin.get_readonly_fields(request, obj=obj)
        assert "storage_type" in fields
        assert "dropbox_token_expires_at" in fields


@pytest.mark.django_db
class TestCloudStorageAccountAdminChangeformView:
    """测试 changeform_view 额外上下文"""

    def test_changeform_view_new(self):
        admin = _make_admin()
        request = _make_request()
        with patch.object(
            CloudStorageAccountAdmin.__bases__[0], "changeform_view", return_value=HttpResponse()
        ) as mock_super:
            result = admin.changeform_view(request, object_id=None)
            assert result.status_code == 200
            # 新建表单（无 object_id）不注入授权上下文
            mock_super.assert_called_once()
            ctx = mock_super.call_args.args[3]
            assert "show_onedrive_auth" not in ctx

    def test_changeform_view_edit_onedrive(self):
        admin = _make_admin()
        request = _make_request()
        account = MagicMock()
        account.pk = 1
        account.storage_type = "onedrive"
        account.onedrive_refresh_token = ""
        account.onedrive_pending_device_code = ""
        with patch.object(
            CloudStorageAccountAdmin.__bases__[0], "changeform_view", return_value=HttpResponse()
        ) as mock_super:
            with patch.object(CloudStorageAccount.objects, "get", return_value=account):
                result = admin.changeform_view(request, object_id=1)
                assert result.status_code == 200
                # OneDrive 账号应注入授权面板上下文
                mock_super.assert_called_once()
                ctx = mock_super.call_args.args[3]
                assert ctx["show_onedrive_auth"] is True
                assert ctx["onedrive_account_id"] == 1
                # 无 pending 设备码、无 refresh token：pending 为 falsy，authorized 为 False
                assert not ctx["onedrive_pending"]
                assert ctx["onedrive_authorized"] is False
                assert ctx["show_dropbox_auth"] is False


@pytest.mark.django_db
class TestCloudStorageAccountAdminAuthViews:
    """测试 OneDrive/Dropbox 授权视图"""

    def test_start_auth_view_not_post(self):
        admin = _make_admin()
        request = _make_request(method="GET")
        result = admin._start_auth_view(request, object_id=1)
        assert result.status_code == 302
        # GET 请求直接弹回账号 change 页
        assert result.url.endswith("/admin/cloud_storage/cloudstorageaccount/1/change/")

    def test_start_dropbox_auth_view_not_post(self):
        admin = _make_admin()
        request = _make_request(method="GET")
        result = admin._start_dropbox_auth_view(request, object_id=1)
        assert result.status_code == 302
        assert result.url.endswith("/admin/cloud_storage/cloudstorageaccount/1/change/")


@pytest.mark.django_db
class TestCloudStoragePendingAuthHelpers:
    """测试 pending auth 辅助函数"""

    def test_clear_onedrive_pending(self):
        _pending_auth[999] = {"user_code": "test"}
        _clear_onedrive_pending(999)
        assert 999 not in _pending_auth

    def test_clear_dropbox_pending(self):
        _pending_auth[999] = {"user_code": "test"}
        _clear_dropbox_pending(999)
        assert 999 not in _pending_auth


@pytest.mark.django_db
class TestResumePendingDeviceCodePolls:
    """测试 resume_pending_device_code_polls"""

    def test_resume_pending_no_pending(self):
        # Should not raise
        assert resume_pending_device_code_polls() is None


class TestCloudStorageAdminAssetsLocation:
    """admin 模板与 JS 已从 apps/core 迁入 apps/cloud_storage（app 自有资产就近存放）。

    验证 TEMPLATES APP_DIRS / staticfiles AppDirectoriesFinder 在新路径下仍能解析，
    ``CloudStorageAccountAdmin.change_form_template`` 与 ``Media.js`` 引用不受搬迁影响。
    """

    def test_change_form_template_resolves_to_cloud_storage_app(self):
        from django.template.loader import get_template

        template = get_template(CloudStorageAccountAdmin.change_form_template)
        # _EngineTemplate 的 origin 属性未入 django-stubs，用 getattr 桥接
        origin = getattr(template, "origin", None)
        assert origin is not None, "模板应能从 cloud_storage app 目录解析出 origin"
        assert str(origin.name).endswith("apps/cloud_storage/templates/admin/cloud_storage/change_form.html")

    def test_admin_js_found_in_cloud_storage_app_static(self):
        from django.contrib.staticfiles import finders

        js_rel = CloudStorageAccountAdmin.Media.js[0]
        found = finders.find(js_rel)
        assert found is not None
        assert found.endswith("apps/cloud_storage/static/admin/js/cloud_storage_admin.js")
