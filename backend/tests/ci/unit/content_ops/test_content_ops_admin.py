"""Content Ops Admin 测试 - ContentTaskAdmin, GeneratedArticleAdmin, PodcastEpisodeAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.content_ops.admin import ContentTaskAdmin, GeneratedArticleAdmin, PodcastEpisodeAdmin
from apps.content_ops.models import ContentTask, GeneratedArticle, PodcastEpisode

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestContentTaskAdmin:
    """ContentTaskAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ContentTaskAdmin(ContentTask, AdminSite())
        assert "id" in admin_obj.list_display
        assert "mode" in admin_obj.list_display
        assert "keyword" in admin_obj.list_display
        assert "status" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 mode 和 status"""
        admin_obj = ContentTaskAdmin(ContentTask, AdminSite())
        assert "mode" in admin_obj.list_filter
        assert "status" in admin_obj.list_filter

    def test_search_fields(self) -> None:
        """search_fields 包含 keyword"""
        admin_obj = ContentTaskAdmin(ContentTask, AdminSite())
        assert "keyword" in admin_obj.search_fields


@pytest.mark.django_db
class TestGeneratedArticleAdmin:
    """GeneratedArticleAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = GeneratedArticleAdmin(GeneratedArticle, AdminSite())
        assert "id" in admin_obj.list_display
        assert "task" in admin_obj.list_display
        assert "title" in admin_obj.list_display
        assert "review_status" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 review_status"""
        admin_obj = GeneratedArticleAdmin(GeneratedArticle, AdminSite())
        assert "review_status" in admin_obj.list_filter


@pytest.mark.django_db
class TestPodcastEpisodeAdmin:
    """PodcastEpisodeAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PodcastEpisodeAdmin(PodcastEpisode, AdminSite())
        assert "id" in admin_obj.list_display
        assert "task" in admin_obj.list_display
        assert "voice" in admin_obj.list_display
        assert "review_status" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 review_status"""
        admin_obj = PodcastEpisodeAdmin(PodcastEpisode, AdminSite())
        assert "review_status" in admin_obj.list_filter
