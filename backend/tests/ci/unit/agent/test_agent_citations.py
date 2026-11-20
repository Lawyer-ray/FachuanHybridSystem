"""逐句溯源：检索类工具结果 → 引用（``citations`` 事件 + 落库 metadata）。

为什么单独守它：前端早已把 ``[Kn]`` 角标与引用卡的渲染层做完
（``frontend/src/features/copilot/domain/knowledge.ts``），整条链路此前是**死的**
——后端从不发引用，律师点不开任何来源。这条链一旦接上，最贵的失误不是「少一条
角标」，而是「角标指向错的那份材料」：律师会拿它去写文书。

所以本文件守四件事：

1. **投影只认真实字段**：每个工具的命中形状都对着 ``mcp_server`` 的返回值逐字段
   核对过（不是猜的）；纯文本结果一条都不产（宁缺勿错）。
2. **编号与模型的计数口径一致**：``cite_no`` 按命中出现顺序 1 起递增、一轮内
   单调、跨轮重新从 1 开始；**去重/重排/跳项都是禁止的**——那会让模型算出的
   ``[K5]`` 指向另一份材料。
3. **截断只掉尾部**：``tool_result.result`` 被 SSE 截到 2000 字，长列表只能拿到
   完整前缀，已分配的号不能因此移动。
4. **提示词与 Python 清单同源**：``apps/agent/pi/AGENTS.md`` 里写给模型的可编号
   工具必须与 ``citations.CITABLE_TOOLS`` 逐名一致——少一个模型会写不存在的号
   （角标消失），多一个会让编号整体前移（角标指错）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps.agent.services.chat import citations as citations_module
from apps.agent.services.chat.citations import (
    CITABLE_TOOLS,
    MAX_CITES_PER_TURN,
    CitationCollector,
    normalize_tool_name,
    project_result,
)
from apps.agent.sse_types import CitationRef, CitationsEvent

#: 提示词文件（本文件在 backend/tests/ci/unit/agent/，上推 4 层到 backend/）
_PROMPT_PATH = Path(__file__).resolve().parents[4] / "apps" / "agent" / "pi" / "AGENTS.md"


def _envelope(items: list[dict[str, Any]]) -> str:
    """``tool_shaping.list_result`` 的信封（``{total, items}``）。"""
    return json.dumps({"total": len(items), "items": items}, ensure_ascii=False)


#: ``search_cases`` 的真实投影（``projection.CASE_LIST_FIELDS`` 的子集）。
_CASE_ITEMS: list[dict[str, Any]] = [
    {"id": 12, "name": "某某诉某公司买卖合同纠纷案", "filing_number": "", "cause_of_action": "买卖合同纠纷"},
    {"id": 13, "name": "另一案", "filing_number": "案号占位A"},
]


class TestProjection:
    """每个检索工具的命中形状 → 引用字段（对着真实响应结构核对）。"""

    def test_search_cases_envelope(self) -> None:
        hits = project_result("mcp__fachuan__search_cases", _envelope(_CASE_ITEMS))

        assert [(hit["kind"], hit["ref_id"], hit["name"]) for hit in hits] == [
            ("case", 12, "某某诉某公司买卖合同纠纷案"),
            ("case", 13, "另一案"),
        ]
        # 案号进 clause：案件没有页码，案号是它最接近「定位」的字段。
        assert hits[1]["clause"] == "案号占位A"

    def test_global_search_splits_cases_and_contracts(self) -> None:
        """两个容器里的条目字段名**完全一样**，种类只能靠容器键区分。

        共用投影会让合同被追加成「案件」——角标点开跳到错误的详情页，
        而这种错误在界面上看起来完全正常。
        """
        payload = json.dumps(
            {
                "cases": [{"id": 1, "title": "张三诉李四", "subtitle": "案号占位B"}],
                "contracts": [{"id": 9, "title": "委托代理合同", "subtitle": ""}],
            },
            ensure_ascii=False,
        )

        hits = project_result("global_search", payload)

        assert [hit["kind"] for hit in hits] == ["case", "contract"]
        assert [hit["ref_id"] for hit in hits] == [1, 9]

    def test_statute_references_build_clause_from_article(self) -> None:
        """法条：``clause`` 用中文原样条号（律师认中文），并拼出「款」。"""
        payload = json.dumps(
            {
                "references": [
                    {
                        "law_name": "民法典",
                        "article_num": 1079,
                        "article_num_raw": "一千零七十九",
                        "paragraph": "二",
                        "article_text": "夫妻一方要求离婚的……",
                    }
                ]
            },
            ensure_ascii=False,
        )

        [hit] = project_result("verify_citations", payload)

        assert hit["kind"] == "statute"
        assert hit["clause"] == "第一千零七十九条第二款"
        assert hit["text"].startswith("夫妻一方")

    def test_statute_clause_does_not_double_the_suffix(self) -> None:
        """上游若自己带了「条/款」，不能拼成「第一千零七十九条条」。

        ``_STATUTE_RE`` 的 ``article`` 组本来不含「条」，但上游换了实现或
        别的数据源带了后缀时，这种重复在界面上看起来只是「系统不严谨」，
        没人会当成 bug 报——所以先剥再拼。
        """
        payload = json.dumps({"references": [{"law_name": "民法典", "article_num_raw": "一千零七十九条条"}]})

        [hit] = project_result("check_law_references", payload)

        assert hit["clause"] == "第一千零七十九条"

    def test_list_research_results_is_a_judgment(self) -> None:
        payload = _envelope(
            [
                {
                    "id": 77,
                    "title": "某某公司与某某公司合同纠纷一审民事判决书",
                    "document_number": "案号占位C",
                    "case_digest": "本院认为……",
                }
            ]
        )

        [hit] = project_result("list_research_results", payload)

        assert (hit["kind"], hit["ref_id"]) == ("judgment", 77)
        assert hit["clause"] == "案号占位C"

    def test_capability_search_uses_snippet_as_text(self) -> None:
        """``doc_id`` 是字符串（塞不进 ``ref_id: int``）→ 宁可只显示不跳转。"""
        payload = json.dumps(
            {
                "results": [
                    {
                        "doc_id": "WK-1",
                        "title": "类案判决书",
                        "court": "北京市朝阳区人民法院",
                        "snippets": {"reasoning": "本院认为被告应承担违约责任。"},
                    }
                ]
            },
            ensure_ascii=False,
        )

        [hit] = project_result("capability_search", payload)

        assert hit["kind"] == "judgment"
        assert hit["ref_id"] is None
        assert hit["text"].startswith("本院认为")

    def test_plain_text_result_produces_nothing(self) -> None:
        """纯文本（错误文案 / Markdown）不产引用：宁缺勿错。"""
        assert project_result("search_cases", "查询失败：网络异常") == []
        assert project_result("search_cases", "") == []
        assert project_result("search_cases", None) == []

    def test_unregistered_tool_produces_nothing(self) -> None:
        """读取类工具（无结构化定位）不编号——它们也不在提示词的清单里。"""
        assert project_result("read_agent_attachment", _envelope(_CASE_ITEMS)) == []
        assert project_result("get_case", _envelope(_CASE_ITEMS)) == []

    def test_hit_without_name_is_skipped(self) -> None:
        """没有标题就没有可展示的卡片：跳过（退化数据，不是正常路径）。"""
        assert project_result("search_cases", _envelope([{"id": 1, "name": ""}])) == []


class TestTruncatedResult:
    """``tool_result.result`` 被截到 2000 字：只能拿完整前缀，且**前缀编号不变**。"""

    def test_complete_objects_are_salvaged_from_a_cut_envelope(self) -> None:
        # 切掉最后一个对象的中间（模拟 SSE 的 2000 字截断）
        full = _envelope([{"id": i, "name": f"案件{i}"} for i in range(1, 4)])
        cut = full[: full.rindex('"name": "案件3"') + 10]

        hits = project_result("search_cases", cut)

        assert [hit["ref_id"] for hit in hits] == [1, 2]

    def test_half_an_object_is_never_accepted(self) -> None:
        """被截断的半个对象绝不解码：``name`` 对、``ref_id`` 缺的引用比没有更糟。"""
        cut = '{"total": 1, "items": [{"id": 12, "name": "某某诉某公司买卖'

        assert project_result("search_cases", cut) == []

    def test_numbering_is_prefix_stable_across_truncation(self) -> None:
        """截断只掉尾部：同一个前缀在完整/截断两种输入下拿到同样的号。"""
        items = [{"id": i, "name": f"案件{i}"} for i in range(1, 6)]
        full = _envelope(items)
        cut = full[: full.index('"案件5"')]

        complete_collector = CitationCollector()
        cut_collector = CitationCollector()
        complete_collector.ingest(tool_name="search_cases", result=full)
        cut_collector.ingest(tool_name="search_cases", result=cut)

        assert [(c.cite_no, c.ref_id) for c in cut_collector.all] == [
            (c.cite_no, c.ref_id) for c in complete_collector.all if c.cite_no <= 4
        ]


class TestCollector:
    """编号分配：本轮单调、跨轮重来、不重排、封顶只掉尾部。"""

    def test_monotonic_across_tool_calls(self) -> None:
        collector = CitationCollector()

        collector.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS))
        collector.ingest(tool_name="list_contracts", result=_envelope([{"id": 9, "name": "委托代理合同"}]))

        assert [c.cite_no for c in collector.all] == [1, 2, 3]
        assert [c.kind for c in collector.all] == ["case", "case", "contract"]

    def test_same_hit_twice_takes_two_numbers(self) -> None:
        """**不去重**：去重会让后面的号整体前移，模型算出的 ``[K5]`` 就指错了。"""
        collector = CitationCollector()

        collector.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS))
        collector.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS))

        assert [c.cite_no for c in collector.all] == [1, 2, 3, 4]
        assert collector.all[0].ref_id == collector.all[2].ref_id

    def test_new_turn_restarts_from_one(self) -> None:
        """跨轮从 1 重新开始——与前端角标的「本轮」语义一致。"""
        first = CitationCollector()
        first.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS))
        second = CitationCollector()

        [ref] = second.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS[1:]))

        assert ref.cite_no == 1

    def test_cap_only_drops_the_tail(self) -> None:
        collector = CitationCollector()
        many = _envelope([{"id": i, "name": f"案件{i}"} for i in range(1, 41)])

        for _ in range(3):  # 120 条命中 > 上限
            collector.ingest(tool_name="search_cases", result=many)

        assert len(collector.all) == MAX_CITES_PER_TURN
        assert [c.cite_no for c in collector.all] == list(range(1, MAX_CITES_PER_TURN + 1))
        assert [c.ref_id for c in collector.all[:3]] == [1, 2, 3]

    def test_ingest_swallows_projection_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """引用是附加价值：解析意外不能中断整轮回答（它在 SSE 循环里）。"""

        def _boom(*_: Any, **__: Any) -> None:
            raise RuntimeError("解析炸了")

        monkeypatch.setattr(citations_module, "project_result", _boom)

        assert CitationCollector().ingest(tool_name="search_cases", result="{}") == []

    def test_wire_uses_snake_case_keys(self) -> None:
        """落库/线路都是 **snake_case**（``cite_no``）；前端负责映射成 ``citeNo``。"""
        collector = CitationCollector()
        collector.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS))

        [payload] = collector.wire()[:1]

        assert payload["cite_no"] == 1
        assert "citeNo" not in payload
        # 只有 None 的键被省掉：帧更小，且语义不变（前端本来就当可选）。
        assert "chunk_id" not in payload

    def test_tool_name_normalisation(self) -> None:
        assert normalize_tool_name("mcp__fachuan__search_cases") == "search_cases"
        assert normalize_tool_name("mcp__other__search_cases") == "search_cases"
        assert normalize_tool_name("search_cases") == "search_cases"
        assert normalize_tool_name("") == ""


class TestWireContract:
    """生成物 / 事件契约：前端已按这批字段名实现，改名前必须先想清楚。"""

    def test_citations_event_round_trips(self) -> None:
        collector = CitationCollector()
        collector.ingest(tool_name="search_cases", result=_envelope(_CASE_ITEMS))

        event = CitationsEvent.model_validate(
            {"type": "citations", "citations": collector.wire(), "agent": "pi", "run_id": "s:pi:1"}
        )

        assert event.type == "citations"
        assert [c.cite_no for c in event.citations] == [1, 2]
        assert event.agent == "pi"

    def test_citation_kind_enum_covers_frontend_contract(self) -> None:
        """``kind`` 的五个取值与前端 ``CitationKind`` 逐字对应。"""
        declared = set(CitationRef.model_fields["kind"].annotation.__args__)  # type: ignore[attr-defined]
        assert declared == {"case", "contract", "statute", "judgment", "file"}

    def test_prompt_lists_every_citable_tool(self) -> None:
        """提示词的可编号清单必须与 ``CITABLE_TOOLS`` 逐名一致。

        少一个 → 模型为一个后端不认的号写 ``[Kn]``（角标静默消失）；
        多一个 → 该工具的命中不占号，后面所有号前移（角标**指错**）。
        两个方向都不会有任何运行时报错，只能靠这条断言挡。
        """
        prompt = _PROMPT_PATH.read_text(encoding="utf-8")

        missing = sorted(name for name in CITABLE_TOOLS if name not in prompt)
        assert not missing, f"系统提示词里缺少可编号工具：{missing}（模型将无法为它们写角标）"

        # 反向：提示词里点名「参与编号」的那一段不能出现清单外的工具名
        section = prompt.split("## 逐句溯源", 1)[1].split("## 行为规范", 1)[0]
        named = {name for name in citations_module.TOOL_SPECS if name in section}
        assert named == set(CITABLE_TOOLS)
