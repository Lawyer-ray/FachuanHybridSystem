"""workflow_service.arun 异步链路测试（全依赖 mock）.

覆盖 arun 成功完成、三个取消检查点、异常标记 FAILED、
llm_model 向子服务 _model 的下发，以及 _mark_cancelled 终态写入。
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.story_viz.services.workflow_service import StoryAnimationWorkflowService

ANIM_ID = "00000000-0000-0000-0000-000000000001"


def _make_animation(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=ANIM_ID,
        source_text=overrides.get("source_text", "判决书原文"),
        source_title=overrides.get("source_title", "标题"),
        viz_type=overrides.get("viz_type", "timeline"),
        llm_model=overrides.get("llm_model", ""),
        refresh_from_db=MagicMock(),
    )


@contextlib.contextmanager
def _run_workflow(animation: SimpleNamespace, *, cancel_results: list[bool] | None = None) -> Iterator[dict[str, Any]]:
    """构造全 mock 依赖并启动 patch，产出可断言的 mock 句柄。"""
    preprocess = MagicMock()
    preprocess.preprocess.return_value = SimpleNamespace(source_hash="h1", cleaned_text="清洗后")

    fact = MagicMock()
    fact.aextract = AsyncMock(return_value=SimpleNamespace(model_dump=MagicMock(return_value={"parties": []})))

    script = MagicMock()
    script.agenerate_script = AsyncMock(return_value=SimpleNamespace(model_dump=MagicMock(return_value={"script": 1})))

    renderer = MagicMock()
    renderer.render.return_value = {"nodes": []}

    fragment = MagicMock()
    fragment.agenerate = AsyncMock(return_value={"fragments": []})

    composer = MagicMock()
    composer.compose.return_value = "<html>done</html>"

    svc = StoryAnimationWorkflowService(
        preprocess_service=preprocess,
        fact_service=fact,
        script_service=script,
        renderer_service=renderer,
        fragment_service=fragment,
        composer_service=composer,
    )
    handles = {
        "svc": svc,
        "preprocess": preprocess,
        "fact": fact,
        "script": script,
        "renderer": renderer,
        "fragment": fragment,
        "composer": composer,
    }

    with (
        patch("apps.story_viz.services.workflow_service.StoryAnimation") as MockAnim,
        patch("apps.story_viz.services.workflow_service.timezone"),
    ):
        MockAnim.objects.get.return_value = animation
        with patch.object(svc, "_update_progress", MagicMock()) as progress_mock:
            with patch.object(svc, "_update_fields", MagicMock()):
                with patch.object(svc, "_mark_cancelled", MagicMock()) as cancel_mock:
                    if cancel_results is None:
                        cancel_ctx = patch.object(svc, "_cancel_requested", return_value=False)
                    else:
                        cancel_ctx = patch.object(svc, "_cancel_requested", side_effect=list(cancel_results))
                    with cancel_ctx as cancel_check_mock:
                        handles["progress_mock"] = progress_mock
                        handles["cancel_mock"] = cancel_mock
                        handles["cancel_check_mock"] = cancel_check_mock
                        yield handles


class TestArunSuccess:
    @pytest.mark.asyncio
    async def test_full_pipeline_completes(self) -> None:
        animation = _make_animation(llm_model="gpt-ao")
        with _run_workflow(animation) as h:
            await h["svc"].arun(animation_id=ANIM_ID)

            h["preprocess"].preprocess.assert_called_once_with(source_text="判决书原文", viz_type="timeline")
            h["fact"].aextract.assert_awaited_once()
            h["script"].agenerate_script.assert_awaited_once()
            h["renderer"].render.assert_called_once()
            h["fragment"].agenerate.assert_awaited_once()
            h["composer"].compose.assert_called_once()

            # 最后一次 _update_progress 是 COMPLETED + html
            last = h["progress_mock"].call_args_list[-1]
            assert last.kwargs["status"] == "completed"
            assert last.kwargs["progress"] == 100
            assert last.kwargs["animation_html"] == "<html>done</html>"
            h["cancel_mock"].assert_not_called()

    @pytest.mark.asyncio
    async def test_model_propagated_to_sub_services(self) -> None:
        animation = _make_animation(llm_model="deepseek-r")
        with _run_workflow(animation) as h:
            await h["svc"].arun(animation_id=ANIM_ID)
        assert h["fact"]._model == "deepseek-r"
        assert h["script"]._model == "deepseek-r"
        assert h["fragment"]._model == "deepseek-r"

    @pytest.mark.asyncio
    async def test_empty_model_propagates_none(self) -> None:
        animation = _make_animation(llm_model="")
        with _run_workflow(animation) as h:
            await h["svc"].arun(animation_id=ANIM_ID)
        assert h["fact"]._model is None
        assert h["script"]._model is None


class TestArunCancel:
    @pytest.mark.asyncio
    async def test_cancel_before_script(self) -> None:
        animation = _make_animation()
        with _run_workflow(animation, cancel_results=[True]) as h:
            await h["svc"].arun(animation_id=ANIM_ID)

        assert h["cancel_check_mock"].call_count == 1
        assert h["cancel_mock"].call_count == 1
        assert h["script"].agenerate_script.await_count == 0

    @pytest.mark.asyncio
    async def test_cancel_before_fragments(self) -> None:
        animation = _make_animation()
        with _run_workflow(animation, cancel_results=[False, True]) as h:
            await h["svc"].arun(animation_id=ANIM_ID)

        assert h["cancel_check_mock"].call_count == 2
        assert h["cancel_mock"].call_count == 1
        assert h["script"].agenerate_script.await_count == 1
        assert h["fragment"].agenerate.await_count == 0

    @pytest.mark.asyncio
    async def test_cancel_before_compose(self) -> None:
        animation = _make_animation()
        with _run_workflow(animation, cancel_results=[False, False, True]) as h:
            await h["svc"].arun(animation_id=ANIM_ID)

        h["cancel_mock"].assert_called_once()
        h["fragment"].agenerate.assert_awaited_once()
        h["composer"].compose.assert_not_called()
        # 取消时不应再写 COMPLETED
        assert all(c.kwargs.get("status") != "completed" for c in h["progress_mock"].call_args_list)


class TestArunFailure:
    @pytest.mark.asyncio
    async def test_fact_failure_marks_failed(self) -> None:
        animation = _make_animation()
        with _run_workflow(animation) as h:
            h["fact"].aextract = AsyncMock(side_effect=RuntimeError("LLM 挂了"))
            await h["svc"].arun(animation_id=ANIM_ID)  # 异常被捕获，不向外抛

        last = h["progress_mock"].call_args_list[-1]
        assert last.kwargs["status"] == "failed"
        assert "LLM 挂了" in last.kwargs["error_message"]
        h["composer"].compose.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_message_truncated_to_4000(self) -> None:
        animation = _make_animation()
        big_error = RuntimeError("x" * 9000)
        with _run_workflow(animation) as h:
            h["fact"].aextract = AsyncMock(side_effect=big_error)
            await h["svc"].arun(animation_id=ANIM_ID)

        last = h["progress_mock"].call_args_list[-1]
        assert len(last.kwargs["error_message"]) == 4000

    @pytest.mark.asyncio
    async def test_compose_failure_marks_failed(self) -> None:
        animation = _make_animation()
        with _run_workflow(animation) as h:
            h["composer"].compose = MagicMock(side_effect=ValueError("模板渲染失败"))
            await h["svc"].arun(animation_id=ANIM_ID)

        last = h["progress_mock"].call_args_list[-1]
        assert last.kwargs["status"] == "failed"
        assert last.kwargs["error_message"] == "模板渲染失败"


class TestMarkCancelledSync:
    def test_mark_cancelled_writes_cancel_status(self) -> None:
        """_mark_cancelled 真实方法：写入 CANCELLED 终态（_update_progress 不 mock）。"""
        animation = _make_animation()
        svc = StoryAnimationWorkflowService(
            preprocess_service=MagicMock(),
            fact_service=MagicMock(),
            script_service=MagicMock(),
            renderer_service=MagicMock(),
            fragment_service=MagicMock(),
            composer_service=MagicMock(),
        )
        with (
            patch("apps.story_viz.services.workflow_service.StoryAnimation") as MockAnim,
            patch("apps.story_viz.services.workflow_service.timezone"),
        ):
            svc._mark_cancelled(animation=animation)

        update_kwargs = MockAnim.objects.filter.return_value.update.call_args.kwargs
        assert update_kwargs["status"] == "cancelled"
        assert update_kwargs["current_stage"] == "cancelled"
        assert update_kwargs["progress_percent"] == 100
        assert update_kwargs["error_message"] == "任务已取消"
