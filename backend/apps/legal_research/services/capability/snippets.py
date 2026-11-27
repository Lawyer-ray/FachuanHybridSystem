"""检索命中 → 结构化片段（snippets）：从 ``capability/service.py`` 拆出的纯函数。

原来这些是 ``LegalResearchCapabilityService`` 的 ``@classmethod``，全部只依赖入参与
常量、不读库也不发请求，因此下沉成模块级函数：判决书原文里「诉讼请求 / 本院查明 /
本院认为 / 判决主文」四段的切分与截断规则可以单独测试，不必构造一个 Service。

依赖方向单向：``service.py`` import 本模块；本模块只 import ``trace_metrics``
（``_decision_from_metadata`` 决定 ``decision`` 字段）与 schemas，不反向 import
``service.py``。原模块按原路径 re-export 本模块全部符号，历史 import 不断裂。
"""

from __future__ import annotations

import re
from typing import Any

from apps.legal_research.schemas.legal_research_schemas import (
    AgentSearchSnippetsOut,
    AgentSearchSubscoresOut,
    RetrievalHitV1,
)

from .trace_metrics import _decision_from_metadata

SNIPPET_MAX_CHARS = 360
SNIPPET_SCAN_MAX_CHARS = 12000
SNIPPET_CAPTURE_MAX_CHARS = 1600

SNIPPET_SECTION_MARKERS: dict[str, tuple[str, ...]] = {
    "claims": (
        r"诉讼请求",
        r"请求判令",
        r"上诉请求",
        r"原告.{0,24}诉称",
        r"申请人.{0,24}请求",
    ),
    "findings": (
        r"本院(?:经审理)?查明",
        r"经审理查明",
        r"法院查明",
        r"查明事实",
    ),
    "reasoning": (
        r"本院认为",
        r"法院认为",
        r"本院经审查认为",
    ),
    "holdings": (
        r"判决如下",
        r"裁定如下",
        r"判令如下",
        r"裁判如下",
        r"裁判结果",
        r"判决主文",
    ),
}


def _normalize_content_text(text: str) -> str:  # pragma: no cover
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _clip_text(value: object, *, max_chars: int) -> str:  # pragma: no cover
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _serialize_hit(*, item: Any) -> RetrievalHitV1:  # pragma: no cover
    metadata_all = item.metadata if isinstance(item.metadata, dict) else {}
    metadata = (
        metadata_all.get("similarity_structured") if isinstance(metadata_all.get("similarity_structured"), dict) else {}
    )
    score = float(item.similarity_score or 0.0)
    conflicts_value = metadata.get("key_conflicts")  # type: ignore[union-attr]
    conflicts = [
        str(x).strip() for x in (conflicts_value if isinstance(conflicts_value, list) else []) if str(x).strip()
    ]
    snippets = _build_snippets(item=item, metadata=metadata, metadata_all=metadata_all)  # type: ignore[arg-type]
    subscores = AgentSearchSubscoresOut(
        facts_match=float(metadata.get("facts_match") or 0.0),  # type: ignore[union-attr]
        legal_relation_match=float(metadata.get("legal_relation_match") or 0.0),  # type: ignore[union-attr]
        dispute_match=float(metadata.get("dispute_match") or 0.0),  # type: ignore[union-attr]
        damage_match=float(metadata.get("damage_match") or 0.0),  # type: ignore[union-attr]
    )
    return RetrievalHitV1(
        doc_id=str(item.source_doc_id or ""),
        title=str(item.title or ""),
        court=str(item.court_text or ""),
        judgment_date=str(item.judgment_date or ""),
        score=round(score, 4),
        decision=_decision_from_metadata(metadata=metadata, score=score),  # type: ignore[arg-type]
        subscores=subscores,
        conflicts=conflicts[:8],
        snippets=snippets,
        why_selected=str(item.match_reason or "")[:300],
        source_url=str(item.source_url or ""),
    )


