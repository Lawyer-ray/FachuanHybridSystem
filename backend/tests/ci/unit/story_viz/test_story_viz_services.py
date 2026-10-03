"""
Tests for apps.story_viz.services — 故事可视化服务
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestFactExtractionService:
    """FactExtractionService 测试"""

    def test_extract_success(self) -> None:
        from apps.story_viz.services.fact_extraction_service import FactExtractionService

        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"case_title": "测试案", "events": [{"sequence": 1, "time_label": "2024年", "summary": "借款发生"}], "characters": [], "relationships": [], "outcome": "胜诉"}'
        mock_llm.chat.return_value = mock_resp

        svc = FactExtractionService(llm_service=mock_llm)
        result = svc.extract(source_title="测试案", source_text="判决书内容")
        assert result.case_title == "测试案"
        assert len(result.events) == 1

    def test_extract_first_attempt_fails_second_succeeds(self) -> None:
        from apps.story_viz.services.fact_extraction_service import FactExtractionService

        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"case_title": "测试案", "events": [{"sequence": 1, "time_label": "", "summary": "借款"}], "characters": [], "relationships": [], "outcome": ""}'
        mock_llm.chat.side_effect = [Exception("first fail"), mock_resp]

        svc = FactExtractionService(llm_service=mock_llm)
        result = svc.extract(source_title="测试案", source_text="内容")
        assert result.case_title == "测试案"

    def test_extract_both_attempts_fail_fallback(self) -> None:
        from apps.story_viz.services.fact_extraction_service import FactExtractionService

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = Exception("always fail")

        svc = FactExtractionService(llm_service=mock_llm)
        result = svc.extract(source_title="测试案", source_text="这是判决书的内容，足够长用于摘要")
        assert result.case_title == "测试案"
        assert result.confidence_notes == "fallback"
        assert len(result.events) == 1

    def test_extract_empty_text_fallback(self) -> None:
        from apps.story_viz.services.fact_extraction_service import FactExtractionService

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = Exception("fail")

        svc = FactExtractionService(llm_service=mock_llm)
        result = svc.extract(source_title="测试案", source_text="")
        assert result.events[0].summary == ""


# ============================================================
# SVG/HTML 相关服务测试
# ============================================================


class TestStoryVizServices:
    """故事可视化相关服务基础测试"""

    def test_workflow_service_import(self) -> None:
        """确认 workflow_service 模块可导入"""
        from apps.story_viz.services import workflow_service

        assert workflow_service is not None

    def test_html_composer_service_import(self) -> None:
        from apps.story_viz.services import html_composer_service

        assert html_composer_service is not None

    def test_svg_fragment_generator_import(self) -> None:
        from apps.story_viz.services import svg_fragment_generator_service

        assert svg_fragment_generator_service is not None

    def test_animation_script_service_import(self) -> None:
        from apps.story_viz.services import animation_script_service

        assert animation_script_service is not None


# ---------------------------------------------------------------------------
# StoryAnimationJobService extended tests
# ---------------------------------------------------------------------------

class TestStoryAnimationJobServiceExtended:
    def _make_service(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        return StoryAnimationJobService()

    def test_build_suggested_questions_empty(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        assert StoryAnimationJobService._build_suggested_questions(facts={}) == []

    def test_build_suggested_questions_with_parties(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        facts = {"parties": [{"name": "张三", "role": "原告"}], "events": [], "relationships": []}
        questions = StoryAnimationJobService._build_suggested_questions(facts=facts)
        assert len(questions) >= 1

    def test_build_suggested_questions_with_judgment(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        facts = {"parties": [], "events": [], "relationships": [], "judgment_result": "胜诉"}
        questions = StoryAnimationJobService._build_suggested_questions(facts=facts)
        assert any("判决" in q for q in questions)

    def test_stage_index(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        assert StoryAnimationJobService._stage_index("extracting_facts") >= 0
        assert StoryAnimationJobService._stage_index("nonexistent") == -1

    def test_summarize_facts_empty(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_facts({})
        assert result["parties"] == []
        assert result["events"] == []
        assert result["relationships"] == []

    def test_summarize_facts_with_data(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        facts = {
            "parties": [{"name": "张三", "role": "原告"}],
            "events": [{"sequence": 1, "time_label": "2024", "summary": "起诉"}],
            "relationships": [{"source": "张三", "target": "李四", "relation_type": "借贷"}],
        }
        result = StoryAnimationJobService._summarize_facts(facts)
        assert len(result["parties"]) == 1
        assert len(result["events"]) == 1

    def test_summarize_script_empty(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_script({})
        assert result["timeline_nodes_count"] == 0

    def test_summarize_render_empty(self):
        from apps.story_viz.services.job_service import StoryAnimationJobService
        result = StoryAnimationJobService._summarize_render({})
        assert result["node_count"] == 0



    def test_build_preview_payload(self):
        from apps.story_viz.models import StoryAnimationStatus
        from apps.story_viz.services.job_service import StoryAnimationJobService
        svc = StoryAnimationJobService()
        animation = MagicMock()
        animation.id = "test-id"
        animation.animation_html = "<html>test</html>"
        animation.status = StoryAnimationStatus.COMPLETED
        payload = svc.build_preview_payload(animation=animation)
        assert payload["has_html"] is True
        assert payload["animation_html"] == "<html>test</html>"


# ---------------------------------------------------------------------------
# Ownership & XSS hardening (security audit IDOR/XSS)
# ---------------------------------------------------------------------------

class TestGetAnimationOwnership:
    """get_animation 归属校验：非 owner 且非 superuser 只能看到本人创建的任务"""

    @pytest.mark.django_db
    def test_non_owner_gets_not_found(self, law_firm):
        from apps.core.exceptions import NotFoundError
        from apps.story_viz.models import StoryAnimation
        from apps.story_viz.services.job_service import StoryAnimationJobService
        from apps.testing.factories import LawyerFactory

        owner = LawyerFactory(username="svz_owner", law_firm=law_firm)
        other = LawyerFactory(username="svz_other", law_firm=law_firm)
        animation = StoryAnimation.objects.create(
            source_title="测试标题",
            source_text="测试正文",
            viz_type="timeline",
            created_by=owner,
        )

        svc = StoryAnimationJobService()
        assert svc.get_animation(animation_id=str(animation.id), user=owner).id == animation.id
        with pytest.raises(NotFoundError):
            svc.get_animation(animation_id=str(animation.id), user=other)

    @pytest.mark.django_db
    def test_superuser_sees_all(self, law_firm):
        from apps.story_viz.models import StoryAnimation
        from apps.story_viz.services.job_service import StoryAnimationJobService
        from apps.testing.factories import LawyerFactory

        owner = LawyerFactory(username="svz_owner2", law_firm=law_firm)
        admin = LawyerFactory(username="svz_admin", law_firm=law_firm, is_superuser=True)
        animation = StoryAnimation.objects.create(
            source_title="测试标题",
            source_text="测试正文",
            viz_type="timeline",
            created_by=owner,
        )

        svc = StoryAnimationJobService()
        assert svc.get_animation(animation_id=str(animation.id), user=admin).id == animation.id


class TestSvgFragmentBlacklist:
    def test_unsafe_tokens_rejected(self):
        from apps.story_viz.services.svg_fragment_generator_service import _is_unsafe_fragment

        for lowered in (
            "<script>alert(1)</script>",
            "<iframe src='x'></iframe>",
            "<foreignobject>body</foreignobject>",
            "<embed src='x'>",
            "<object data='x'></object>",
            "<a href='javascript:alert(1)'>x</a>",
            "<g onload='alert(1)'></g>",
            "<g onload = 'alert(1)'></g>",
            "<g onanimationend='alert(1)'></g>",
        ):
            assert _is_unsafe_fragment(lowered), lowered

    def test_safe_fragment_accepted(self):
        from apps.story_viz.services.svg_fragment_generator_service import _is_unsafe_fragment

        assert not _is_unsafe_fragment("<circle cx='0' cy='0' r='8' fill='red' />")
        assert not _is_unsafe_fragment("<path d='m0 0 l10 10' stroke='#38bdf8' />")


class TestHtmlComposerSafeJson:
    def test_safe_json_escapes_angle_brackets(self):
        from apps.story_viz.services.html_composer_service import _safe_json

        out = _safe_json({"label": "</script><script>alert(1)</script>"})
        assert "<" not in out
        assert ">" not in out
        assert "\\u003c" in out
        assert "\\u003e" in out
