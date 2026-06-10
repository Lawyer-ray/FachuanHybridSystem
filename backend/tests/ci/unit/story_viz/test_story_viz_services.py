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
        from apps.story_viz.services.job_service import StoryAnimationJobService
        from apps.story_viz.models import StoryAnimationStatus
        svc = StoryAnimationJobService()
        animation = MagicMock()
        animation.id = "test-id"
        animation.animation_html = "<html>test</html>"
        animation.status = StoryAnimationStatus.COMPLETED
        payload = svc.build_preview_payload(animation=animation)
        assert payload["has_html"] is True
        assert payload["animation_html"] == "<html>test</html>"