def _build_snippets(  # pragma: no cover
    *, item: Any, metadata: dict[str, Any], metadata_all: dict[str, Any]
) -> AgentSearchSnippetsOut:
    snippets_meta = metadata.get("snippets") if isinstance(metadata.get("snippets"), dict) else {}
    extracted = _extract_snippets_from_text(_extract_content_excerpt(item=item, metadata_all=metadata_all))

    claims = _clip_text(snippets_meta.get("claims"), max_chars=SNIPPET_MAX_CHARS) or extracted.get(  # type: ignore[union-attr]
        "claims", ""
    )
    findings = _clip_text(snippets_meta.get("findings"), max_chars=SNIPPET_MAX_CHARS) or extracted.get(  # type: ignore[union-attr]
        "findings", ""
    )
    reasoning = (
        _clip_text(snippets_meta.get("reasoning"), max_chars=SNIPPET_MAX_CHARS)  # type: ignore[union-attr]
        or extracted.get("reasoning", "")
        or _clip_text(getattr(item, "case_digest", ""), max_chars=SNIPPET_MAX_CHARS)
    )
    holdings = _clip_text(snippets_meta.get("holdings"), max_chars=SNIPPET_MAX_CHARS) or extracted.get(  # type: ignore[union-attr]
        "holdings", ""
    )
    return AgentSearchSnippetsOut(
        claims=claims,
        findings=findings,
        reasoning=reasoning,
        holdings=holdings,
    )


def _extract_content_excerpt(*, item: Any, metadata_all: dict[str, Any]) -> str:  # pragma: no cover
    raw = metadata_all.get("content_excerpt")
    if raw is None:
        raw = metadata_all.get("content_text_excerpt")
    text = str(raw or "").strip()
    if not text:
        text = str(getattr(item, "case_digest", "") or "")
    return _normalize_content_text(text)[:SNIPPET_SCAN_MAX_CHARS]


def _extract_snippets_from_text(text: str) -> dict[str, str]:  # pragma: no cover
    if not text:
        return {}
    paragraphs = _split_snippet_paragraphs(text)
    sections: dict[str, list[str]] = {"claims": [], "findings": [], "reasoning": [], "holdings": []}

    current_label = ""
    for paragraph in paragraphs:
        label = _detect_snippet_label(paragraph)
        if label:
            current_label = label
        if not current_label:
            continue
        existing = "\n".join(sections[current_label])
        if len(existing) >= SNIPPET_CAPTURE_MAX_CHARS:
            continue
        sections[current_label].append(paragraph)

    extracted: dict[str, str] = {}
    for label in ("claims", "findings", "reasoning", "holdings"):
        merged = _clip_text("\n".join(sections[label]), max_chars=SNIPPET_MAX_CHARS)
        if not merged:
            merged = _extract_span_by_marker(text=text, markers=SNIPPET_SECTION_MARKERS[label])
        if merged:
            extracted[label] = merged
    return extracted


def _split_snippet_paragraphs(text: str) -> list[str]:  # pragma: no cover
    normalized = _normalize_content_text(text)
    raw_parts = re.split(r"\n+|(?<=。)|(?<=；)|(?<=！)|(?<=？)", normalized)
    paragraphs: list[str] = []
    for part in raw_parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" :：;；\t")
        if len(cleaned) < 6:
            continue
        paragraphs.append(cleaned)
        if len(paragraphs) >= 400:
            break
    return paragraphs


def _detect_snippet_label(paragraph: str) -> str:  # pragma: no cover
    for label, markers in SNIPPET_SECTION_MARKERS.items():
        if any(re.search(marker, paragraph) for marker in markers):
            return label
    return ""


def _extract_span_by_marker(*, text: str, markers: tuple[str, ...]) -> str:  # pragma: no cover
    if not text:
        return ""
    start = -1
    for marker in markers:
        match = re.search(marker, text)
        if match is None:
            continue
        if start < 0 or match.start() < start:
            start = match.start()
    if start < 0:
        return ""

    end = min(len(text), start + SNIPPET_CAPTURE_MAX_CHARS)
    end_candidates: list[int] = []
    for marker_group in SNIPPET_SECTION_MARKERS.values():
        for marker in marker_group:
            match = re.search(marker, text[start + 1 :])
            if match is None:
                continue
            idx = start + 1 + match.start()
            if idx > start:
                end_candidates.append(idx)
    if end_candidates:
        end = min(end, min(end_candidates))
    return _clip_text(text[start:end], max_chars=SNIPPET_MAX_CHARS)
