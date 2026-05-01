"""案例相似度 - 段落选择 / 排序 / 去重."""

from __future__ import annotations

import re

from .similarity_scorers import (
    build_candidate_excerpt,
    focus_content_after_fact_marker,
    lexical_vector_similarity_score,
    token_overlap_score,
)


def split_paragraphs(content_text: str, *, passage_max_chars: int) -> list[str]:
    text = focus_content_after_fact_marker(content_text)
    if not text:
        return []
    text = text[:passage_max_chars]
    raw_parts = re.split(r"[\n\r]+|(?<=。)|(?<=；)|(?<=！)|(?<=？)", text)
    out: list[str] = []
    for part in raw_parts:
        normalized = re.sub(r"\s+", " ", part).strip()
        if len(normalized) < 12:
            continue
        out.append(normalized)
        if len(out) >= 120:
            break
    return out


def dedupe_passages(passages: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for passage in passages:
        key = passage[:160]
        if key in seen:
            continue
        seen.add(key)
        out.append(passage)
    return out


def compose_passage_excerpt(*, passages: list[str], preview_max_chars: int) -> str:
    if not passages:
        return ""
    clipped = [p[:preview_max_chars] for p in passages]
    return "\n---\n".join(f"[片段{i + 1}] {text}" for i, text in enumerate(clipped))


def select_relevant_passages(
    *,
    keyword: str,
    case_summary: str,
    title: str,
    case_digest: str,
    content_text: str,
    max_passages: int,
    passage_max_chars: int,
) -> list[str]:
    paragraphs = split_paragraphs(content_text, passage_max_chars=passage_max_chars)
    if not paragraphs:
        return []

    query_text = f"{keyword} {case_summary} {title} {case_digest}"
    ranked: list[tuple[float, str]] = []
    for paragraph in paragraphs:
        overlap = token_overlap_score(query_text, paragraph)
        vector = lexical_vector_similarity_score(query_text, paragraph)
        score = overlap * 0.58 + vector * 0.42
        if score <= 0:
            continue
        ranked.append((score, paragraph))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top = [text for _, text in ranked[: max(1, max_passages)]]
    if not top:
        return []
    return dedupe_passages(top)


def passage_alignment_score(
    *,
    keyword: str,
    case_summary: str,
    title: str,
    case_digest: str,
    content_text: str,
    passage_max_chars: int,
    passage_top_k: int,
) -> float:
    passages = select_relevant_passages(
        keyword=keyword,
        case_summary=case_summary,
        title=title,
        case_digest=case_digest,
        content_text=content_text,
        max_passages=min(2, passage_top_k),
        passage_max_chars=passage_max_chars,
    )
    if not passages:
        return 0.0

    query_text = f"{keyword} {case_summary}"
    scores = [
        max(
            token_overlap_score(query_text, passage),
            lexical_vector_similarity_score(query_text, passage),
        )
        for passage in passages
    ]
    return max(0.0, min(1.0, max(scores, default=0.0)))
