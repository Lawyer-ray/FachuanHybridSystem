from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.story_viz.api.animation_api import preview_story_animation
from apps.story_viz.services.job_service import StoryAnimationJobService
from apps.story_viz.services.preprocess_service import JudgmentPreprocessService
from apps.story_viz.services.svg_fragment_generator_service import SvgFragmentGeneratorService


class _FakeResp:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLMService:
    def __init__(self, content: str) -> None:
        self._content = content

    def chat(self, **_: object) -> _FakeResp:
        return _FakeResp(self._content)


def test_preprocess_service_trims_and_builds_stable_hash() -> None:
    service = JudgmentPreprocessService()
    source_text = "\n  第一行  \n\n 第二行  \n"

    result1 = service.preprocess(source_text=source_text, viz_type="timeline")
    result2 = service.preprocess(source_text=source_text, viz_type="timeline")

    assert result1.cleaned_text == "第一行\n第二行"
    assert len(result1.source_hash) == 64
    assert result1.source_hash == result2.source_hash


def test_svg_fragment_generator_filters_unsafe_payload() -> None:
    unsafe_payload = '{"fragments": [{"name": "bad", "svg": "<script>alert(1)</script>"}]}'
    service = SvgFragmentGeneratorService(llm_service=_FakeLLMService(unsafe_payload))
    script = SimpleNamespace(fragment_prompts=["生成一个装饰"])

    payload = service.generate(script=script)

    assert "fragments" in payload
    assert payload["fragments"]
    assert all("<script" not in item["svg"].lower() for item in payload["fragments"])


def test_job_service_completed_payload_contains_preview_url() -> None:
    animation = SimpleNamespace(
        id="abc",
        source_title="标题",
        viz_type="timeline",
        status="completed",
        current_stage="completed",
        progress_percent=100,
        error_message="",
        task_id="task-1",
        cancel_requested=False,
        updated_at=SimpleNamespace(isoformat=lambda: "2026-01-01T00:00:00"),
    )

    payload = StoryAnimationJobService().build_status_payload(animation=animation)

    assert payload["preview_url"].endswith("/api/v1/story-viz/animations/abc/preview")
    assert payload["status"] == "completed"


def test_preview_api_returns_409_when_not_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_animation = SimpleNamespace(status="processing", animation_html="")

    class _FakeJobService:
        def get_animation(self, *, animation_id: object) -> object:
            return fake_animation

    monkeypatch.setattr(
        "apps.story_viz.api.animation_api.get_story_animation_job_service",
        lambda: _FakeJobService(),
    )

    response = preview_story_animation(request=SimpleNamespace(), animation_id="00000000-0000-0000-0000-000000000000")

    assert response.status_code == 409
    assert "任务未完成" in response.content.decode("utf-8")
