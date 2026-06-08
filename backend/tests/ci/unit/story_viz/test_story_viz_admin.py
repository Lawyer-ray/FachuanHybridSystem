"""Story Viz Admin 测试 - StoryAnimationAdmin"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.story_viz.admin.story_animation_admin import StoryAnimationAdmin
from apps.story_viz.models import StoryAnimation

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestStoryAnimationAdmin:
    """StoryAnimationAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        assert "source_title" in admin_obj.list_display
        assert "viz_type_display" in admin_obj.list_display
        assert "status_badge" in admin_obj.list_display
        assert "stage_display" in admin_obj.list_display
        assert "progress_display" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 status"""
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        assert "status" in admin_obj.list_filter

    def test_search_fields(self) -> None:
        """search_fields 包含 source_title"""
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        assert "source_title" in admin_obj.search_fields

    def test_status_badge(self) -> None:
        """status_badge 应返回带颜色的状态"""
        animation = StoryAnimation.objects.create(
            source_title="测试动画",
            source_text="测试内容",
            viz_type="timeline",
            status="pending",
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.status_badge(animation)
        assert "color" in result

    def test_viz_type_display(self) -> None:
        """viz_type_display 应返回类型显示名称"""
        animation = StoryAnimation.objects.create(
            source_title="类型测试动画",
            source_text="类型测试内容",
            viz_type="timeline",
            status="pending",
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.viz_type_display(animation)
        assert len(result) > 0

    def test_duration_with_times(self) -> None:
        """duration 应计算耗时"""
        now = timezone.now()
        animation = StoryAnimation.objects.create(
            source_title="耗时测试动画",
            source_text="耗时测试内容",
            viz_type="timeline",
            status="completed",
            started_at=now - timedelta(seconds=30),
            finished_at=now,
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.duration(animation)
        assert "30 秒" in result

    def test_duration_without_start_time(self) -> None:
        """duration 无开始时间时应返回破折号"""
        animation = StoryAnimation.objects.create(
            source_title="无时间动画",
            source_text="无时间内容",
            viz_type="timeline",
            status="pending",
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.duration(animation)
        assert result == "-"

    def test_facts_payload_display_with_data(self) -> None:
        """facts_payload_display 应显示事实数据统计"""
        animation = StoryAnimation.objects.create(
            source_title="事实数据动画",
            source_text="事实数据内容",
            viz_type="timeline",
            status="pending",
            facts_payload={"events": [{"name": "事件1"}, {"name": "事件2"}], "parties": [{"name": "人物1"}]},
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.facts_payload_display(animation)
        assert "事件节点: 2 个" in result
        assert "人物节点: 1 个" in result

    def test_facts_payload_display_empty(self) -> None:
        """facts_payload_display 无数据时应显示'无数据'"""
        animation = StoryAnimation.objects.create(
            source_title="空数据动画",
            source_text="空数据内容",
            viz_type="timeline",
            status="pending",
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.facts_payload_display(animation)
        assert "无数据" in result

    def test_script_payload_display_with_data(self) -> None:
        """script_payload_display 应显示脚本数据统计"""
        animation = StoryAnimation.objects.create(
            source_title="脚本数据动画",
            source_text="脚本数据内容",
            viz_type="timeline",
            status="pending",
            script_payload={
                "timeline_nodes": [{"name": "节点1"}],
                "relationship_nodes": [{"name": "关系1"}],
                "edges": [{"source": "A", "target": "B"}],
            },
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.script_payload_display(animation)
        assert "时间线节点: 1 个" in result
        assert "关系节点: 1 个" in result
        assert "关系连线: 1 条" in result

    def test_render_payload_display_with_data(self) -> None:
        """render_payload_display 应显示渲染数据统计"""
        animation = StoryAnimation.objects.create(
            source_title="渲染数据动画",
            source_text="渲染数据内容",
            viz_type="timeline",
            status="pending",
            render_payload={"nodes": [{"id": 1}, {"id": 2}], "edges": [{"source": 1, "target": 2}]},
        )
        admin_obj = StoryAnimationAdmin(StoryAnimation, AdminSite())
        result = admin_obj.render_payload_display(animation)
        assert "节点: 2 个" in result
        assert "连线: 1 条" in result
