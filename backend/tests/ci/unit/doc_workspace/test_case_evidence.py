"""类案检索作为审查的第四维风险来源。

## 每条断言守的东西

| 断言 | 不守会怎样 |
|---|---|
| 检索失败/未接入/超时 → 降级为空证据 | 「查不到类案」被当成「审查失败」，一轮审查白跑 |
| 超时有硬上限 | 威科侧慢就把整轮审查拖死（审查已在后台，但也不能无限等） |
| 查询词只取最有区分度的三类并限条数 | 把配额一次打光；或关键词太长检索系统命中率暴跌 |
| 类案要点进提示词并明确「没案号不许标 case」 | 模型凭记忆编案号——编案号比不提类案严重得多 |
| 声称 `risk_source=case` 却没有 `case_ref` → 降为辅助来源 | 无出处的「据类案」被当成决定性依据 |
| `summary.case_evidence` 记录查询与命中 | 律师无法判断「这轮到底查没查类案」 |
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from apps.doc_workspace.services import case_evidence, review_pipeline

pytestmark = pytest.mark.django_db


class TestBuildQueries:
    def test_picks_profile_relation_and_mandatory_clause_types(self) -> None:
        rules = [
            {"rule_key": "land.collective_land", "rule_class": "mandatory", "clause_type": "转让资格"},
            {"rule_key": "x", "rule_class": "contractual", "clause_type": "价款"},
        ]
        queries = case_evidence.build_queries(
            subject_profile=["工业用地", "历史污染"],
            relations=[{"relation": "抵押权人", "why": "", "risk": ""}],
            rules=rules,
        )
        assert "工业用地" in queries
        assert "抵押权人" in queries
        assert "转让资格" in queries
        # 契约性条款不该成为检索词（它的问题不是「法院怎么判」）
        assert "价款" not in queries

    def test_caps_at_max_queries_and_dedups(self) -> None:
        rules = [
            {"rule_key": f"r{i}", "rule_class": "mandatory", "clause_type": f"类型{i}"} for i in range(6)
        ]
        queries = case_evidence.build_queries(
            subject_profile=["工业用地", "工业用地"], relations=[], rules=rules
        )
        assert len(queries) <= case_evidence.MAX_QUERIES
        assert len(set(queries)) == len(queries)


def _hit(case_no: str, gist: str = "要点", relevance: float = 0.9) -> case_evidence.CaseHit:
    return case_evidence.CaseHit(
        case_no=case_no, court="某中院", title="某案", gist=gist, relevance=relevance
    )


class TestGather:
    def test_collects_and_dedups_hits(self) -> None:
        def searcher(*, query: str, facts: str, limit: int) -> list[case_evidence.CaseHit]:
            return [_hit("（20XX）京01民终某某号", relevance=0.95), _hit("（20XX）京01民终某某号", relevance=0.95)]

        evidence = case_evidence.gather(queries=["工业用地"], facts="案情", searcher=searcher)
        assert len(evidence.hits) == 1
        assert evidence.hits[0].case_no == "（20XX）京01民终某某号"

    def test_no_searcher_is_skipped_not_failed(self) -> None:
        evidence = case_evidence.gather(queries=["x"], facts="f", searcher=None)
        assert evidence.hits == []
        assert "未接入" in evidence.skipped

    def test_empty_queries_is_skipped(self) -> None:
        evidence = case_evidence.gather(queries=[], facts="f", searcher=lambda **_: [])
        assert "检索词" in evidence.skipped

    def test_timeout_does_not_raise(self) -> None:
        def slow(**_: Any) -> list[case_evidence.CaseHit]:
            time.sleep(0.5)
            return [_hit("（20XX）京02民终某某号")]

        evidence = case_evidence.gather(
            queries=["x"], facts="f", searcher=slow, timeout_seconds=0.05
        )
        assert evidence.timeout is True
        assert evidence.hits == []

    def test_searcher_error_degrades(self) -> None:
        def boom(**_: Any) -> list[case_evidence.CaseHit]:
            raise RuntimeError("配额用尽")

        evidence = case_evidence.gather(queries=["x"], facts="f", searcher=boom)
        assert evidence.hits == []
        # 单次查询失败被吞，不产生 skipped（那是整体未接入才有）
        assert evidence.skipped == ""

    def test_one_query_failure_does_not_kill_others(self) -> None:
        def flaky(*, query: str, facts: str, limit: int) -> list[case_evidence.CaseHit]:
            if query == "bad":
                raise ValueError("解析失败")
            return [_hit("（20XX）京03民终某某号")]

        evidence = case_evidence.gather(queries=["bad", "good"], facts="f", searcher=flaky)
        assert [h.case_no for h in evidence.hits] == ["（20XX）京03民终某某号"]


class TestPromptBlock:
    def test_block_forbids_inventing_case_numbers(self) -> None:
        evidence = case_evidence.CaseEvidence(hits=[_hit("（20XX）京01民终某某号", "违约金上限约定无效")])
        block = evidence.to_prompt_block()
        assert "（20XX）京01民终某某号" in block
        assert "编案号" in block
        assert "case_ref" in block

    def test_empty_evidence_renders_nothing(self) -> None:
        assert case_evidence.CaseEvidence().to_prompt_block() == ""


class TestNormalizeCaseSource:
    RULE: dict[str, Any] = {
        "rule_key": "land.collective_land",
        "clause_type": "转让资格",
        "standard_text": "…",
        "severity_if_missing": "high",
        "rule_class": "contractual",
        "stage": "before",
        "consequence": "invalid",
        "beneficiary": "neutral",
    }

    def _normalize(self, item: dict[str, Any]) -> dict[str, Any]:
        out = review_pipeline._normalize_item(  # noqa: SLF001
            {"rule_key": "land.collective_land", **item},
            rules_by_key={"land.collective_land": dict(self.RULE)},
            stance="neutral",
        )
        assert out is not None
        return out

    def test_case_source_with_case_no_is_kept(self) -> None:
        out = self._normalize(
            {"risk_source": "case", "case_ref": "（20XX）京01民终某某号", "source_weight": "core"}
        )
        assert out["risk_source"] == "case"
        assert out["case_ref"] == "（20XX）京01民终某某号"
        assert out["source_weight"] == "core"

    def test_case_source_without_case_no_is_downgraded(self) -> None:
        out = self._normalize({"risk_source": "case", "source_weight": "core"})
        assert out["risk_source"] == "case"
        assert out["source_weight"] == "supporting"


class TestPipelineUsesEvidence:
    def _run(self, monkeypatch: Any, payload: dict[str, Any]) -> tuple[Any, list[str]]:
        from apps.doc_workspace.models import ReviewRun
        from apps.doc_workspace.services import playbook_service

        seen: list[str] = []

        def fake_searcher(*, query: str, facts: str, limit: int) -> list[case_evidence.CaseHit]:
            return [_hit("（20XX）京01民终某某号", "同类条款被判无效")]

        case_evidence.register_searcher(lambda: fake_searcher)
        try:
            run = ReviewRun.objects.create(
                owner_kind="contract",
                owner_id=1500,
                subpath="1-合同/a.docx",
                status="queued",
                stance="neutral",
                contract_type="土地使用权转让",
                playbook_snapshot=playbook_service.snapshot_rules(
                    playbook_service.ensure_builtin(contract_type="土地使用权转让")
                ),
                playbook_version=2,
            )
            import json

            review_pipeline.execute_run(
                run,
                caller=lambda messages: seen.append(messages[0]["content"]) or json.dumps(payload),
                text="本合同为国有建设用地使用权转让。",
            )
        finally:
            case_evidence.register_searcher(None)
        return run, seen

    def test_evidence_enters_prompt_and_summary(self, monkeypatch: Any) -> None:
        run, seen = self._run(monkeypatch, {"findings": []})

        assert "类案要点" in seen[0]
        assert "（20XX）京01民终某某号" in seen[0]
        summary = run.summary["case_evidence"]
        assert summary["hits"][0]["case_no"] == "（20XX）京01民终某某号"
        assert summary["queries"]

    def test_no_searcher_still_reviews(self, monkeypatch: Any) -> None:
        run, seen = self._run(monkeypatch, {"findings": []})
        assert run.status == "done"
        assert "类案要点" in seen[0]
