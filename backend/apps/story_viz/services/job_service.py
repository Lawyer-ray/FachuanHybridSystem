from __future__ import annotations

import hashlib
import logging
import typing
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.core.dependencies.core import build_llm_service, build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.story_viz.models import StoryAnimation, StoryAnimationStage, StoryAnimationStatus

_PIPELINE_STAGES: list[tuple[str, str]] = [
    (StoryAnimationStage.EXTRACTING_FACTS, "提取事实"),
    (StoryAnimationStage.DIRECTING_SCRIPT, "编排脚本"),
    (StoryAnimationStage.RENDERING_LAYOUT, "渲染布局"),
    (StoryAnimationStage.GENERATING_FRAGMENTS, "生成视觉片段"),
    (StoryAnimationStage.COMPOSING_HTML, "组装HTML"),
]

_MAX_ITEMS = 20

if typing.TYPE_CHECKING:
    from apps.organization.models import Lawyer

logger = logging.getLogger("apps.story_viz")


class StoryAnimationJobService:
    @transaction.atomic
    def create_from_admin(
        self,
        *,
        source_title: str,
        source_text: str,
        viz_type: str,
        llm_model: str = "",
        created_by: typing.Any = None,
    ) -> StoryAnimation:
        source_title = source_title.strip()
        source_text = source_text.strip()
        if not source_title:
            raise ValidationException(message="标题不能为空", errors={"source_title": "请输入文书标题"})
        if not source_text:
            raise ValidationException(message="正文不能为空", errors={"source_text": "请输入判决书正文"})

        # 去重检查：相同 viz_type + 全文哈希 视为重复输入
        text_hash = hashlib.sha256(source_text.encode()).hexdigest()[:32]
        dup = (
            StoryAnimation.objects.filter(
                viz_type=viz_type,
                source_hash=text_hash,
            )
            .exclude(status__in={StoryAnimationStatus.FAILED, StoryAnimationStatus.CANCELLED})
            .order_by("-created_at")
            .first()
        )
        if dup:
            return dup

        animation = StoryAnimation.objects.create(
            source_title=source_title,
            source_text=source_text,
            viz_type=viz_type,
            llm_model=llm_model,
            source_hash=text_hash,
            status=StoryAnimationStatus.PENDING,
            current_stage=StoryAnimationStage.QUEUED,
            progress_percent=0,
            created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        )
        task_name = self.submit_generation(animation=animation)
        StoryAnimation.objects.filter(id=animation.id).update(task_id=task_name, started_at=timezone.now())
        animation.refresh_from_db()
        return animation

    def submit_generation(self, *, animation: StoryAnimation) -> str:
        return str(
            build_task_submission_service().submit(
                "apps.story_viz.tasks.generate_story_animation",
                args=[str(animation.id)],
                task_name=f"story_viz_{animation.id}",
            )
        )

    def get_animation(self, *, animation_id: UUID | str) -> StoryAnimation:
        try:
            return StoryAnimation.objects.get(id=UUID(str(animation_id)))
        except StoryAnimation.DoesNotExist:
            raise NotFoundError(message="故事可视化任务不存在", code="STORY_VIZ_NOT_FOUND", errors={}) from None

    def build_status_payload(self, *, animation: StoryAnimation) -> dict[str, object]:
        preview_url = ""
        if animation.status == StoryAnimationStatus.COMPLETED:
            preview_url = f"/api/v1/story-viz/animations/{animation.id}/preview"

        facts = animation.facts_payload if isinstance(animation.facts_payload, dict) else {}
        parties = facts.get("parties", [])
        events = facts.get("events", [])
        relationships = facts.get("relationships", [])

        return {
            "id": str(animation.id),
            "title": animation.source_title,
            "viz_type": animation.viz_type,
            "status": animation.status,
            "stage": animation.current_stage,
            "stage_display": animation.get_current_stage_display(),
            "progress": int(animation.progress_percent or 0),
            "error_message": animation.error_message or "",
            "preview_url": preview_url,
            "task_id": animation.task_id or "",
            "cancel_requested": bool(animation.cancel_requested),
            "created_at": animation.created_at.isoformat() if animation.created_at else "",
            "started_at": animation.started_at.isoformat() if animation.started_at else "",
            "finished_at": animation.finished_at.isoformat() if animation.finished_at else "",
            "updated_at": animation.updated_at.isoformat() if animation.updated_at else "",
            "facts_count": len(events),
            "parties_count": len(parties),
            "relationships_count": len(relationships),
        }

    def build_detail_payload(self, *, animation: StoryAnimation) -> dict[str, object]:
        base = self.build_status_payload(animation=animation)
        stages = self._build_stages(animation=animation)
        facts = animation.facts_payload if isinstance(animation.facts_payload, dict) else {}
        script = animation.script_payload if isinstance(animation.script_payload, dict) else {}
        render = animation.render_payload if isinstance(animation.render_payload, dict) else {}

        base["stages"] = stages
        base["facts_summary"] = self._summarize_facts(facts)
        base["script_summary"] = self._summarize_script(script)
        base["render_summary"] = self._summarize_render(render)
        base["has_html"] = bool(animation.animation_html)
        base["animation_html"] = ""
        base["suggested_questions"] = self._build_suggested_questions(facts=facts)
        return base

    def build_preview_payload(self, *, animation: StoryAnimation) -> dict[str, object]:
        return {
            "id": str(animation.id),
            "has_html": bool(animation.animation_html),
            "animation_html": animation.animation_html if animation.status == StoryAnimationStatus.COMPLETED else "",
        }

    def _build_stages(self, *, animation: StoryAnimation) -> list[dict[str, object]]:
        status = animation.status
        current = animation.current_stage
        stage_list: list[dict[str, object]] = []

        for stage_key, stage_label in _PIPELINE_STAGES:
            if status == StoryAnimationStatus.COMPLETED:
                s = "done"
            elif status in {StoryAnimationStatus.FAILED, StoryAnimationStatus.CANCELLED}:
                if stage_key == current:
                    s = "failed" if status == StoryAnimationStatus.FAILED else "cancelled"
                elif self._stage_index(stage_key) < self._stage_index(current):
                    s = "done"
                else:
                    s = "pending"
            elif status == StoryAnimationStatus.PROCESSING:
                if stage_key == current:
                    s = "active"
                elif self._stage_index(stage_key) < self._stage_index(current):
                    s = "done"
                else:
                    s = "pending"
            else:
                s = "pending"

            summary: dict[str, object] = {}
            if s == "done" and stage_key == StoryAnimationStage.EXTRACTING_FACTS:
                facts = animation.facts_payload if isinstance(animation.facts_payload, dict) else {}
                summary = {
                    "parties_count": len(facts.get("parties", [])),
                    "events_count": len(facts.get("events", [])),
                }
            stage_list.append({"name": stage_key, "label": stage_label, "status": s, "summary": summary})

        return stage_list

    @staticmethod
    def _stage_index(stage_key: str) -> int:
        for i, (key, _) in enumerate(_PIPELINE_STAGES):
            if key == stage_key:
                return i
        return -1

    @staticmethod
    def _summarize_facts(facts: dict[str, object]) -> dict[str, object]:
        parties = facts.get("parties", [])
        events = facts.get("events", [])
        relationships = facts.get("relationships", [])
        return {
            "parties": [
                {"name": p.get("name", ""), "role": p.get("role", "")}
                for p in (parties[:_MAX_ITEMS] if isinstance(parties, list) else [])
            ],
            "events": [
                {
                    "sequence": e.get("sequence", 0),
                    "time_label": e.get("time_label", ""),
                    "summary": e.get("summary", ""),
                }
                for e in (events[:_MAX_ITEMS] if isinstance(events, list) else [])
            ],
            "relationships": [
                {
                    "source": r.get("source", ""),
                    "target": r.get("target", ""),
                    "relation_type": r.get("relation_type", ""),
                }
                for r in (relationships[:_MAX_ITEMS] if isinstance(relationships, list) else [])
            ],
        }

    @staticmethod
    def _summarize_script(script: dict[str, object]) -> dict[str, object]:
        timeline_nodes = script.get("timeline_nodes", [])
        relationship_nodes = script.get("relationship_nodes", [])
        edges = script.get("edges", [])
        return {
            "highlights": list(script.get("highlights", []) or [])[:_MAX_ITEMS],  # type: ignore[arg-type,call-overload]
            "annotations": list(script.get("annotations", []) or [])[:_MAX_ITEMS],  # type: ignore[arg-type,call-overload]
            "timeline_nodes_count": len(timeline_nodes) if isinstance(timeline_nodes, list) else 0,
            "relationship_nodes_count": len(relationship_nodes) if isinstance(relationship_nodes, list) else 0,
            "edges_count": len(edges) if isinstance(edges, list) else 0,
        }

    @staticmethod
    def _summarize_render(render: dict[str, object]) -> dict[str, object]:
        nodes = render.get("nodes", [])
        edges = render.get("edges", [])
        return {
            "node_count": len(nodes) if isinstance(nodes, list) else 0,
            "edge_count": len(edges) if isinstance(edges, list) else 0,
        }

    @staticmethod
    def _build_suggested_questions(*, facts: dict[str, object]) -> list[str]:
        questions: list[str] = []
        parties = facts.get("parties", [])
        events = facts.get("events", [])
        relationships = facts.get("relationships", [])
        judgment = facts.get("judgment_result", "")

        if parties:
            questions.append("当事人有哪些？各自角色是什么？")
        if events:
            questions.append("案件经过了哪些关键事件？")
        if judgment:
            questions.append("法院最终判决结果是什么？")
        if relationships:
            questions.append("当事人之间是什么关系？")

        for e in events if isinstance(events, list) else []:
            amounts = e.get("amounts", []) if isinstance(e, dict) else []
            if amounts:
                questions.append("涉及金额是多少？")
                break

        return questions[:5]

    @transaction.atomic
    def request_cancel(self, *, animation_id: UUID | str) -> StoryAnimation:
        animation = self.get_animation(animation_id=animation_id)
        if animation.status in {
            StoryAnimationStatus.COMPLETED,
            StoryAnimationStatus.FAILED,
            StoryAnimationStatus.CANCELLED,
        }:
            return animation

        cancel_info: dict[str, object] = {}
        if animation.task_id:
            try:
                cancel_info = build_task_submission_service().cancel(animation.task_id)
            except Exception:
                logger.exception("story_viz_cancel_failed", extra={"animation_id": str(animation.id)})

        can_mark_cancelled = animation.status == StoryAnimationStatus.PENDING and (
            not animation.task_id or bool(cancel_info.get("queue_deleted")) or not bool(cancel_info.get("running"))
        )
        updates: dict[str, object] = {"cancel_requested": True}
        if can_mark_cancelled:
            updates.update(
                status=StoryAnimationStatus.CANCELLED,
                current_stage=StoryAnimationStage.CANCELLED,
                finished_at=timezone.now(),
                progress_percent=100,
                error_message="任务已取消",
            )
        StoryAnimation.objects.filter(id=animation.id).update(**updates)
        animation.refresh_from_db()
        return animation

    @transaction.atomic
    def retry(self, *, animation_id: UUID | str) -> StoryAnimation:
        animation = self.get_animation(animation_id=animation_id)
        if animation.status not in {StoryAnimationStatus.FAILED, StoryAnimationStatus.CANCELLED}:
            raise ValidationException(message="当前状态不允许重试", errors={"status": animation.status})

        task_id = self.submit_generation(animation=animation)
        StoryAnimation.objects.filter(id=animation.id).update(
            status=StoryAnimationStatus.PENDING,
            current_stage=StoryAnimationStage.QUEUED,
            progress_percent=0,
            task_id=task_id,
            cancel_requested=False,
            error_message="",
            animation_html="",
            finished_at=None,
            started_at=timezone.now(),
        )
        animation.refresh_from_db()
        return animation

    def ask(self, *, animation_id: UUID | str, question: str, model: str | None = None) -> str:
        animation = self.get_animation(animation_id=animation_id)
        if animation.status != StoryAnimationStatus.COMPLETED:
            raise ValidationException(message="任务未完成，暂无法问答", errors={"status": animation.status})

        facts = animation.facts_payload if isinstance(animation.facts_payload, dict) else {}
        parties = facts.get("parties", [])
        events = facts.get("events", [])
        relationships = facts.get("relationships", [])

        facts_text_parts: list[str] = []
        if parties:
            facts_text_parts.append(
                "当事人：" + "；".join(f"{p.get('name', '')}（{p.get('role', '')}）" for p in parties[:20])
            )
        if events:
            facts_text_parts.append(
                "事件：" + "；".join(f"{e.get('time_label', '')} {e.get('summary', '')}" for e in events[:20])
            )
        if relationships:
            facts_text_parts.append(
                "关系："
                + "；".join(
                    f"{r.get('source', '')} → {r.get('target', '')}（{r.get('relation_type', '')}）"
                    for r in relationships[:20]
                )
            )
        facts_context = "\n".join(facts_text_parts)

        system_prompt = (
            "你是法律案件分析助手。用户正在查看一份判决书的可视化结果。"
            "请根据以下案件信息回答用户的问题。回答要简洁准确，基于提供的事实数据。\n\n"
            f"【案件标题】{animation.source_title}\n\n"
            f"【原文摘要】{animation.source_text[:2000]}\n\n"
            f"【结构化事实】\n{facts_context}"
        )

        llm_service = build_llm_service()
        effective_model = model or animation.llm_model or None
        resp = llm_service.complete(
            prompt=question,
            system_prompt=system_prompt,
            model=effective_model,
            temperature=0.3,
            max_tokens=2000,
        )
        return str(resp.content)
