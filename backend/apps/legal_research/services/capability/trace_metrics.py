"""查询轨迹与关键词：从 ``capability/service.py`` 拆出的纯函数。

``_build_keyword_and_summary`` 决定任务落库的 keyword / case_summary，
``_build_query_trace`` + ``_build_query_type_metrics`` 把执行器回传的 query_stats
折算成三类查询（primary / expansion / feedback）的扫描数、命中数与贡献率，
``_decision_from_metadata`` 把结构化相似度元数据折算成 accept / review / reject。

依赖方向单向：``service.py`` 与 ``snippets.py`` import 本模块；本模块只 import
``ranking``（``_normalize_text``），不反向 import ``service.py``。
原模块按原路径 re-export 本模块全部符号。
"""

from __future__ import annotations

import time
from typing import Any

from apps.core.exceptions import ValidationException
from apps.legal_research.models import LegalResearchTask
from apps.legal_research.schemas.legal_research_schemas import AgentSearchQueryTraceOut, AgentSearchRequestV1
from apps.legal_research.services.keywords import normalize_keyword_query

from .ranking import _normalize_text


def _build_keyword_and_summary(*, payload: AgentSearchRequestV1) -> tuple[str, str]:  # pragma: no cover
    seed_terms = [payload.cause_type.strip(), payload.legal_issue.strip()]
    seed_text = " ".join(term for term in seed_terms if term)
    keyword = normalize_keyword_query(seed_text) if seed_text else ""
    if not keyword:
        keyword = normalize_keyword_query(payload.facts)
    if not keyword:
        raise ValidationException("facts 为空或无法生成有效检索关键词")

    summary_parts = [payload.facts.strip()]
    if payload.legal_issue.strip():
        summary_parts.append(f"争议焦点：{payload.legal_issue.strip()}")
    if payload.cause_type.strip():
        summary_parts.append(f"案由：{payload.cause_type.strip()}")
    court_name = str(payload.court_scope.court_name or "").strip()
    if court_name:
        summary_parts.append(f"法院范围：{court_name}")
    return keyword, "\n".join(part for part in summary_parts if part)[:8000]


def _decision_from_metadata(*, metadata: dict[str, Any], score: float) -> str:  # pragma: no cover
    raw = str(metadata.get("decision") or "").strip().lower()
    if raw in {"reject", "low"}:
        return "reject"
    if raw == "medium":
        return "review"
    if raw == "high":
        return "accept"
    if score >= 0.9:
        return "accept"
    if score >= 0.75:
        return "review"
    return "reject"


def _build_query_trace(  # pragma: no cover
    *,
    task: LegalResearchTask,
    payload: AgentSearchRequestV1,
    run_payload: dict[str, Any],
    started: float,
) -> AgentSearchQueryTraceOut:
    query_trace = run_payload.get("query_trace") if isinstance(run_payload, dict) else {}
    if not isinstance(query_trace, dict):
        query_trace = {}
    primary_queries = query_trace.get("primary_queries")
    expansion_queries = query_trace.get("expansion_queries")
    feedback_queries = query_trace.get("feedback_queries")
    primary_query_list = [
        str(x).strip()
        for x in (primary_queries if isinstance(primary_queries, list) else [task.keyword])
        if str(x).strip()
    ]
    expansion_query_list = [
        str(x).strip() for x in (expansion_queries if isinstance(expansion_queries, list) else []) if str(x).strip()
    ]
    feedback_query_list = [
        str(x).strip() for x in (feedback_queries if isinstance(feedback_queries, list) else []) if str(x).strip()
    ]
    query_type_metrics = _build_query_type_metrics(
        query_trace=query_trace,
        primary_queries=primary_query_list,
        expansion_queries=expansion_query_list,
        feedback_queries=feedback_query_list,
    )
    return AgentSearchQueryTraceOut(
        primary_queries=primary_query_list,
        expansion_queries=expansion_query_list,
        feedback_queries=feedback_query_list,
        query_type_metrics=query_type_metrics,
        budget_used_ms=max(1, int((time.monotonic() - started) * 1000)),
        candidates_scanned=int(task.scanned_count),
    )


def _build_query_type_metrics(  # pragma: no cover
    *,
    query_trace: dict[str, Any],
    primary_queries: list[str],
    expansion_queries: list[str],
    feedback_queries: list[str],
) -> dict[str, AgentSearchQueryTraceOut.QueryTypeMetric]:
    raw_stats = query_trace.get("query_stats")
    query_stats = raw_stats if isinstance(raw_stats, dict) else {}
    primary_set = {_normalize_text(x) for x in primary_queries if x}
    expansion_set = {_normalize_text(x) for x in expansion_queries if x}
    feedback_set = {_normalize_text(x) for x in feedback_queries if x}

    bucket: dict[str, dict[str, int]] = {
        "primary": {"scanned": 0, "matched": 0},
        "expansion": {"scanned": 0, "matched": 0},
        "feedback": {"scanned": 0, "matched": 0},
    }
    for query, metric in query_stats.items():
        query_text = _normalize_text(str(query))
        if not query_text:
            continue
        if query_text in feedback_set:
            group = "feedback"
        elif query_text in expansion_set:
            group = "expansion"
        elif query_text in primary_set:
            group = "primary"
        else:
            group = "primary"
        metric_dict = metric if isinstance(metric, dict) else {}
        bucket[group]["scanned"] += max(0, int(metric_dict.get("scanned", 0) or 0))
        bucket[group]["matched"] += max(0, int(metric_dict.get("matched", 0) or 0))

    total_matched = sum(item["matched"] for item in bucket.values())
    out: dict[str, AgentSearchQueryTraceOut.QueryTypeMetric] = {}
    for key, value in bucket.items():
        matched = value["matched"]
        contribution = (matched / total_matched) if total_matched > 0 else 0.0
        out[key] = AgentSearchQueryTraceOut.QueryTypeMetric(
            scanned=value["scanned"],
            matched=matched,
            contribution_rate=round(contribution, 4),
        )
    return out
