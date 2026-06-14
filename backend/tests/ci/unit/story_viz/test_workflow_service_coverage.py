"""补充覆盖测试: story_viz/services/workflow_service.py (38 missing)

覆盖: run 方法的正常流程 + 异常流程 + 取消流程 + _mark_cancelled。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from apps.story_viz.models import StoryAnimationStage, StoryAnimationStatus
from apps.story_viz.services.workflow_service import StoryAnimationWorkflowService


def _make_animation(
    *,
    source_text: str = "test source",
    source_title: str = "Test Title",
    viz_type: str = "timeline",
    llm_model: str | None = None,
    cancel_requested: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        source_text=source_text,
        source_title=source_title,
        viz_type=viz_type,
        llm_model=llm_model,
        cancel_requested=cancel_requested,
        refresh_from_db=MagicMock(),
    )


def _build_service() -> tuple[StoryAnimationWorkflowService, dict[str, MagicMock]]:
    preprocess = MagicMock()
    preprocess.preprocess.return_value = SimpleNamespace(source_hash="abc", cleaned_text="cleaned")

    fact = MagicMock()
    fact.extract.return_value = SimpleNamespace(model_dump=MagicMock(return_value={"facts": True}))

    script = MagicMock()
    script.generate_script.return_value = SimpleNamespace(model_dump=MagicMock(return_value={"script": True}))

    renderer = MagicMock()
    renderer.render.return_value = {"layout": "ok"}

    fragment = MagicMock()
    fragment.generate.return_value = {"fragments": True}

    composer = MagicMock()
    composer.compose.return_value = "<html></html>"

    svc = StoryAnimationWorkflowService(
        preprocess_service=preprocess,
        fact_service=fact,
        script_service=script,
        renderer_service=renderer,
        fragment_service=fragment,
        composer_service=composer,
    )
    deps = {
        "preprocess": preprocess,
        "fact": fact,
        "script": script,
        "renderer": renderer,
        "fragment": fragment,
        "composer": composer,
    }
    return svc, deps


class TestWorkflowRun:
    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_successful_run(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        animation = _make_animation()
        MockAnimation.objects.get.return_value = animation
        mock_tz.now.return_value = "now"

        svc, deps = _build_service()

        with patch.object(svc, "_cancel_requested", return_value=False):
            svc.run(animation_id="00000000-0000-0000-0000-000000000001")

        deps["preprocess"].preprocess.assert_called_once()
        deps["fact"].extract.assert_called_once()
        deps["script"].generate_script.assert_called_once()
        deps["renderer"].render.assert_called_once()
        deps["fragment"].generate.assert_called_once()
        deps["composer"].compose.assert_called_once()

    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_exception_marks_failed(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        animation = _make_animation()
        MockAnimation.objects.get.return_value = animation
        mock_tz.now.return_value = "now"

        svc, deps = _build_service()
        deps["preprocess"].preprocess.side_effect = Exception("boom")

        with patch.object(svc, "_cancel_requested", return_value=False):
            svc.run(animation_id="00000000-0000-0000-0000-000000000001")

        # Verify the last update had FAILED status
        last_update_call = MockAnimation.objects.filter.return_value.update.call_args_list[-1]
        assert last_update_call[1]["status"] == StoryAnimationStatus.FAILED

    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_cancel_after_facts(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        animation = _make_animation()
        MockAnimation.objects.get.return_value = animation
        mock_tz.now.return_value = "now"

        svc, deps = _build_service()
        with patch.object(svc, "_cancel_requested", return_value=True):
            svc.run(animation_id="00000000-0000-0000-0000-000000000001")

        deps["script"].generate_script.assert_not_called()

    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_cancel_after_script(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        animation = _make_animation()
        MockAnimation.objects.get.return_value = animation
        mock_tz.now.return_value = "now"

        svc, deps = _build_service()
        # First cancel check (after facts) -> False, second (after script) -> True
        call_count = 0

        def _side_effect(**kwargs: object) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        with patch.object(svc, "_cancel_requested", side_effect=_side_effect):
            svc.run(animation_id="00000000-0000-0000-0000-000000000001")

        deps["renderer"].render.assert_not_called()

    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_cancel_after_fragments(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        animation = _make_animation()
        MockAnimation.objects.get.return_value = animation
        mock_tz.now.return_value = "now"

        svc, deps = _build_service()
        # First two cancel checks -> False, third (after fragments) -> True
        call_count = 0

        def _side_effect(**kwargs: object) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        with patch.object(svc, "_cancel_requested", side_effect=_side_effect):
            svc.run(animation_id="00000000-0000-0000-0000-000000000001")

        deps["composer"].compose.assert_not_called()

    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_model_propagation(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        animation = _make_animation(llm_model="deepseek-chat")
        MockAnimation.objects.get.return_value = animation
        mock_tz.now.return_value = "now"

        svc, deps = _build_service()
        with patch.object(svc, "_cancel_requested", return_value=False):
            svc.run(animation_id="00000000-0000-0000-0000-000000000001")

        assert deps["fact"]._model == "deepseek-chat"
        assert deps["script"]._model == "deepseek-chat"
        assert deps["fragment"]._model == "deepseek-chat"


class TestMarkCancelled:
    @patch("apps.story_viz.services.workflow_service.StoryAnimation")
    @patch("apps.story_viz.services.workflow_service.timezone")
    def test_mark_cancelled(self, mock_tz: MagicMock, MockAnimation: MagicMock) -> None:
        svc, _ = _build_service()
        animation = _make_animation()
        mock_tz.now.return_value = "now"

        svc._mark_cancelled(animation=animation)

        update_call = MockAnimation.objects.filter.return_value.update
        update_call.assert_called()
        last_call = update_call.call_args_list[-1]
        assert last_call[1]["status"] == StoryAnimationStatus.CANCELLED
        assert last_call[1]["error_message"] == "任务已取消"
