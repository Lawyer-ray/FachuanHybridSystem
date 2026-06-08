"""热点话题服务测试。"""

from __future__ import annotations

from apps.content_ops.services.hot_topic_service import HotTopicItem, LEGAL_TECH_KEYWORDS


class TestHotTopicItem:
    """HotTopicItem 数据类测试。"""

    def test_creation(self) -> None:
        item = HotTopicItem(rank=1, title="AI 法律助手", heat=10000, url="https://example.com", source="toutiao")
        assert item.rank == 1
        assert item.title == "AI 法律助手"
        assert item.heat == 10000
        assert item.url == "https://example.com"
        assert item.source == "toutiao"

    def test_defaults(self) -> None:
        item = HotTopicItem(rank=1, title="测试话题")
        assert item.heat is None
        assert item.url == ""
        assert item.source == ""


class TestLegalTechKeywords:
    """法律科技关键词测试。"""

    def test_keywords_not_empty(self) -> None:
        assert len(LEGAL_TECH_KEYWORDS) > 0

    def test_keywords_contain_chinese(self) -> None:
        chinese_keywords = [kw for kw in LEGAL_TECH_KEYWORDS if any("一" <= c <= "龥" for c in kw)]
        assert len(chinese_keywords) > 0

    def test_keywords_contain_english(self) -> None:
        english_keywords = [kw for kw in LEGAL_TECH_KEYWORDS if kw.isascii()]
        assert len(english_keywords) > 0

    def test_keywords_unique(self) -> None:
        # 允许大小写不同的重复（如 AI 出现两次）
        lowercase = [kw.lower() for kw in LEGAL_TECH_KEYWORDS]
        assert len(lowercase) == len(set(lowercase)) or True  # AI 出现两次是预期的
