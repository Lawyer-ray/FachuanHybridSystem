"""占位符渲染服务单元测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService, RenderStats


@pytest.fixture
def svc() -> PlaceholderRenderService:
    return PlaceholderRenderService()


# ── render ─────────────────────────────────────────────────────────────────

@patch("apps.litigation_ai.services.generation.placeholder_render_service.resolve_render_variable")
def test_render_single_brace_syntax(mock_resolve) -> None:
    """单花括号语法渲染。"""
    mock_resolve.return_value = (True, "张三")
    svc = PlaceholderRenderService()
    result, stats = svc.render("原告{原告名称}诉被告", {"plaintiff": "张三"}, syntax="single")
    assert "张三" in result
    assert "原告名称" in stats.placeholders_found


@patch("apps.litigation_ai.services.generation.placeholder_render_service.resolve_render_variable")
def test_render_double_brace_syntax(mock_resolve) -> None:
    """双花括号语法渲染。"""
    mock_resolve.return_value = (True, "张三")
    svc = PlaceholderRenderService()
    result, stats = svc.render("原告{{ 原告名称 }}诉被告", {"plaintiff": "张三"}, syntax="double")
    assert "张三" in result


@patch("apps.litigation_ai.services.generation.placeholder_render_service.resolve_render_variable")
def test_render_miss(mock_resolve) -> None:
    """占位符未命中。"""
    mock_resolve.return_value = (False, "{未匹配}")
    svc = PlaceholderRenderService()
    result, stats = svc.render("{未知字段}", {}, syntax="single")
    assert len(stats.placeholders_missed) == 1


def test_render_none_template(svc: PlaceholderRenderService) -> None:
    """None 模板处理为 空字符串。"""
    result, stats = svc.render(None, {})
    assert result == ""


def test_render_empty_template(svc: PlaceholderRenderService) -> None:
    """空模板返回空。"""
    result, stats = svc.render("", {})
    assert result == ""
    assert stats.placeholders_found == []


def test_render_no_placeholders(svc: PlaceholderRenderService) -> None:
    """无占位符的模板原样返回。"""
    result, stats = svc.render("普通文本", {})
    assert result == "普通文本"
    assert stats.placeholders_found == []


# ── RenderStats ────────────────────────────────────────────────────────────

def test_render_stats_hit_rate_all_hit() -> None:
    """全部命中 hit_rate = 1.0。"""
    stats = RenderStats(["a", "b"], ["a", "b"], [])
    assert stats.hit_rate == 1.0


def test_render_stats_hit_rate_partial() -> None:
    """部分命中 hit_rate < 1.0。"""
    stats = RenderStats(["a", "b"], ["a"], ["b"])
    assert stats.hit_rate == pytest.approx(0.5)


def test_render_stats_hit_rate_no_found() -> None:
    """无占位符 hit_rate = 1.0。"""
    stats = RenderStats([], [], [])
    assert stats.hit_rate == 1.0


def test_render_stats_missed() -> None:
    """missed = found - hit。"""
    stats = RenderStats(["a", "b", "c"], ["a"], ["b", "c"])
    assert len(stats.placeholders_missed) == 2
