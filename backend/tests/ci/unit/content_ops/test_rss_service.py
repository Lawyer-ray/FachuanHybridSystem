"""内容运营模块测试。"""

from __future__ import annotations

from apps.content_ops.services.rss_service import RSSService


class TestRSSService:
    """RSSService 测试。"""

    def setup_method(self) -> None:
        self.service = RSSService()

    def test_empty_feed(self) -> None:
        """生成空 RSS Feed。"""
        feed = self.service._empty_feed("https://example.com")
        assert '<?xml version="1.0"' in feed
        assert "法穿AI" in feed
        assert "法律故事播客" in feed
        assert "https://example.com" in feed

    def test_empty_feed_has_required_elements(self) -> None:
        """空 Feed 包含必需元素。"""
        feed = self.service._empty_feed("https://example.com")
        assert "<rss" in feed
        assert "<channel>" in feed
        assert "<title>" in feed
        assert "<link>" in feed
        assert "<description>" in feed
        assert "<language>" in feed

    def test_get_timezone_offset(self) -> None:
        """获取时区偏移。"""
        offset = self.service._get_timezone_offset()
        assert isinstance(offset, str)
        assert len(offset) > 0
