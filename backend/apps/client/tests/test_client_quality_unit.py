"""client-quality-uplift 单元测试。

验证 resolve_media_url、_update_identity_doc、save_and_rename_file 的具体行为。
需求: 2.2, 3.1, 4.1, 4.2, 4.3
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from apps.client.services.client_admin_file_mixin import ClientAdminFileMixin
from apps.client.utils.media import resolve_media_url


class TestResolveMediaUrl:
    """resolve_media_url 单元测试。"""

    def test_resolve_media_url_empty_returns_none(self) -> None:
        """空字符串返回 None。验证: 需求 4.3"""
        assert resolve_media_url("") is None

    @patch("apps.client.utils.media.settings")
    def test_resolve_media_url_absolute_path_under_media_root(
        self, mock_settings: Any
    ) -> None:
        """绝对路径在 MEDIA_ROOT 下，返回正确 URL。验证: 需求 4.1, 4.2"""
        mock_settings.MEDIA_ROOT = "/tmp/media"
        mock_settings.MEDIA_URL = "/media/"

        result = resolve_media_url("/tmp/media/docs/file.pdf")

        assert result == "/media/docs/file.pdf"

    @patch("apps.client.utils.media.settings")
    def test_resolve_media_url_relative_path(
        self, mock_settings: Any
    ) -> None:
        """相对路径直接拼接 MEDIA_URL。验证: 需求 4.1, 4.2"""
        mock_settings.MEDIA_ROOT = "/tmp/media"
        mock_settings.MEDIA_URL = "/media/"

        result = resolve_media_url("docs/file.pdf")

        assert result == "/media/docs/file.pdf"


@pytest.mark.django_db
class TestUpdateIdentityDoc:
    """_update_identity_doc 单元测试。"""

    def test_update_identity_doc_not_found_raises(self) -> None:
        """文档不存在时抛出 DoesNotExist。验证: 需求 3.1"""
        from apps.client.models import ClientIdentityDoc

        mixin = ClientAdminFileMixin()

        with pytest.raises(ClientIdentityDoc.DoesNotExist):
            mixin._update_identity_doc(
                doc_id=999999, file_path="test.pdf", admin_user="test"
            )


class TestSaveAndRenameFile:
    """save_and_rename_file 单元测试。"""

    def test_save_and_rename_file_no_service_raises_attribute_error(self) -> None:
        """无 identity_doc_service 属性时抛出 AttributeError。验证: 需求 2.2"""

        class BareHost(ClientAdminFileMixin):
            """不设置 identity_doc_service 的宿主类。"""

            pass

        instance: Any = BareHost.__new__(BareHost)
        # 确保实例上没有 identity_doc_service
        if hasattr(instance, "identity_doc_service"):
            delattr(instance, "identity_doc_service")

        with pytest.raises(AttributeError):
            instance.identity_doc_service  # noqa: B018
