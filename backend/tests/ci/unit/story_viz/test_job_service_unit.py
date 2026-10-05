"""story_viz/services/job_service.py 单元测试.

覆盖 get_animation 的 IDOR 过滤、status/detail/preview 三类 payload、
stage 时间线推导、摘要聚合（非列表容错）、问答 ask 的 LLM mock 链路。
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.story_viz.models import StoryAnimation, StoryAnimationStage, StoryAnimationStatus, StoryVizType
from apps.story_viz.services.job_service import StoryAnimationJobService


@pytest.fixture()
def users(db):
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name="storyviz 测试律所")
    owner = Lawyer.objects.create_user(username="sv_owner", real_name="属主", law_firm=firm)
    other = Lawyer.objects.create_user(username="sv_other", real_name="他人", law_firm=firm)
    return owner, other


def _make_animation(**overrides) -> StoryAnimation:
    return StoryAnimation.objects.create(
        source_title=overrides.get("source_title", "测试判决书"),
        source_text=overrides.get("source_text", "正文内容"),
        viz_type=overrides.get("viz_type", StoryVizType.TIMELINE),
        status=overrides.get("status", StoryAnimationStatus.PENDING),
        current_stage=overrides.get("current_stage", StoryAnimationStage.QUEUED),
        progress_percent=overrides.get("progress_percent", 0),
        llm_model=overrides.get("llm_model", ""),
        created_by=overrides.get("created_by"),
        facts_payload=overrides.get(
            "facts_payload",
            {
                "parties": [{"name": "张三", "role": "原告"}],
                "events": [{"sequence": 1, "time_label": "2024", "summary": "借款", "amounts": ["1万"]}],
                "relationships": [{"source": "张三", "target": "李四", "relation_type": "借贷"}],
                "judgment_result": "胜诉",
            },
        ),
        script_payload=overrides.get("script_payload", {"timeline_nodes": [{}], "highlights": ["h"] * 25}),
        render_payload=overrides.get("render_payload", {"nodes": [1, 2], "edges": [1]}),
        animation_html=overrides.get("animation_html", ""),
        **overrides.get("extra_fields", {}),
    )


@pytest.fixture()
def svc() -> StoryAnimationJobService:
    return StoryAnimationJobService()


@pytest.mark.django_db
class TestGetAnimation:
    def test_no_user_returns_any(self, svc, users) -> None:
        owner, _ = users
        anim = _make_animation(created_by=owner)
        assert svc.get_animation(animation_id=anim.id).id == anim.id

    def test_owner_can_read_own(self, svc, users) -> None:
        owner, _ = users
        anim = _make_animation(created_by=owner)
        assert svc.get_animation(animation_id=anim.id, user=owner).id == anim.id

    def test_other_user_blocked(self, svc, users) -> None:
        owner, other = users
        anim = _make_animation(created_by=owner)
        with pytest.raises(NotFoundError, match="故事可视化任务不存在"):
            svc.get_animation(animation_id=anim.id, user=other)

    def test_superuser_reads_any(self, svc, users) -> None:
        owner, other = users
        other.is_superuser = True
        anim = _make_animation(created_by=owner)
        assert svc.get_animation(animation_id=anim.id, user=other).id == anim.id

    def test_missing_raises_not_found(self, svc) -> None:
        with pytest.raises(NotFoundError, match="故事可视化任务不存在"):
            svc.get_animation(animation_id=uuid.uuid4())

    def test_string_id_accepted(self, svc, users) -> None:
        owner, _ = users
        anim = _make_animation(created_by=owner)
        assert svc.get_animation(animation_id=str(anim.id), user=owner).id == anim.id


@pytest.mark.django_db
class TestBuildStatusPayload:
    def test_pending_payload(self, svc) -> None:
        anim = _make_animation()
        payload = svc.build_status_payload(animation=anim)
        assert payload["status"] == "pending"
        assert payload["stage"] == "queued"
        assert payload["preview_url"] == ""
        assert payload["facts_count"] == 1
        assert payload["parties_count"] == 1
        assert payload["relationships_count"] == 1
        assert payload["cancel_requested"] is False
        assert payload["error_message"] == ""
        assert payload["created_at"]  # ISO 时间戳

    def test_completed_payload_has_preview_url(self, svc) -> None:
        anim = _make_animation(
            status=StoryAnimationStatus.COMPLETED,
            current_stage=StoryAnimationStage.COMPLETED,
            progress_percent=100,
        )
        payload = svc.build_status_payload(animation=anim)
        assert payload["preview_url"] == f"/api/v1/story-viz/animations/{anim.id}/preview"

    def test_non_dict_facts_payload_tolerated(self, svc) -> None:
        anim = _make_animation(facts_payload=["not", "a", "dict"])
        payload = svc.build_status_payload(animation=anim)
        assert payload["facts_count"] == 0


@pytest.mark.django_db
class TestBuildDetailPayload:
    def test_detail_aggregates_summaries(self, svc) -> None:
        anim = _make_animation(animation_html="<html>x</html>")
        payload = svc.build_detail_payload(animation=anim)
        assert payload["has_html"] is True
        # 详情不回传 HTML 正文
        assert payload["animation_html"] == ""
        assert len(payload["stages"]) == 5
        assert payload["facts_summary"]["parties"][0] == {"name": "张三", "role": "原告"}
        assert payload["script_summary"]["timeline_nodes_count"] == 1
        # highlights 截断到 _MAX_ITEMS=20
        assert len(payload["script_summary"]["highlights"]) == 20
        assert payload["render_summary"] == {"node_count": 2, "edge_count": 1}
        # 有 parties + events + judgment + relationships + amounts → 5 类问题
        assert len(payload["suggested_questions"]) == 5

    def test_non_dict_payloads_tolerated(self, svc) -> None:
        anim = _make_animation(
            script_payload="junk",
            render_payload=42,
            facts_payload={},
        )
        payload = svc.build_detail_payload(animation=anim)
        assert payload["script_summary"]["timeline_nodes_count"] == 0
        assert payload["render_summary"] == {"node_count": 0, "edge_count": 0}
        assert payload["suggested_questions"] == []


@pytest.mark.django_db
class TestBuildPreviewPayload:
    def test_completed_returns_html(self, svc) -> None:
        anim = _make_animation(
            status=StoryAnimationStatus.COMPLETED,
            animation_html="<html>ok</html>",
        )
        payload = svc.build_preview_payload(animation=anim)
        assert payload == {"id": str(anim.id), "has_html": True, "animation_html": "<html>ok</html>"}

    def test_uncompleted_hides_html(self, svc) -> None:
        anim = _make_animation(status=StoryAnimationStatus.PROCESSING, animation_html="<html>x</html>")
        payload = svc.build_preview_payload(animation=anim)
        assert payload["has_html"] is True
        assert payload["animation_html"] == ""


@pytest.mark.django_db
class TestBuildStages:
    def _stages(self, svc, anim) -> list[dict]:
        return svc.build_detail_payload(animation=anim)["stages"]

    def test_completed_all_done_with_facts_summary(self, svc) -> None:
        anim = _make_animation(status=StoryAnimationStatus.COMPLETED, current_stage=StoryAnimationStage.COMPLETED)
        stages = self._stages(svc, anim)
        assert all(s["status"] == "done" for s in stages)
        facts_stage = stages[0]
        assert facts_stage["name"] == "extracting_facts"
        assert facts_stage["summary"] == {"parties_count": 1, "events_count": 1}

    def test_processing_active_stage(self, svc) -> None:
        anim = _make_animation(
            status=StoryAnimationStatus.PROCESSING,
            current_stage=StoryAnimationStage.DIRECTING_SCRIPT,
        )
        stages = self._stages(svc, anim)
        by_name = {s["name"]: s["status"] for s in stages}
        assert by_name["extracting_facts"] == "done"
        assert by_name["directing_script"] == "active"
        assert by_name["rendering_layout"] == "pending"
        assert by_name["composing_html"] == "pending"

    def test_failed_at_current_stage(self, svc) -> None:
        anim = _make_animation(
            status=StoryAnimationStatus.FAILED,
            current_stage=StoryAnimationStage.RENDERING_LAYOUT,
        )
        stages = self._stages(svc, anim)
        by_name = {s["name"]: s["status"] for s in stages}
        assert by_name["rendering_layout"] == "failed"
        assert by_name["extracting_facts"] == "done"
        assert by_name["composing_html"] == "pending"

    def test_cancelled_at_current_stage(self, svc) -> None:
        anim = _make_animation(
            status=StoryAnimationStatus.CANCELLED,
            current_stage=StoryAnimationStage.EXTRACTING_FACTS,
        )
        stages = self._stages(svc, anim)
        assert stages[0]["status"] == "cancelled"
        assert stages[1]["status"] == "pending"

    def test_pending_all_pending(self, svc) -> None:
        anim = _make_animation(status=StoryAnimationStatus.PENDING)
        stages = self._stages(svc, anim)
        assert all(s["status"] == "pending" for s in stages)
        assert all(s["summary"] == {} for s in stages)


class TestSummarizeHelpers:
    def test_stage_index_known_and_unknown(self) -> None:
        assert StoryAnimationJobService._stage_index("extracting_facts") == 0
        assert StoryAnimationJobService._stage_index("composing_html") == 4
        assert StoryAnimationJobService._stage_index("nope") == -1

    def test_summarize_facts_non_list_members(self) -> None:
        result = StoryAnimationJobService._summarize_facts({"parties": "x", "events": 3, "relationships": None})
        assert result == {"parties": [], "events": [], "relationships": []}

    def test_summarize_facts_truncates_to_max_items(self) -> None:
        parties = [{"name": f"p{i}", "role": "r"} for i in range(30)]
        result = StoryAnimationJobService._summarize_facts({"parties": parties})
        assert len(result["parties"]) == 20

    def test_summarize_script_non_list_counts_zero(self) -> None:
        result = StoryAnimationJobService._summarize_script(
            {"timeline_nodes": "x", "relationship_nodes": None, "edges": 5, "highlights": None, "annotations": "y"}
        )
        assert result["timeline_nodes_count"] == 0
        assert result["relationship_nodes_count"] == 0
        assert result["edges_count"] == 0
        assert result["highlights"] == []
        # 非列表真值会被 list() 逐字符展开（当前行为）
        assert result["annotations"] == ["y"]

    def test_summarize_render_non_list(self) -> None:
        assert StoryAnimationJobService._summarize_render({"nodes": "a", "edges": None}) == {
            "node_count": 0,
            "edge_count": 0,
        }

    def test_suggested_questions_amounts_break_loop(self) -> None:
        questions = StoryAnimationJobService._build_suggested_questions(
            facts={
                "parties": [{"name": "a"}],
                "events": [{"amounts": ["1"]}, {"amounts": ["2"]}, {"amounts": ["3"]}],
            }
        )
        # amounts 只追加一次
        assert questions.count("涉及金额是多少？") == 1

    def test_suggested_questions_non_list_events(self) -> None:
        # 非列表真值 events：问题条目仍按 truthy 追加，但金额扫描被跳过
        questions = StoryAnimationJobService._build_suggested_questions(facts={"events": "junk"})
        assert questions == ["案件经过了哪些关键事件？"]


@pytest.mark.django_db
class TestAsk:
    def test_uncompleted_rejects(self, svc) -> None:
        anim = _make_animation(status=StoryAnimationStatus.PROCESSING)
        with pytest.raises(ValidationException, match="任务未完成"):
            svc.ask(animation_id=anim.id, question="谁赢了")

    def test_completed_calls_llm_with_facts_context(self, svc) -> None:
        anim = _make_animation(status=StoryAnimationStatus.COMPLETED, llm_model="qwen-max")
        resp = MagicMock()
        resp.content = "张三胜诉"
        llm = MagicMock()
        llm.complete.return_value = resp

        with patch("apps.story_viz.services.job_service.build_llm_service", return_value=llm):
            answer = svc.ask(animation_id=anim.id, question="谁赢了")

        assert answer == "张三胜诉"
        kwargs = llm.complete.call_args.kwargs
        assert kwargs["prompt"] == "谁赢了"
        assert kwargs["model"] == "qwen-max"  # animation.llm_model 兜底
        assert "张三（原告）" in kwargs["system_prompt"]
        assert "张三 → 李四（借贷）" in kwargs["system_prompt"]

    def test_explicit_model_overrides_animation_model(self, svc) -> None:
        anim = _make_animation(status=StoryAnimationStatus.COMPLETED, llm_model="qwen-max")
        llm = MagicMock()
        llm.complete.return_value = MagicMock(content="答")
        with patch("apps.story_viz.services.job_service.build_llm_service", return_value=llm):
            svc.ask(animation_id=anim.id, question="q", model="gpt-5")
        assert llm.complete.call_args.kwargs["model"] == "gpt-5"
