from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from django.core.cache import cache

from apps.core.interfaces import ServiceLocator
from apps.legal_research.services.tuning_config import LegalResearchTuningConfig

logger = logging.getLogger(__name__)


class _LLMEmbeddingClientAdapter:
    """
    将统一 llm_service.embed_texts 适配为历史 embeddings.create 形态。
    保留该适配层，确保旧测试与局部调用约定稳定。
    """

    def __init__(self, llm_service: Any) -> None:
        self._llm_service = llm_service
        self.embeddings = self

    def create(self, **kwargs: Any) -> Any:
        raw_input = kwargs.get("input", "")
        if isinstance(raw_input, list):
            texts = [str(item or "") for item in raw_input]
        else:
            texts = [str(raw_input or "")]
        model = kwargs.get("model")
        vectors = self._llm_service.embed_texts(
            texts=texts,
            backend="siliconflow",
            model=model,
            fallback=False,
        )
        data = [SimpleNamespace(embedding=vector) for vector in vectors]
        return SimpleNamespace(data=data)


@dataclass
class SimilarityResult:
    score: float
    reason: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


class CaseSimilarityService:
    """用硅基流动模型计算案例相似度。"""

    SCORE_MAX_TOKENS = 260
    RESCORE_MAX_TOKENS = 220
    JSON_REPAIR_MAX_TOKENS = 260
    SCORE_TIMEOUT_SECONDS = 40
    RESCORE_TIMEOUT_SECONDS = 30
    JSON_REPAIR_TIMEOUT_SECONDS = 25
    PARAGRAPH_TOP_K = 6
    PARAGRAPH_MAX_CHARS = 14000
    PASSAGE_PREVIEW_MAX_CHARS = 1400
    FACT_FOCUS_MARKER = "本院查明"
    MIN_EVIDENCE_SPAN_CHARS = 4
    SIMILARITY_CACHE_PREFIX = "legal_research:similarity"
    SIMILARITY_PROMPT_VERSION = "v2-structured"
    SIMILARITY_LOCAL_CACHE_MAX_SIZE = 1024
    SEMANTIC_EMBEDDING_CACHE_PREFIX = "legal_research:semantic_embedding"
    SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE = 2048
    SEMANTIC_EMBEDDING_TEXT_MAX_CHARS = 1400
    SEMANTIC_EMBEDDING_TIMEOUT_SECONDS = 8
    SEMANTIC_EMBEDDING_FAIL_COOLDOWN_SECONDS = 120
    VECTOR_SEMANTIC_WEIGHT = 0.6
    VECTOR_LEXICAL_WEIGHT = 0.4
    SEMANTIC_RECHECK_BASELINE_THRESHOLD = 0.56
    SEMANTIC_RECHECK_WEAK_SIGNAL_THRESHOLD = 0.45
    SEMANTIC_RECHECK_WEAK_SIGNAL_COUNT = 3
    SEMANTIC_RECHECK_MIN_QUERY_TERMS = 6
    SEMANTIC_RECHECK_LEXICAL_MAX = 0.62
    HARD_CONFLICT_NEEDLES = (
        "主体",
        "身份",
        "当事人关系",
        "法律关系",
        "合同类型",
        "交易对象",
        "违约方式",
        "违约行为",
        "损失类型",
        "损失原因",
        "请求权基础",
        "法律后果",
        "交易结构",
    )

    def __init__(self, *, tuning: LegalResearchTuningConfig | None = None) -> None:
        self._llm = ServiceLocator.get_llm_service()
        self._embedding_client: Any | None = None
        self._tuning = tuning or LegalResearchTuningConfig()
        self._passage_top_k = max(1, int(self._tuning.passage_top_k))
        self._passage_max_chars = max(1000, int(self._tuning.passage_max_chars))
        self._passage_preview_max_chars = max(300, int(self._tuning.passage_preview_max_chars))
        self._recall_weights = self._tuning.normalized_recall_weights
        self._similarity_cache_ttl = max(60, int(getattr(self._tuning, "similarity_cache_ttl_seconds", 86400)))
        self._similarity_local_cache_max_size = max(
            32,
            int(getattr(self._tuning, "similarity_local_cache_max_size", self.SIMILARITY_LOCAL_CACHE_MAX_SIZE)),
        )
        self._similarity_local_cache: OrderedDict[str, SimilarityResult] = OrderedDict()
        self._semantic_vector_enabled = bool(getattr(self._tuning, "semantic_vector_enabled", True))
        self._semantic_vector_model = str(getattr(self._tuning, "semantic_vector_model", "") or "").strip()
        self._semantic_vector_cache_ttl = max(
            60,
            int(getattr(self._tuning, "semantic_vector_cache_ttl_seconds", 86400)),
        )
        self._semantic_vector_local_cache_max_size = max(
            64,
            int(
                getattr(
                    self._tuning,
                    "semantic_vector_local_cache_max_size",
                    self.SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE,
                )
            ),
        )
        self._semantic_vector_local_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._semantic_vector_fail_until: float = 0.0

    def score_case(
        self,
        *,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        content_text: str,
        model: str | None = None,
    ) -> SimilarityResult:
        started = time.monotonic()
        passages = self._select_relevant_passages(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
            max_passages=self._passage_top_k,
        )
        candidate_excerpt = self._compose_passage_excerpt(passages=passages)
        if not candidate_excerpt:
            candidate_excerpt = self._build_candidate_excerpt(content_text, max_len=3200)
        cache_key = self._build_similarity_cache_key(
            mode="score",
            model=model,
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            candidate_excerpt=candidate_excerpt,
        )
        cached_result, cache_probe = self._load_similarity_cache_with_probe(cache_key)
        if cached_result is not None:
            self._log_similarity_metrics(
                mode="score",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                cache_hit=True,
                cache_source=str(cache_probe.get("source", "")),
                cache_probe=str(cache_probe.get("probe", "")),
                model=cached_result.model,
                score=cached_result.score,
                metadata=cached_result.metadata,
            )
            return cached_result

        target_tags = ", ".join(self._extract_transaction_tags(case_summary)) or "无"
        candidate_tags = ", ".join(self._extract_transaction_tags(f"{title} {case_digest}")) or "无"
        prompt = (
            "你是法律案例匹配评估器。必须只输出严格JSON，不允许任何额外文本。\n"
            "输出字段:\n"
            "{\n"
            '  "score": 0.0-1.0,\n'
            '  "decision": "high|medium|low|reject",\n'
            '  "reason": "不超过120字",\n'
            '  "facts_match": 0.0-1.0,\n'
            '  "legal_relation_match": 0.0-1.0,\n'
            '  "dispute_match": 0.0-1.0,\n'
            '  "damage_match": 0.0-1.0,\n'
            '  "key_conflicts": ["冲突点1","冲突点2"],\n'
            '  "evidence_spans": ["候选原文短语1","候选原文短语2"]\n'
            "}\n"
            "裁判规则:\n"
            "1) 重点比对事实要件、法律关系、争议焦点、损失类型。\n"
            "2) 如主体、法律关系、违约方式、损失类型明显不一致，decision 不得为 high，score 不得高于 0.60。\n"
            "3) evidence_spans 至少给出2条，且必须来自候选相关段落的原文短语。\n\n"
            f"关键词: {keyword}\n"
            f"目标案情: {case_summary}\n\n"
            f"目标交易标签: {target_tags}\n"
            f"候选交易标签: {candidate_tags}\n\n"
            f"候选标题: {title}\n"
            f"候选摘要: {case_digest}\n"
            f"候选相关段落: {candidate_excerpt}\n"
        )

        response = self._llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是法律案例匹配评估器，只输出JSON，不输出额外文本。",
                },
                {"role": "user", "content": prompt},
            ],
            backend="siliconflow",
            model=(model or None),
            fallback=False,
            temperature=0.0,
            max_tokens=self.SCORE_MAX_TOKENS,
            timeout_seconds=self.SCORE_TIMEOUT_SECONDS,
        )

        score = 0.0
        reason = ""
        metadata: dict[str, Any] = {}
        parsed = self._extract_json(response.content)
        fallback_score = self._extract_score_from_text(response.content)
        if not isinstance(parsed, dict) and fallback_score <= 0:
            parsed = self._repair_json_payload(raw_text=response.content, model=(model or response.model or None))
        if isinstance(parsed, dict):
            score = self._coerce_score(parsed.get("score", 0.0))
            reason = str(parsed.get("reason", "") or "")
            evidence_context = f"{title}\n{case_digest}\n{candidate_excerpt}"
            score = self._apply_structured_adjustments(score=score, payload=parsed, context_text=evidence_context)
            metadata = self._extract_structured_metadata(
                payload=parsed,
                adjusted_score=score,
                context_text=evidence_context,
            )
        else:
            score = fallback_score
            reason = (response.content or "")[:120]

        if score <= 0:
            overlap = self._keyword_overlap_score(
                keyword=keyword,
                title=title,
                case_digest=case_digest,
                content_text=content_text,
            )
            if overlap > 0:
                score = min(1.0, overlap * 0.75)
                reason = reason or f"关键词重合度补偿={overlap:.2f}"

        score = max(0.0, min(1.0, score))
        if not reason:
            reason = "模型未返回理由"
        result = SimilarityResult(score=score, reason=reason, model=response.model, metadata=metadata)
        self._save_similarity_cache(cache_key=cache_key, result=result)
        self._log_similarity_metrics(
            mode="score",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            cache_hit=False,
            cache_source=str(cache_probe.get("source", "")),
            cache_probe=str(cache_probe.get("probe", "")),
            model=result.model,
            score=result.score,
            metadata=result.metadata,
        )
        return result

    def rescore_borderline_case(
        self,
        *,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        content_text: str,
        first_score: float,
        first_reason: str,
        model: str | None = None,
    ) -> SimilarityResult:
        started = time.monotonic()
        passages = self._select_relevant_passages(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
            max_passages=min(3, self._passage_top_k),
        )
        candidate_excerpt = self._compose_passage_excerpt(passages=passages)
        if not candidate_excerpt:
            candidate_excerpt = self._build_candidate_excerpt(content_text, max_len=2400)
        cache_key = self._build_similarity_cache_key(
            mode="rescore",
            model=model,
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            candidate_excerpt=candidate_excerpt,
            first_score=first_score,
            first_reason=first_reason,
        )
        cached_result, cache_probe = self._load_similarity_cache_with_probe(cache_key)
        if cached_result is not None:
            self._log_similarity_metrics(
                mode="rescore",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                cache_hit=True,
                cache_source=str(cache_probe.get("source", "")),
                cache_probe=str(cache_probe.get("probe", "")),
                model=cached_result.model,
                score=cached_result.score,
                metadata=cached_result.metadata,
            )
            return cached_result

        target_tags = ", ".join(self._extract_transaction_tags(case_summary)) or "无"
        candidate_tags = ", ".join(self._extract_transaction_tags(f"{title} {case_digest}")) or "无"
        prompt = (
            "你要做第二次复判。必须只输出严格JSON，不允许任何额外文本。\n"
            "输出字段:\n"
            "{\n"
            '  "score": 0.0-1.0,\n'
            '  "decision": "high|medium|low|reject",\n'
            '  "reason": "不超过100字",\n'
            '  "facts_match": 0.0-1.0,\n'
            '  "legal_relation_match": 0.0-1.0,\n'
            '  "dispute_match": 0.0-1.0,\n'
            '  "damage_match": 0.0-1.0,\n'
            '  "key_conflicts": ["冲突点1","冲突点2"],\n'
            '  "evidence_spans": ["候选原文短语1","候选原文短语2"]\n'
            "}\n"
            "复判要求: 重点看交易关系、违约事实、损失类型、裁判结论是否同类。\n"
            "若存在关键冲突，score 不得高于 0.60。\n\n"
            f"关键词: {keyword}\n"
            f"目标案情: {case_summary}\n"
            f"目标交易标签: {target_tags}\n"
            f"候选交易标签: {candidate_tags}\n"
            f"首轮分数: {first_score:.3f}\n"
            f"首轮理由: {first_reason}\n\n"
            f"候选标题: {title}\n"
            f"候选摘要: {case_digest}\n"
            f"候选相关段落: {candidate_excerpt}\n"
        )
        response = self._llm.chat(
            messages=[
                {"role": "system", "content": "你是法律案例复判器，只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            backend="siliconflow",
            model=(model or None),
            fallback=False,
            temperature=0.0,
            max_tokens=self.RESCORE_MAX_TOKENS,
            timeout_seconds=self.RESCORE_TIMEOUT_SECONDS,
        )

        score = 0.0
        reason = ""
        metadata: dict[str, Any] = {}
        parsed = self._extract_json(response.content)
        fallback_score = self._extract_score_from_text(response.content)
        if not isinstance(parsed, dict) and fallback_score <= 0:
            parsed = self._repair_json_payload(raw_text=response.content, model=(model or response.model or None))
        if isinstance(parsed, dict):
            score = self._coerce_score(parsed.get("score", 0.0))
            reason = str(parsed.get("reason", "") or "")
            evidence_context = f"{title}\n{case_digest}\n{candidate_excerpt}"
            score = self._apply_structured_adjustments(score=score, payload=parsed, context_text=evidence_context)
            metadata = self._extract_structured_metadata(
                payload=parsed,
                adjusted_score=score,
                context_text=evidence_context,
            )
        else:
            score = fallback_score
            reason = (response.content or "")[:100]

        if score <= 0:
            score = max(0.0, min(1.0, first_score))
        if not reason:
            reason = first_reason or "复判未返回理由"
        result = SimilarityResult(
            score=max(0.0, min(1.0, score)),
            reason=reason,
            model=response.model,
            metadata=metadata,
        )
        self._save_similarity_cache(cache_key=cache_key, result=result)
        self._log_similarity_metrics(
            mode="rescore",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            cache_hit=False,
            cache_source=str(cache_probe.get("source", "")),
            cache_probe=str(cache_probe.get("probe", "")),
            model=result.model,
            score=result.score,
            metadata=result.metadata,
        )
        return result

    def coarse_recall_score(
        self,
        *,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        content_text: str,
    ) -> SimilarityResult:
        """阶段1宽召回：使用词项重合进行高召回初筛，不做严格判负。"""
        keyword_overlap = self._keyword_overlap_score(
            keyword=keyword,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        summary_overlap = self._summary_overlap_score(
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        query_text = f"{keyword} {case_summary}"
        document_text = f"{title} {case_digest} {(content_text or '')[:2400]}"

        bm25_score = self._bm25_proxy_score(
            query_text=query_text,
            document_text=document_text,
        )
        vector_lexical_score = self._vector_similarity_score(
            text_a=query_text, text_b=document_text, allow_semantic=False
        )
        passage_score = self._passage_alignment_score(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        metadata_score = self._metadata_hint_score(
            keyword=keyword,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        semantic_recheck = self._should_enable_semantic_vector_recheck(
            query_text=query_text,
            keyword_overlap=keyword_overlap,
            summary_overlap=summary_overlap,
            bm25_score=bm25_score,
            lexical_vector_score=vector_lexical_score,
            passage_score=passage_score,
            metadata_score=metadata_score,
        )
        vector_score = vector_lexical_score
        vector_mode = "lex"
        if semantic_recheck:
            vector_score = self._vector_similarity_score(text_a=query_text, text_b=document_text, allow_semantic=True)
            vector_mode = "sem"
        (
            weight_keyword,
            weight_summary,
            weight_bm25,
            weight_vector,
            weight_passage,
            weight_metadata,
        ) = self._recall_weights

        mixed_score = (
            weight_keyword * keyword_overlap
            + weight_summary * summary_overlap
            + weight_bm25 * bm25_score
            + weight_vector * vector_score
            + weight_passage * passage_score
            + weight_metadata * metadata_score
        )
        score = max(mixed_score, keyword_overlap, summary_overlap * 0.95, passage_score * 0.9)
        score = max(0.0, min(1.0, score))
        reason = (
            "宽召回混合:"
            f"kw={keyword_overlap:.2f};sum={summary_overlap:.2f};"
            f"bm25={bm25_score:.2f};vec={vector_score:.2f}[{vector_mode}];"
            f"passage={passage_score:.2f};meta={metadata_score:.2f}"
        )
        return SimilarityResult(score=score, reason=reason, model="coarse-heuristic")

    def _should_enable_semantic_vector_recheck(
        self,
        *,
        query_text: str,
        keyword_overlap: float,
        summary_overlap: float,
        bm25_score: float,
        lexical_vector_score: float,
        passage_score: float,
        metadata_score: float,
    ) -> bool:
        if not self._semantic_vector_enabled or not self._semantic_vector_model:
            return False

        strongest_signal = max(keyword_overlap, summary_overlap, bm25_score, lexical_vector_score, passage_score)
        if strongest_signal >= 0.72:
            return False

        weak_signal_count = sum(
            1
            for value in (
                keyword_overlap,
                summary_overlap,
                bm25_score,
                lexical_vector_score,
                passage_score,
                metadata_score,
            )
            if value < self.SEMANTIC_RECHECK_WEAK_SIGNAL_THRESHOLD
        )
        if weak_signal_count >= self.SEMANTIC_RECHECK_WEAK_SIGNAL_COUNT:
            return True

        baseline_score = (
            0.24 * keyword_overlap
            + 0.21 * summary_overlap
            + 0.18 * bm25_score
            + 0.19 * lexical_vector_score
            + 0.13 * passage_score
            + 0.05 * metadata_score
        )
        if baseline_score < self.SEMANTIC_RECHECK_BASELINE_THRESHOLD:
            return True

        query_term_count = len(self._dedupe_tokens(self._tokenize(query_text), max_tokens=24))
        return (
            query_term_count >= self.SEMANTIC_RECHECK_MIN_QUERY_TERMS
            and lexical_vector_score < self.SEMANTIC_RECHECK_LEXICAL_MAX
            and max(keyword_overlap, summary_overlap) < 0.58
        )

    def _passage_alignment_score(
        self,
        *,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        content_text: str,
    ) -> float:
        passages = self._select_relevant_passages(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
            max_passages=min(2, self._passage_top_k),
        )
        if not passages:
            return 0.0

        query_text = f"{keyword} {case_summary}"
        scores = [
            max(
                self._token_overlap_score(query_text, passage),
                self._vector_similarity_score(query_text, passage, allow_semantic=False),
            )
            for passage in passages
        ]
        return max(0.0, min(1.0, max(scores, default=0.0)))

    def _select_relevant_passages(
        self,
        *,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        content_text: str,
        max_passages: int,
    ) -> list[str]:
        paragraphs = self._split_paragraphs(content_text)
        if not paragraphs:
            return []

        query_text = f"{keyword} {case_summary} {title} {case_digest}"
        ranked: list[tuple[float, str]] = []
        for paragraph in paragraphs:
            overlap = self._token_overlap_score(query_text, paragraph)
            vector = self._vector_similarity_score(query_text, paragraph, allow_semantic=False)
            score = overlap * 0.58 + vector * 0.42
            if score <= 0:
                continue
            ranked.append((score, paragraph))

        ranked.sort(key=lambda x: x[0], reverse=True)
        top = [text for _, text in ranked[: max(1, max_passages)]]
        if not top:
            return []
        return self._dedupe_passages(top)

    def _split_paragraphs(self, content_text: str) -> list[str]:
        text = self._focus_content_after_fact_marker(content_text)
        if not text:
            return []
        text = text[: self._passage_max_chars]
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

    @staticmethod
    def _dedupe_passages(passages: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for passage in passages:
            key = passage[:160]
            if key in seen:
                continue
            seen.add(key)
            out.append(passage)
        return out

    def _compose_passage_excerpt(self, *, passages: list[str]) -> str:
        if not passages:
            return ""
        clipped = [p[: self._passage_preview_max_chars] for p in passages]
        return "\n---\n".join(f"[片段{i + 1}] {text}" for i, text in enumerate(clipped))

    @classmethod
    def _focus_content_after_fact_marker(cls, content_text: str) -> str:
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

    @classmethod
    def _bm25_proxy_score(cls, *, query_text: str, document_text: str) -> float:
        query_tokens = cls._tokenize(query_text)
        if not query_tokens:
            return 0.0
        doc_tokens = cls._tokenize(document_text)
        if not doc_tokens:
            return 0.0

        freq = Counter(doc_tokens)
        doc_len = max(1, len(doc_tokens))
        avg_dl = 280.0
        k1 = 1.2
        b = 0.75
        total = 0.0
        used = 0
        for token in cls._dedupe_tokens(query_tokens, max_tokens=20):
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

    def _vector_similarity_score(self, text_a: str, text_b: str, *, allow_semantic: bool = True) -> float:
        lexical = self._lexical_vector_similarity_score(text_a, text_b)
        semantic = self._semantic_vector_similarity_score(text_a, text_b) if allow_semantic else None
        if semantic is None:
            return lexical
        blended = semantic * self.VECTOR_SEMANTIC_WEIGHT + lexical * self.VECTOR_LEXICAL_WEIGHT
        return max(0.0, min(1.0, blended))

    @classmethod
    def _lexical_vector_similarity_score(cls, text_a: str, text_b: str) -> float:
        grams_a = cls._char_ngrams(text_a)
        grams_b = cls._char_ngrams(text_b)
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

    def _semantic_vector_similarity_score(self, text_a: str, text_b: str) -> float | None:
        if not self._semantic_vector_enabled or not self._semantic_vector_model:
            return None
        now = time.time()
        if now < self._semantic_vector_fail_until:
            return None

        vector_a = self._get_semantic_embedding(text_a)
        vector_b = self._get_semantic_embedding(text_b)
        if not vector_a or not vector_b:
            return None
        if len(vector_a) != len(vector_b):
            return None

        dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=False))
        norm_a = math.sqrt(sum(v * v for v in vector_a))
        norm_b = math.sqrt(sum(v * v for v in vector_b))
        if norm_a <= 0 or norm_b <= 0:
            return None
        cosine = dot / (norm_a * norm_b)
        return max(0.0, min(1.0, cosine))

    def _get_semantic_embedding(self, text: str) -> list[float] | None:
        normalized = self._normalize_embedding_text(text)
        if not normalized:
            return None
        cache_key = self._build_semantic_embedding_cache_key(
            model=self._semantic_vector_model,
            text=normalized,
        )
        local = self._read_semantic_vector_local_cache(cache_key)
        if local is not None:
            return local

        try:
            payload = cache.get(cache_key)
        except Exception:
            payload = None
        if isinstance(payload, list) and payload:
            vector = self._coerce_float_list(payload)
            if vector:
                self._write_semantic_vector_local_cache(cache_key=cache_key, vector=vector)
                return vector

        try:
            embedding_client = self._get_embedding_client()
            embedding_response = embedding_client.embeddings.create(
                model=self._semantic_vector_model,
                input=normalized,
                timeout=self.SEMANTIC_EMBEDDING_TIMEOUT_SECONDS,
            )
            rows = getattr(embedding_response, "data", None) or []
            if not rows:
                return None
            vector = self._coerce_float_list(getattr(rows[0], "embedding", None) or [])
            if not vector:
                return None
            self._write_semantic_vector_local_cache(cache_key=cache_key, vector=vector)
            try:
                cache.set(cache_key, vector, timeout=self._semantic_vector_cache_ttl)
            except Exception:
                pass
            return vector
        except Exception as exc:
            self._semantic_vector_fail_until = time.time() + self.SEMANTIC_EMBEDDING_FAIL_COOLDOWN_SECONDS
            logger.info("语义向量调用失败，回退字符向量", extra={"error": str(exc)})
            return None

    def _get_embedding_client(self) -> Any:
        if self._embedding_client is None:
            self._embedding_client = _LLMEmbeddingClientAdapter(self._llm)
        return self._embedding_client

    @classmethod
    def _char_ngrams(cls, text: str) -> Counter[str]:
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

    @classmethod
    def _token_overlap_score(cls, query_text: str, text: str) -> float:
        query_tokens = cls._dedupe_tokens(cls._tokenize(query_text), max_tokens=24)
        if not query_tokens:
            return 0.0
        haystack = (text or "").lower()
        matched = sum(1 for token in query_tokens if token.lower() in haystack)
        return matched / len(query_tokens)

    @classmethod
    def _metadata_hint_score(cls, *, keyword: str, title: str, case_digest: str, content_text: str) -> float:
        domain_terms = [
            "买卖合同",
            "买卖",
            "违约",
            "违约责任",
            "损失",
            "赔偿",
            "价差",
            "交货",
            "转卖",
            "合同价",
            "市场价格",
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

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        raw = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,10}", (text or "").lower())
        stopwords = {
            "以及",
            "或者",
            "如果",
            "因此",
            "应当",
            "需要",
            "有关",
            "关于",
            "因为",
            "但是",
            "其中",
            "并且",
            "法院认为",
            "本院认为",
            "原告",
            "被告",
        }
        return [token for token in raw if token not in stopwords]

    @staticmethod
    def _dedupe_tokens(tokens: list[str], *, max_tokens: int) -> list[str]:
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

    @classmethod
    def _build_candidate_excerpt(cls, content_text: str, *, max_len: int = 3200) -> str:
        text = cls._focus_content_after_fact_marker(content_text)
        if len(text) <= max_len:
            return text
        head = text[:1400]
        middle_start = max(0, len(text) // 2 - 450)
        middle = text[middle_start : middle_start + 900]
        tail = text[-900:]
        return f"{head}\n...\n{middle}\n...\n{tail}"

    @classmethod
    def _coerce_score(cls, value: object) -> float:
        raw = str(value or "").strip().replace("％", "%")
        if not raw:
            return 0.0

        percent_match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*%", raw)
        if percent_match:
            return cls._normalize_score(float(percent_match.group(1)))

        numeric_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
        if not numeric_match:
            return 0.0
        try:
            parsed = float(numeric_match.group(1))
        except (TypeError, ValueError):
            return 0.0
        return cls._normalize_score(parsed)

    @staticmethod
    def _normalize_score(score: float) -> float:
        if score > 1.0 and score <= 100.0:
            return score / 100.0
        if score < 0:
            return 0.0
        return min(1.0, score)

    @classmethod
    def _extract_score_from_text(cls, text: str) -> float:
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
            score = cls._coerce_score(match.group(1))
            if score > 0:
                return score
        return 0.0

    @staticmethod
    def _keyword_overlap_score(*, keyword: str, title: str, case_digest: str, content_text: str) -> float:
        raw_tokens = re.split(r"[\s,，;；、]+", (keyword or "").lower())
        tokens = [token for token in raw_tokens if token and len(token) >= 2]
        if not tokens:
            return 0.0

        haystack = f"{title} {case_digest} {(content_text or '')[:1200]}".lower()
        matched = sum(1 for token in tokens if token in haystack)
        return matched / len(tokens)

    @staticmethod
    def _summary_overlap_score(*, case_summary: str, title: str, case_digest: str, content_text: str) -> float:
        summary_tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", (case_summary or "").lower())
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

    @staticmethod
    def _extract_json(text: str) -> dict[str, object] | None:
        if not text:
            return None

        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```[a-zA-Z0-9_-]*", "", candidate).strip()
            candidate = candidate.removesuffix("```").strip()

        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None

        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            logger.warning("相似度JSON解析失败", extra={"preview": text[:200]})

        return None

    def _repair_json_payload(self, *, raw_text: str, model: str | None = None) -> dict[str, object] | None:
        content = (raw_text or "").strip()
        if not content:
            return None

        prompt = (
            "请将下面文本修复为严格JSON对象，且只输出JSON，不要输出其他文本。\n"
            "字段要求:\n"
            "{\n"
            '  "score": 0.0-1.0,\n'
            '  "decision": "high|medium|low|reject",\n'
            '  "reason": "不超过120字",\n'
            '  "facts_match": 0.0-1.0,\n'
            '  "legal_relation_match": 0.0-1.0,\n'
            '  "dispute_match": 0.0-1.0,\n'
            '  "damage_match": 0.0-1.0,\n'
            '  "key_conflicts": [],\n'
            '  "evidence_spans": []\n'
            "}\n"
            "若原文缺失字段，请保守补全，score不得超过0.50。\n\n"
            f"原文:\n{content[:3200]}"
        )
        try:
            response = self._llm.chat(
                messages=[
                    {"role": "system", "content": "你是JSON修复器，只输出JSON对象。"},
                    {"role": "user", "content": prompt},
                ],
                backend="siliconflow",
                model=(model or None),
                fallback=False,
                temperature=0.0,
                max_tokens=self.JSON_REPAIR_MAX_TOKENS,
                timeout_seconds=self.JSON_REPAIR_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.info("相似度JSON修复调用失败", extra={"error": str(exc)})
            return None

        parsed = self._extract_json(response.content)
        if isinstance(parsed, dict):
            return parsed
        return None

    @classmethod
    def _apply_structured_adjustments(
        cls,
        *,
        score: float,
        payload: dict[str, object],
        context_text: str = "",
    ) -> float:
        adjusted = max(0.0, min(1.0, float(score)))

        decision = str(payload.get("decision", "") or "").strip().lower()
        if decision in {"reject", "不相似"}:
            adjusted = min(adjusted, 0.45)
        elif decision in {"low", "低"}:
            adjusted = min(adjusted, 0.6)
        elif decision in {"medium", "中"}:
            adjusted = min(adjusted, 0.85)

        component_scores = [
            cls._coerce_score(payload.get("facts_match", 1.0)),
            cls._coerce_score(payload.get("legal_relation_match", 1.0)),
            cls._coerce_score(payload.get("dispute_match", 1.0)),
            cls._coerce_score(payload.get("damage_match", 1.0)),
        ]
        min_component = min(component_scores)
        if min_component < 0.2:
            adjusted = min(adjusted, 0.55)
        elif min_component < 0.35:
            adjusted = min(adjusted, 0.68)

        conflicts = cls._normalize_text_list(payload.get("key_conflicts"))
        if conflicts and any(any(needle in conflict for needle in cls.HARD_CONFLICT_NEEDLES) for conflict in conflicts):
            adjusted = min(adjusted, 0.62)

        evidence_spans = cls._normalize_text_list(payload.get("evidence_spans"))
        if evidence_spans and len(evidence_spans) < 2:
            adjusted = min(adjusted, 0.82)
        if evidence_spans:
            hit_count, valid_count = cls._evidence_span_hit_count(
                evidence_spans=evidence_spans,
                context_text=context_text,
            )
            if valid_count >= 2:
                hit_ratio = hit_count / valid_count
                if hit_ratio < 0.5:
                    adjusted = min(adjusted, 0.72)
                elif hit_ratio < 1.0:
                    adjusted = min(adjusted, 0.82)
            elif valid_count == 1 and hit_count == 0:
                adjusted = min(adjusted, 0.78)

        return max(0.0, min(1.0, adjusted))

    @staticmethod
    def _normalize_text_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @classmethod
    def _extract_structured_metadata(
        cls,
        *,
        payload: dict[str, object],
        adjusted_score: float,
        context_text: str = "",
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {"score_adjusted": round(max(0.0, min(1.0, adjusted_score)), 4)}
        raw_score = cls._coerce_score(payload.get("score", 0.0))
        metadata["score_raw"] = round(max(0.0, min(1.0, raw_score)), 4)

        decision = str(payload.get("decision", "") or "").strip().lower()
        if decision:
            metadata["decision"] = decision

        for field_name in ("facts_match", "legal_relation_match", "dispute_match", "damage_match"):
            if field_name not in payload:
                continue
            value = cls._coerce_score(payload.get(field_name, 0.0))
            metadata[field_name] = round(max(0.0, min(1.0, value)), 4)

        conflicts = [item[:120] for item in cls._normalize_text_list(payload.get("key_conflicts"))[:6]]
        if conflicts:
            metadata["key_conflicts"] = conflicts

        evidence_spans = [item[:160] for item in cls._normalize_text_list(payload.get("evidence_spans"))[:6]]
        if evidence_spans:
            metadata["evidence_spans"] = evidence_spans
            hit_count, valid_count = cls._evidence_span_hit_count(
                evidence_spans=evidence_spans,
                context_text=context_text,
            )
            if valid_count > 0:
                metadata["evidence_hits"] = hit_count
                metadata["evidence_total"] = valid_count
                metadata["evidence_hit_ratio"] = round(hit_count / valid_count, 4)

        return metadata

    @classmethod
    def _evidence_span_hit_count(cls, *, evidence_spans: list[str], context_text: str) -> tuple[int, int]:
        normalized_context = cls._normalize_match_text(context_text)
        if not normalized_context:
            return 0, 0

        hits = 0
        total = 0
        for span in evidence_spans:
            normalized_span = cls._normalize_match_text(span)
            if len(normalized_span) < cls.MIN_EVIDENCE_SPAN_CHARS:
                continue
            total += 1
            if normalized_span in normalized_context:
                hits += 1
        return hits, total

    @staticmethod
    def _normalize_match_text(text: str) -> str:
        if not text:
            return ""
        normalized = re.sub(r"\s+", "", text)
        normalized = re.sub(r"[，。；：、“”‘’\"'（）()【】\[\]《》<>、,.!?！？:;·\-]", "", normalized)
        return normalized.lower()

    @staticmethod
    def _extract_transaction_tags(text: str) -> list[str]:
        normalized = (text or "").strip().lower()
        if not normalized:
            return []

        tag_rules: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("转卖", ("转卖", "转售", "另行出售", "卖给他人")),
            ("交货迟延", ("未按时", "逾期交货", "迟延交货", "延迟交货", "未交货", "不交货")),
            ("质量瑕疵", ("质量", "瑕疵", "不合格")),
            ("价差争议", ("价格", "价差", "高价另购", "市场价格", "固定价格")),
            ("付款迟延", ("逾期付款", "迟延付款", "未付款", "不付款", "拖欠")),
        )
        tags: list[str] = []
        for label, needles in tag_rules:
            if any(needle in normalized for needle in needles):
                tags.append(label)
        return tags

    @classmethod
    def _log_similarity_metrics(
        cls,
        *,
        mode: str,
        elapsed_ms: int,
        cache_hit: bool,
        cache_source: str = "",
        cache_probe: str = "",
        model: str,
        score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        extra_payload: dict[str, Any] = {
            "mode": str(mode or ""),
            "elapsed_ms": max(0, int(elapsed_ms)),
            "cache_hit": bool(cache_hit),
            "model": str(model or ""),
            "score": round(max(0.0, min(1.0, float(score))), 4),
        }
        normalized_cache_source = str(cache_source or "").strip().lower()
        if normalized_cache_source:
            extra_payload["cache_source"] = normalized_cache_source
        normalized_cache_probe = str(cache_probe or "").strip().lower()
        if normalized_cache_probe:
            extra_payload["cache_probe"] = normalized_cache_probe
        if isinstance(metadata, dict):
            decision = str(metadata.get("decision", "") or "").strip().lower()
            if decision:
                extra_payload["decision"] = decision
            conflicts = metadata.get("key_conflicts")
            if isinstance(conflicts, list):
                normalized_conflicts = [str(item).strip() for item in conflicts if str(item).strip()]
                extra_payload["has_conflict"] = bool(normalized_conflicts)
                if normalized_conflicts:
                    extra_payload["conflict_count"] = len(normalized_conflicts)
        logger.info("案例相似度评分", extra=extra_payload)

    def _build_similarity_cache_key(
        self,
        *,
        mode: str,
        model: str | None,
        keyword: str,
        case_summary: str,
        title: str,
        case_digest: str,
        candidate_excerpt: str,
        first_score: float | None = None,
        first_reason: str | None = None,
    ) -> str:
        payload = {
            "v": self.SIMILARITY_PROMPT_VERSION,
            "mode": mode,
            "model": str(model or "").strip(),
            "keyword": re.sub(r"\s+", " ", (keyword or "")).strip(),
            "case_summary": re.sub(r"\s+", " ", (case_summary or "")).strip(),
            "title": re.sub(r"\s+", " ", (title or "")).strip(),
            "case_digest": re.sub(r"\s+", " ", (case_digest or "")).strip(),
            "candidate_excerpt": re.sub(r"\s+", " ", (candidate_excerpt or "")).strip(),
        }
        if first_score is not None:
            payload["first_score"] = str(round(float(first_score), 4))
        if first_reason:
            payload["first_reason"] = re.sub(r"\s+", " ", first_reason).strip()[:220]
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{self.SIMILARITY_CACHE_PREFIX}:{digest}"

    def _load_similarity_cache(self, cache_key: str) -> SimilarityResult | None:
        cached, _ = self._load_similarity_cache_with_probe(cache_key)
        return cached

    def _load_similarity_cache_with_probe(self, cache_key: str) -> tuple[SimilarityResult | None, dict[str, str]]:
        if not cache_key:
            return None, {"source": "none", "probe": "empty_key"}
        local = self._read_similarity_local_cache(cache_key)
        if local is not None:
            return local, {"source": "local", "probe": "local_hit"}

        try:
            payload = cache.get(cache_key)
        except Exception:
            return None, {"source": "none", "probe": "shared_error"}
        if payload is None:
            return None, {"source": "none", "probe": "shared_miss"}
        if not isinstance(payload, dict):
            return None, {"source": "none", "probe": "shared_invalid_payload"}
        cached = self._deserialize_similarity_result(payload)
        if cached is None:
            return None, {"source": "none", "probe": "shared_invalid_result"}
        self._write_similarity_local_cache(cache_key=cache_key, result=cached)
        return cached, {"source": "shared", "probe": "shared_hit"}

    def _save_similarity_cache(self, *, cache_key: str, result: SimilarityResult) -> None:
        if not cache_key:
            return
        self._write_similarity_local_cache(cache_key=cache_key, result=result)
        payload = self._serialize_similarity_result(result)
        try:
            cache.set(cache_key, payload, timeout=self._similarity_cache_ttl)
        except Exception:
            return

    def _read_similarity_local_cache(self, cache_key: str) -> SimilarityResult | None:
        if not cache_key:
            return None
        cached = self._similarity_local_cache.get(cache_key)
        if cached is None:
            return None
        self._similarity_local_cache.move_to_end(cache_key, last=True)
        return cached

    def _write_similarity_local_cache(self, *, cache_key: str, result: SimilarityResult) -> None:
        if not cache_key:
            return
        self._similarity_local_cache[cache_key] = result
        self._similarity_local_cache.move_to_end(cache_key, last=True)
        while len(self._similarity_local_cache) > self._similarity_local_cache_max_size:
            self._similarity_local_cache.popitem(last=False)

    def _read_semantic_vector_local_cache(self, cache_key: str) -> list[float] | None:
        if not cache_key:
            return None
        cached = self._semantic_vector_local_cache.get(cache_key)
        if cached is None:
            return None
        self._semantic_vector_local_cache.move_to_end(cache_key, last=True)
        return cached

    def _write_semantic_vector_local_cache(self, *, cache_key: str, vector: list[float]) -> None:
        if not cache_key:
            return
        self._semantic_vector_local_cache[cache_key] = vector
        self._semantic_vector_local_cache.move_to_end(cache_key, last=True)
        while len(self._semantic_vector_local_cache) > self._semantic_vector_local_cache_max_size:
            self._semantic_vector_local_cache.popitem(last=False)

    @staticmethod
    def _serialize_similarity_result(result: SimilarityResult) -> dict[str, Any]:
        return {
            "score": float(result.score),
            "reason": str(result.reason or ""),
            "model": str(result.model or ""),
            "metadata": result.metadata if isinstance(result.metadata, dict) else {},
        }

    @staticmethod
    def _deserialize_similarity_result(payload: dict[str, Any]) -> SimilarityResult | None:
        try:
            score = float(payload.get("score", 0.0))
        except (TypeError, ValueError):
            return None
        reason = str(payload.get("reason", "") or "")
        model = str(payload.get("model", "") or "")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        return SimilarityResult(
            score=max(0.0, min(1.0, score)),
            reason=reason,
            model=model,
            metadata=metadata,
        )

    @classmethod
    def _build_semantic_embedding_cache_key(cls, *, model: str, text: str) -> str:
        raw = f"{model}|{text}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{cls.SEMANTIC_EMBEDDING_CACHE_PREFIX}:{digest}"

    @classmethod
    def _normalize_embedding_text(cls, text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "")).strip()
        if not normalized:
            return ""
        return normalized[: cls.SEMANTIC_EMBEDDING_TEXT_MAX_CHARS]

    @staticmethod
    def _coerce_float_list(value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        out: list[float] = []
        for item in value:
            try:
                out.append(float(item))
            except (TypeError, ValueError):
                return []
        return out
