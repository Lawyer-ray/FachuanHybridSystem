"""animation_script_service.py 单元测试（LLM mock）.

覆盖生成成功 / 首次失败重试成功 / 双失败回退（timeline 与 claim_judgment
两种回退脚本结构），同步 generate_script 与异步 agenerate_script 双链路。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.story_viz.schemas import ExtractedFacts, FactEvent, FactParty, FactRelationship
from apps.story_viz.services.animation_script_service import AnimationScriptService


def _facts() -> ExtractedFacts:
    return ExtractedFacts(
        case_title="张三诉李四",
        parties=[FactParty(name="张三", role="原告"), FactParty(name="李四", role="被告"), FactParty(name="", role="")],
        events=[
            FactEvent(sequence=1, time_label="2024-01", summary="签订借条", amounts=["10万"]),
            FactEvent(sequence=2, time_label="2024-06", summary="起诉"),
            FactEvent(sequence=3, time_label="", summary=""),
        ],
        relationships=[
            FactRelationship(source="张三", target="李四", relation_type="借贷"),
            FactRelationship(source="", target="", relation_type="x"),
        ],
        judgment_result="胜诉",
    )


def _script_json(title: str = "导演标题") -> str:
    return json.dumps(
        {
            "title": title,
            "viz_type": "timeline",
            "highlights": ["要点"],
            "annotations": ["注"],
            "timeline_nodes": [{"time": "2024", "label": "签合同"}],
            "scene_order": ["scene_1"],
        },
        ensure_ascii=False,
    )


def _llm(content: Any = None, side_effect: Any = None) -> MagicMock:
    llm = MagicMock()
    resp = MagicMock()
    resp.content = content
    if side_effect is not None:
        llm.chat = MagicMock(side_effect=side_effect)
        llm.achat = AsyncMock(side_effect=side_effect)
    else:
        llm.chat = MagicMock(return_value=resp)
        llm.achat = AsyncMock(return_value=resp)
    return llm


class TestGenerateScript:
    def test_success_sets_viz_type(self) -> None:
        llm = _llm(content=_script_json("首个尝试"))
        svc = AnimationScriptService(llm_service=llm, model="gpt-x")
        script = svc.generate_script(facts=_facts(), viz_type="timeline")

        assert script.title == "首个尝试"
        assert script.viz_type == "timeline"  # 以入参覆盖 LLM 返回值
        # 首次调用 temperature=0.0，模型名透传
        assert llm.chat.call_args.kwargs["model"] == "gpt-x"
        assert llm.chat.call_args.kwargs["temperature"] == 0.0
        assert llm.chat.call_count == 1

    def test_first_failure_retries_with_higher_temperature(self) -> None:
        good = MagicMock()
        good.content = _script_json("重试成功")
        llm = _llm(side_effect=[RuntimeError("boom"), good])
        svc = AnimationScriptService(llm_service=llm)

        script = svc.generate_script(facts=_facts(), viz_type="timeline")

        assert script.title == "重试成功"
        assert llm.chat.call_count == 2
        assert llm.chat.call_args_list[1].kwargs["temperature"] == 0.3

    def test_invalid_json_falls_back(self) -> None:
        llm = _llm(content="不是 JSON")
        svc = AnimationScriptService(llm_service=llm)
        script = svc.generate_script(facts=_facts(), viz_type="timeline")

        # 走 fallback：标题取 facts.case_title，而非 LLM 输出
        assert script.title == "张三诉李四"
        assert llm.chat.call_count == 2  # 重试一次后仍失败


class TestFallbackScriptTimeline:
    def _fallback(self) -> Any:
        llm = _llm(content="junk")
        return AnimationScriptService(llm_service=llm).generate_script(facts=_facts(), viz_type="timeline")

    def test_nodes_edges_built_from_facts(self) -> None:
        script = self._fallback()
        # 空名 party 与空 source/target relationship 被过滤
        assert [n.id for n in script.relationship_nodes] == ["张三", "李四"]
        assert len(script.edges) == 1
        assert script.edges[0].relation == "借贷"
        # 注释取有 summary 的事件（最多 5 条）
        assert script.annotations == ["签订借条", "起诉"]
        # 时间线取有 summary 的事件（最多 12 条）
        assert [n["time"] for n in script.timeline_nodes] == ["2024-01", "2024-06"]
        assert script.fragment_prompts == ["indicator pulse", "connection halo"]
        assert script.motion_plan.duration_ms == 1000

    def test_scene_order_counts_all_events(self) -> None:
        script = self._fallback()
        # scene_order 按 len(facts.events) 计（含被过滤的空事件），上限 5
        assert script.scene_order == [f"scene_{i}" for i in range(3)]


class TestFallbackScriptClaimJudgment:
    def test_comparison_built_from_events(self) -> None:
        llm = _llm(content="junk")
        script = AnimationScriptService(llm_service=llm).generate_script(facts=_facts(), viz_type="claim_judgment")

        # 有 summary 的事件 → comparison item，amount 取第一个金额
        claims = [c.claim for c in script.comparison_nodes]
        assert claims == ["签订借条", "起诉"]
        assert script.comparison_nodes[0].amount_claim == "10万"
        assert script.comparison_nodes[0].supported is False
        assert script.annotations == ["胜诉"]  # judgment_result 进注释

    def test_comparison_falls_back_to_judgment_result(self) -> None:
        facts = ExtractedFacts(case_title="空事件案", judgment_result="驳回")
        llm = _llm(content="junk")
        script = AnimationScriptService(llm_service=llm).generate_script(facts=facts, viz_type="claim_judgment")

        # 无可用事件时退化为单一「诉讼请求 → 判决结果」条目
        assert len(script.comparison_nodes) == 1
        assert script.comparison_nodes[0].claim == "诉讼请求"
        assert script.comparison_nodes[0].judgment == "驳回"


class TestAGenerateScript:
    @pytest.mark.asyncio
    async def test_async_success(self) -> None:
        llm = _llm(content=_script_json("异步"))
        svc = AnimationScriptService(llm_service=llm, model="m1")
        script = await svc.agenerate_script(facts=_facts(), viz_type="relationship")
        assert script.title == "异步"
        assert script.viz_type == "relationship"
        assert llm.achat.call_args.kwargs["model"] == "m1"

    @pytest.mark.asyncio
    async def test_async_first_failure_retries(self) -> None:
        good = MagicMock()
        good.content = _script_json("异步重试")
        llm = _llm(side_effect=[RuntimeError("x"), good])
        svc = AnimationScriptService(llm_service=llm)
        script = await svc.agenerate_script(facts=_facts(), viz_type="timeline")
        assert script.title == "异步重试"
        assert llm.achat.call_count == 2

    @pytest.mark.asyncio
    async def test_async_double_failure_fallback(self) -> None:
        llm = _llm(side_effect=RuntimeError("dead"))
        svc = AnimationScriptService(llm_service=llm)
        script = await svc.agenerate_script(facts=_facts(), viz_type="claim_judgment")
        assert script.title == "张三诉李四"
        assert len(script.comparison_nodes) == 2
