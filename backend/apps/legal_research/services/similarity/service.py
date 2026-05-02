"""案例相似度 - 核心评分编排."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from django.core.cache import cache

from apps.core.interfaces import ServiceLocator
from .tuning_config import LegalResearchTuningConfig

from . import cache as cache_mod
from . import json_utils as json_utils
from . import passage as passage_mod
from . import scorers as scorers

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
        similarity_cache_ttl = max(60, int(getattr(self._tuning, "similarity_cache_ttl_seconds", 86400)))
        semantic_vector_cache_ttl = max(60, int(getattr(self._tuning, "semantic_vector_cache_ttl_seconds", 86400)))
        self._semantic_vector_enabled = bool(getattr(self._tuning, "semantic_vector_enabled", True))
        self._semantic_vector_model = str(getattr(self._tuning, "semantic_vector_model", "") or "").strip()
        self._semantic_vector_fail_until: float = 0.0

        self._similarity_cache = cache_mod.SimilarityCacheManager(
            cache_ttl=similarity_cache_ttl,
            local_cache_max_size=max(
                32,
                int(getattr(self._tuning, "similarity_local_cache_max_size", self.SIMILARITY_LOCAL_CACHE_MAX_SIZE)),
            ),
            result_class=SimilarityResult,
        )
        self._semantic_vector_cache = cache_mod.SemanticVectorCacheManager(
            cache_ttl=semantic_vector_cache_ttl,
            local_cache_max_size=max(
                64,
                int(
                    getattr(
                        self._tuning,
                        "semantic_vector_local_cache_max_size",
                        self.SEMANTIC_VECTOR_LOCAL_CACHE_MAX_SIZE,
                    )
                ),
            ),
        )

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
        passages = passage_mod.select_relevant_passages(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
            max_passages=self._passage_top_k,
            passage_max_chars=self._passage_max_chars,
        )
        candidate_excerpt = passage_mod.compose_passage_excerpt(
            passages=passages,
            preview_max_chars=self._passage_preview_max_chars,
        )
        if not candidate_excerpt:
            candidate_excerpt = scorers.build_candidate_excerpt(content_text, max_len=3200)
        cache_key = cache_mod.build_similarity_cache_key(
            mode="score",
            model=model,
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            candidate_excerpt=candidate_excerpt,
        )
        cached_result, cache_probe = self._similarity_cache.load(cache_key)
        if cached_result is not None:
            result: SimilarityResult = cached_result
            self._log_similarity_metrics(
                mode="score",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                cache_hit=True,
                cache_source=str(cache_probe.get("source", "")),
                cache_probe=str(cache_probe.get("probe", "")),
                model=result.model,
                score=result.score,
                metadata=result.metadata,
            )
            return result

        target_tags = ", ".join(json_utils.extract_transaction_tags(case_summary)) or "无"
        candidate_tags = ", ".join(json_utils.extract_transaction_tags(f"{title} {case_digest}")) or "无"
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
            model=(model or None),
            fallback=True,
            temperature=0.0,
            max_tokens=self.SCORE_MAX_TOKENS,
            timeout_seconds=self.SCORE_TIMEOUT_SECONDS,
        )

        score = 0.0
        reason = ""
        metadata: dict[str, Any] = {}
        parsed = json_utils.extract_json(response.content)
        fallback_score = scorers.extract_score_from_text(response.content)
        if not isinstance(parsed, dict) and fallback_score <= 0:
            parsed = self._repair_json_payload(raw_text=response.content, model=(model or response.model or None))
        if isinstance(parsed, dict):
            score = scorers.coerce_score(parsed.get("score", 0.0))
            reason = str(parsed.get("reason", "") or "")
            evidence_context = f"{title}\n{case_digest}\n{candidate_excerpt}"
            score = json_utils.apply_structured_adjustments(score=score, payload=parsed, context_text=evidence_context)
            metadata = json_utils.extract_structured_metadata(
                payload=parsed,
                adjusted_score=score,
                context_text=evidence_context,
            )
        else:
            score = fallback_score
            reason = (response.content or "")[:120]

        if score <= 0:
            overlap = scorers.keyword_overlap_score(
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
        self._similarity_cache.save(cache_key=cache_key, result=result)
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
        passages = passage_mod.select_relevant_passages(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
            max_passages=min(3, self._passage_top_k),
            passage_max_chars=self._passage_max_chars,
        )
        candidate_excerpt = passage_mod.compose_passage_excerpt(
            passages=passages,
            preview_max_chars=self._passage_preview_max_chars,
        )
        if not candidate_excerpt:
            candidate_excerpt = scorers.build_candidate_excerpt(content_text, max_len=2400)
        cache_key = cache_mod.build_similarity_cache_key(
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
        cached_result, cache_probe = self._similarity_cache.load(cache_key)
        if cached_result is not None:
            result: SimilarityResult = cached_result
            self._log_similarity_metrics(
                mode="rescore",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                cache_hit=True,
                cache_source=str(cache_probe.get("source", "")),
                cache_probe=str(cache_probe.get("probe", "")),
                model=result.model,
                score=result.score,
                metadata=result.metadata,
            )
            return result

        target_tags = ", ".join(json_utils.extract_transaction_tags(case_summary)) or "无"
        candidate_tags = ", ".join(json_utils.extract_transaction_tags(f"{title} {case_digest}")) or "无"
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
            model=(model or None),
            fallback=True,
            temperature=0.0,
            max_tokens=self.RESCORE_MAX_TOKENS,
            timeout_seconds=self.RESCORE_TIMEOUT_SECONDS,
        )

        score = 0.0
        reason = ""
        metadata: dict[str, Any] = {}
        parsed = json_utils.extract_json(response.content)
        fallback_score = scorers.extract_score_from_text(response.content)
        if not isinstance(parsed, dict) and fallback_score <= 0:
            parsed = self._repair_json_payload(raw_text=response.content, model=(model or response.model or None))
        if isinstance(parsed, dict):
            score = scorers.coerce_score(parsed.get("score", 0.0))
            reason = str(parsed.get("reason", "") or "")
            evidence_context = f"{title}\n{case_digest}\n{candidate_excerpt}"
            score = json_utils.apply_structured_adjustments(score=score, payload=parsed, context_text=evidence_context)
            metadata = json_utils.extract_structured_metadata(
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
        self._similarity_cache.save(cache_key=cache_key, result=result)
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
        keyword_overlap = scorers.keyword_overlap_score(
            keyword=keyword,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        summary_overlap = scorers.summary_overlap_score(
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        query_text = f"{keyword} {case_summary}"
        document_text = f"{title} {case_digest} {(content_text or '')[:2400]}"

        bm25_score = scorers.bm25_proxy_score(
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
        metadata_score = scorers.metadata_hint_score(
            keyword=keyword,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
        )
        semantic_always_on = bool(getattr(self._tuning, "semantic_vector_always_on", False))
        semantic_recheck = semantic_always_on or self._should_enable_semantic_vector_recheck(
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

        query_term_count = len(scorers.dedupe_tokens(scorers.tokenize(query_text), max_tokens=24))
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
        return passage_mod.passage_alignment_score(
            keyword=keyword,
            case_summary=case_summary,
            title=title,
            case_digest=case_digest,
            content_text=content_text,
            passage_max_chars=self._passage_max_chars,
            passage_top_k=self._passage_top_k,
        )

    def _vector_similarity_score(self, text_a: str, text_b: str, *, allow_semantic: bool = True) -> float:
        lexical = scorers.lexical_vector_similarity_score(text_a, text_b)
        semantic = self._semantic_vector_similarity_score(text_a, text_b) if allow_semantic else None
        if semantic is None:
            return lexical
        blended = semantic * self.VECTOR_SEMANTIC_WEIGHT + lexical * self.VECTOR_LEXICAL_WEIGHT
        return max(0.0, min(1.0, blended))

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
        normalized = cache_mod.normalize_embedding_text(text)
        if not normalized:
            return None
        cache_key = cache_mod.build_semantic_embedding_cache_key(
            model=self._semantic_vector_model,
            text=normalized,
        )
        local = self._semantic_vector_cache.read_local(cache_key)
        if local is not None:
            return local

        django_cached = self._semantic_vector_cache.load_from_django_cache(cache_key)
        if django_cached is not None:
            return django_cached

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
            vector = cache_mod.coerce_float_list(getattr(rows[0], "embedding", None) or [])
            if not vector:
                return None
            self._semantic_vector_cache.save_to_django_cache(cache_key=cache_key, vector=vector)
            return vector
        except Exception as exc:
            self._semantic_vector_fail_until = time.time() + self.SEMANTIC_EMBEDDING_FAIL_COOLDOWN_SECONDS
            logger.info("语义向量调用失败，回退字符向量", extra={"error": str(exc)})
            return None

    def _get_embedding_client(self) -> Any:
        if self._embedding_client is None:
            self._embedding_client = _LLMEmbeddingClientAdapter(self._llm)
        return self._embedding_client

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
                model=(model or None),
                fallback=True,
                temperature=0.0,
                max_tokens=self.JSON_REPAIR_MAX_TOKENS,
                timeout_seconds=self.JSON_REPAIR_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.info("相似度JSON修复调用失败", extra={"error": str(exc)})
            return None

        parsed = json_utils.extract_json(response.content)
        if isinstance(parsed, dict):
            return parsed
        return None

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


# Re-export for backward compatibility
from .scorers import (
    bm25_proxy_score,
    build_candidate_excerpt,
    char_ngrams,
    coerce_score,
    dedupe_tokens,
    extract_score_from_text,
    focus_content_after_fact_marker,
    keyword_overlap_score,
    lexical_vector_similarity_score,
    metadata_hint_score,
    normalize_score,
    summary_overlap_score,
    tokenize,
    token_overlap_score,
)
from .json_utils import (
    apply_structured_adjustments,
    extract_json,
    extract_structured_metadata,
    extract_transaction_tags,
)
from .passage import (
    compose_passage_excerpt,
    dedupe_passages,
    passage_alignment_score,
    select_relevant_passages,
    split_paragraphs,
)
from .cache import (
    SimilarityCacheManager,
    SemanticVectorCacheManager,
    build_similarity_cache_key,
    build_semantic_embedding_cache_key,
    normalize_embedding_text,
)
