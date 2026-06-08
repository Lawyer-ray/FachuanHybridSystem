"""法院短信推荐服务、验证码识别器、智能填充服务、文件准备服务测试。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.automation.services.sms.court_sms_recommendation_service import (
    RecommendationResult,
    _COURT_NAME_PATTERN,
    _YEAR_COURT_PREFIX_PATTERN,
)
from apps.automation.services.scraper.core.captcha_recognizer import CaptchaRecognizer
from apps.documents.services.smart_fill.service import (
    PlaceholderResult,
    SmartFillResult,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    AUTO_FILL_KEYS,
)
from apps.batch_printing.services.job.file_prepare_service import FilePrepareService


class TestRecommendationResult:
    """RecommendationResult 数据类测试。"""

    def test_creation(self) -> None:
        result = RecommendationResult(
            case_id=1,
            case_name="张三诉李四",
            score=100,
            reasons=["案号匹配"],
            case_numbers=["（2025）粤0604民初12345号"],
            parties=["张三", "李四"],
            court_names=["佛山市禅城区人民法院"],
            status="active",
        )
        assert result.case_id == 1
        assert result.score == 100
        assert "案号匹配" in result.reasons

    def test_defaults(self) -> None:
        result = RecommendationResult(case_id=1, case_name="test", score=0)
        assert result.reasons == []
        assert result.case_numbers == []
        assert result.parties == []
        assert result.court_names == []
        assert result.status == ""


class TestCourtNamePattern:
    """法院名称正则测试。"""

    def test_match_court_name(self) -> None:
        assert _COURT_NAME_PATTERN.search("佛山市禅城区人民法院") is not None
        assert _COURT_NAME_PATTERN.search("广东省高级人民法院") is not None

    def test_no_match_non_court(self) -> None:
        assert _COURT_NAME_PATTERN.search("普通文本") is None


class TestYearCourtPrefixPattern:
    """年份法院代码前缀正则测试。"""

    def test_match_prefix(self) -> None:
        match = _YEAR_COURT_PREFIX_PATTERN.search("（2025）粤0605民初123号")
        assert match is not None
        assert match.group(1) == "2025"

    def test_no_match_empty(self) -> None:
        assert _YEAR_COURT_PREFIX_PATTERN.search("普通文本") is None


class TestCaptchaRecognizer:
    """CaptchaRecognizer 抽象接口测试。"""

    def test_abstract_methods(self) -> None:
        """验证抽象方法存在。"""
        assert hasattr(CaptchaRecognizer, "recognize")
        assert hasattr(CaptchaRecognizer, "recognize_from_element")

    def test_cannot_instantiate(self) -> None:
        """不能直接实例化抽象类。"""
        try:
            CaptchaRecognizer()
            raise AssertionError("应抛出 TypeError")
        except TypeError:
            pass


class TestSmartFillResult:
    """SmartFillResult 数据类测试。"""

    def test_creation(self) -> None:
        result = SmartFillResult(
            placeholders=[PlaceholderResult(key="name", value="张三", source="llm")],
            rendered_bytes=b"fake docx",
        )
        assert len(result.placeholders) == 1
        assert result.placeholders[0].key == "name"
        assert result.rendered_bytes == b"fake docx"

    def test_defaults(self) -> None:
        result = SmartFillResult()
        assert result.placeholders == []
        assert result.rendered_bytes is None
        assert result.error is None


class TestPlaceholderResult:
    """PlaceholderResult 数据类测试。"""

    def test_creation(self) -> None:
        result = PlaceholderResult(key="name", value="张三", source="llm")
        assert result.key == "name"
        assert result.value == "张三"
        assert result.source == "llm"

    def test_auto_source(self) -> None:
        result = PlaceholderResult(key="今天日期", value="2025年01月01日", source="auto")
        assert result.source == "auto"

    def test_fallback_source(self) -> None:
        result = PlaceholderResult(key="unknown", value="/", source="fallback")
        assert result.source == "fallback"


class TestSmartFillConstants:
    """智能填充常量测试。"""

    def test_system_prompt_not_empty(self) -> None:
        assert len(SYSTEM_PROMPT) > 0

    def test_user_prompt_template_has_placeholders(self) -> None:
        assert "{catalog}" in USER_PROMPT_TEMPLATE
        assert "{user_input}" in USER_PROMPT_TEMPLATE
        assert "{today_date}" in USER_PROMPT_TEMPLATE

    def test_auto_fill_keys(self) -> None:
        assert "今天日期" in AUTO_FILL_KEYS
        assert "当前日期" in AUTO_FILL_KEYS
        assert "今年年份" in AUTO_FILL_KEYS


class TestFilePrepareService:
    """FilePrepareService 测试。"""

    def test_get_capability_snapshot(self) -> None:
        """获取能力快照。"""
        service = FilePrepareService()
        snapshot = service.get_capability_snapshot()
        assert "docx_supported" in snapshot
        assert "docx_converter" in snapshot
