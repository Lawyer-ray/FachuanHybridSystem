"""案例相似度 - 评分原语 (纯 classmethod / staticmethod)."""

from __future__ import annotations

import math
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    raw = re.findall(r"[一-鿿A-Za-z0-9]{2,10}", (text or "").lower())
    stopwords = {
        "以及", "或者", "如果", "因此", "应当", "需要", "有关", "关于",
        "因为", "但是", "其中", "并且", "法院认为", "本院认为", "原告", "被告",
    }
    return [token for token in raw if token not in stopwords]


def dedupe_tokens(tokens: list[str], *, max_tokens: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(token.strip())
        if len(out) >= max_tokens:
            break
    return out


def char_ngrams(text: str) -> Counter[str]:
    normalized = re.sub(r"\s+", "", (text or "").lower())[:2000]
    counter: Counter[str] = Counter()
    if len(normalized) < 2:
        return counter
    for n in (2, 3):
        if len(normalized) < n:
            continue
        for i in range(len(normalized) - n + 1):
            gram = normalized[i : i + n]
            counter[gram] += 1
    return counter


def bm25_proxy_score(*, query_text: str, document_text: str) -> float:
    query_tokens = tokenize(query_text)
    if not query_tokens:
        return 0.0
    doc_tokens = tokenize(document_text)
    if not doc_tokens:
        return 0.0

    freq = Counter(doc_tokens)
    doc_len = max(1, len(doc_tokens))
    avg_dl = 280.0
    k1 = 1.2
    b = 0.75
    total = 0.0
    used = 0
    for token in dedupe_tokens(query_tokens, max_tokens=20):
        tf = freq.get(token.lower(), 0)
        if tf <= 0:
            continue
        denom = tf + k1 * (1 - b + b * doc_len / avg_dl)
        if denom <= 0:
            continue
        score = (tf * (k1 + 1)) / denom
        total += min(1.0, score / 2.3)
        used += 1

    if used == 0:
        return 0.0
    return max(0.0, min(1.0, total / used))


def lexical_vector_similarity_score(text_a: str, text_b: str) -> float:
    grams_a = char_ngrams(text_a)
    grams_b = char_ngrams(text_b)
    if not grams_a or not grams_b:
        return 0.0

    common = set(grams_a).intersection(grams_b)
    dot = sum(grams_a[g] * grams_b[g] for g in common)
    norm_a = math.sqrt(sum(v * v for v in grams_a.values()))
    norm_b = math.sqrt(sum(v * v for v in grams_b.values()))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    cosine = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, cosine))


def token_overlap_score(query_text: str, text: str) -> float:
    query_tokens_list = dedupe_tokens(tokenize(query_text), max_tokens=24)
    if not query_tokens_list:
        return 0.0
    haystack = (text or "").lower()
    matched = sum(1 for token in query_tokens_list if token.lower() in haystack)
    return matched / len(query_tokens_list)


def metadata_hint_score(*, keyword: str, title: str, case_digest: str, content_text: str) -> float:
    domain_terms = [
        "买卖合同", "买卖", "违约", "违约责任", "损失", "赔偿",
        "价差", "交货", "转卖", "合同价", "市场价格",
    ]
    keyword_text = f"{keyword} {title} {case_digest}"
    relevant = [term for term in domain_terms if term in keyword_text]
    if not relevant:
        relevant = [term for term in domain_terms if term in (title + case_digest)]
    if not relevant:
        return 0.0
    haystack = f"{title} {case_digest} {(content_text or '')[:2000]}"
    matched = sum(1 for term in relevant if term in haystack)
    return max(0.0, min(1.0, matched / max(1, len(relevant))))


def keyword_overlap_score(*, keyword: str, title: str, case_digest: str, content_text: str) -> float:
    raw_tokens = re.split(r"[\s,，;；、]+", (keyword or "").lower())
    tokens = [token for token in raw_tokens if token and len(token) >= 2]
    if not tokens:
        return 0.0

    haystack = f"{title} {case_digest} {(content_text or '')[:1200]}".lower()
    matched = sum(1 for token in tokens if token in haystack)
    return matched / len(tokens)


def summary_overlap_score(*, case_summary: str, title: str, case_digest: str, content_text: str) -> float:
    summary_tokens = re.findall(r"[一-鿿A-Za-z0-9]{2,}", (case_summary or "").lower())
    if not summary_tokens:
        return 0.0

    filtered: list[str] = []
    stopwords = {"以及", "或者", "如果", "因此", "应当", "需要", "有关", "关于", "因为", "但是", "其中", "并且"}
    for token in summary_tokens:
        if token in stopwords:
            continue
        if token.isdigit():
            continue
        filtered.append(token)

    if not filtered:
        return 0.0

    haystack = f"{title} {case_digest} {(content_text or '')[:2000]}".lower()
    matched = sum(1 for token in filtered if token in haystack)
    return matched / len(filtered)


def coerce_score(value: object) -> float:
    raw = str(value or "").strip().replace("％", "%")
    if not raw:
        return 0.0

    percent_match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*%", raw)
    if percent_match:
        return normalize_score(float(percent_match.group(1)))

    numeric_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
    if not numeric_match:
        return 0.0
    try:
        parsed = float(numeric_match.group(1))
    except (TypeError, ValueError):
        return 0.0
    return normalize_score(parsed)


def normalize_score(score: float) -> float:
    if score > 1.0 and score <= 100.0:
        return score / 100.0
    if score < 0:
        return 0.0
    return min(1.0, score)


def extract_score_from_text(text: str) -> float:
    if not text:
        return 0.0

    patterns = [
        r'"score"\s*[:：]\s*"?([0-9]+(?:\.[0-9]+)?%?)"?',
        r"相似度[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?%?)",
        r"\b(0(?:\.\d+)?|1(?:\.0+)?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        score = coerce_score(match.group(1))
        if score > 0:
            return score
    return 0.0


def build_candidate_excerpt(content_text: str, *, max_len: int = 3200) -> str:
    text = focus_content_after_fact_marker(content_text)
    if len(text) <= max_len:
        return text
    head = text[:1400]
    middle_start = max(0, len(text) // 2 - 450)
    middle = text[middle_start : middle_start + 900]
    tail = text[-900:]
    return f"{head}\n...\n{middle}\n...\n{tail}"


def focus_content_after_fact_marker(content_text: str) -> str:
    text = (content_text or "").strip()
    if not text:
        return ""

    marker_match = re.search(r"本院(?:经审理)?查明", text)
    if marker_match is None:
        return text
    marker_index = marker_match.start()

    focused = text[marker_index:].strip()
    if len(focused) < 24:
        return text
    return focused
