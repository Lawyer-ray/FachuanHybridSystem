from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from django.apps import apps as django_apps
from django.core.cache import cache
from django.utils import timezone

from apps.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDenied,
    RecognitionTimeoutError,
    ServiceUnavailableError,
    ValidationException,
)
from apps.core.llm.config import LLMConfig
from apps.legal_research.models import LegalResearchSearchMode, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.schemas.legal_research_schemas import (
    AgentSearchQueryTraceOut,
    AgentSearchRequestV1,
    AgentSearchResponseV1,
    AgentSearchSnippetsOut,
    AgentSearchSubscoresOut,
    RetrievalHitV1,
)
from apps.legal_research.services.keywords import normalize_keyword_query
from apps.legal_research.services.task.executor import LegalResearchExecutor
from apps.legal_research.services.task.event_service import LegalResearchTaskEventService
from apps.legal_research.services.task.service import LegalResearchTaskService

logger = logging.getLogger(__name__)


def _get_account_credential_model() -> Any:
    return django_apps.get_model("organization", "AccountCredential")


class LegalResearchCapabilityService:
    IDEMPOTENCY_TTL_SECONDS = 1800
    CACHE_PREFIX = "legal_research:capability:v1"
    THREAD_NAME_PREFIX = "legal-research-capability"
    MAX_DIRECT_CONCURRENCY = 3
    DIRECT_CONCURRENCY_WAIT_SECONDS = 2.0
    _DIRECT_SEMAPHORE = threading.BoundedSemaphore(MAX_DIRECT_CONCURRENCY)
    FAILURE_CIRCUIT_THRESHOLD = 3
    FAILURE_CIRCUIT_COOLDOWN_SECONDS = 180
    SNIPPET_MAX_CHARS = 360
    SNIPPET_SCAN_MAX_CHARS = 12000
    SNIPPET_CAPTURE_MAX_CHARS = 1600
    HARD_CONFLICT_NEEDLES: tuple[str, ...] = (
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
    INTENT_PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
        "similar_case": {
            "base": 0.42,
            "facts": 0.23,
            "legal": 0.18,
            "dispute": 0.12,
            "damage": 0.05,
            "same_court_bonus": 0.0,
            "reasoning_bonus": 0.0,
            "holdings_bonus": 0.0,
        },
        "same_court_precedent": {
            "base": 0.32,
            "facts": 0.16,
            "legal": 0.24,
            "dispute": 0.09,
            "damage": 0.04,
            "same_court_bonus": 0.11,
            "reasoning_bonus": 0.03,
            "holdings_bonus": 0.01,
        },
    }
    COURT_LEVEL_KEYWORDS: tuple[tuple[str, str], ...] = (
        ("最高人民法院", "supreme"),
        ("高级人民法院", "high"),
        ("中级人民法院", "middle"),
        ("知识产权法院", "specialized"),
        ("互联网法院", "specialized"),
        ("海事法院", "specialized"),
        ("铁路运输法院", "specialized"),
        ("人民法院", "basic"),
    )
    REGION_CODE_PREFIX: dict[str, str] = {
        "11": "北京",
        "12": "天津",
        "13": "河北",
        "14": "山西",
        "15": "内蒙古",
        "21": "辽宁",
        "22": "吉林",
        "23": "黑龙江",
        "31": "上海",
        "32": "江苏",
        "33": "浙江",
        "34": "安徽",
        "35": "福建",
        "36": "江西",
        "37": "山东",
        "41": "河南",
        "42": "湖北",
        "43": "湖南",
        "44": "广东",
        "45": "广西",
        "46": "海南",
        "50": "重庆",
        "51": "四川",
        "52": "贵州",
        "53": "云南",
        "54": "西藏",
        "61": "陕西",
        "62": "甘肃",
        "63": "青海",
        "64": "宁夏",
        "65": "新疆",
    }

    def __init__(self) -> None:
        self._task_service = LegalResearchTaskService()

    def search(
        self,
        *,
        payload: AgentSearchRequestV1,
        user: Any | None,
        idempotency_key: str = "",
    ) -> AgentSearchResponseV1:
        key = idempotency_key.strip()
        body_hash = self._payload_hash(payload=payload, user=user)
        if key:
            cached = self._load_idempotent_response(user=user, idempotency_key=key, body_hash=body_hash)
            if cached is not None:
                return cached

        credential = self._resolve_credential(payload=payload, user=user)
        if self._is_failure_circuit_open(credential_id=credential.id):
            raise ServiceUnavailableError(
                message="案例检索能力暂时降级，请稍后重试",
                code="LEGAL_RESEARCH_CAPABILITY_SOURCE_DEGRADED",
                errors={"credential_id": credential.id},
                service_name="legal_research",
            )
        keyword, case_summary = self._build_keyword_and_summary(payload=payload)
        timeout_ms = int(payload.budget.timeout_ms)
        started = time.monotonic()

        task = LegalResearchTask.objects.create(
            created_by=user,
            credential=credential,
            source="weike",
            keyword=keyword,
            case_summary=case_summary,
            search_mode=payload.search_mode or LegalResearchSearchMode.EXPANDED,
            target_count=int(payload.target_count),
            max_candidates=int(payload.budget.max_candidates),
            min_similarity_score=0.9,
            status=LegalResearchTaskStatus.PENDING,
            message="能力调用执行中",
            llm_backend=LLMConfig.get_default_backend(),
            llm_model=LLMConfig.get_default_model(),
        )

        acquired = self._DIRECT_SEMAPHORE.acquire(timeout=self.DIRECT_CONCURRENCY_WAIT_SECONDS)
        if not acquired:
            self._mark_failure_circuit(credential_id=credential.id)
            LegalResearchTaskEventService.record_event(
                task_id=task.id,
                stage="search",
                source="system",
                interface_name="capability_direct_call",
                method="POST",
                status_code=503,
                duration_ms=0,
                success=False,
                error_code="LEGAL_RESEARCH_CAPABILITY_BUSY",
                error_message="capability busy",
                request_summary={
                    "intent": payload.intent,
                    "target_count": payload.target_count,
                    "max_candidates": payload.budget.max_candidates,
                },
                response_summary={"status": "failed"},
            )
            raise ServiceUnavailableError(
                message="案例检索能力调用繁忙，请稍后重试",
                code="LEGAL_RESEARCH_CAPABILITY_BUSY",
                errors={"max_concurrency": self.MAX_DIRECT_CONCURRENCY},
                service_name="legal_research",
            )

        try:
            run_payload = self._execute_with_timeout(task_id=str(task.id), timeout_ms=timeout_ms)
        except FutureTimeoutError:
            self._mark_failure_circuit(credential_id=credential.id)
            self._mark_timeout(task=task, timeout_ms=timeout_ms)
            LegalResearchTaskEventService.record_event(
                task_id=task.id,
                stage="search",
                source="system",
                interface_name="capability_direct_call",
                method="POST",
                status_code=504,
                duration_ms=max(0, timeout_ms),
                success=False,
                error_code="LEGAL_RESEARCH_CAPABILITY_TIMEOUT",
                error_message="capability timeout",
                request_summary={
                    "intent": payload.intent,
                    "target_count": payload.target_count,
                    "max_candidates": payload.budget.max_candidates,
                },
                response_summary={"status": "failed"},
            )
            raise RecognitionTimeoutError(
                message="案例检索能力调用超时",
                code="LEGAL_RESEARCH_CAPABILITY_TIMEOUT",
                errors={"task_id": task.id, "timeout_ms": timeout_ms},
                timeout_seconds=max(1.0, float(timeout_ms) / 1000.0),
            ) from None
        finally:
            self._DIRECT_SEMAPHORE.release()

        task.refresh_from_db()
        payload_status = str((run_payload or {}).get("status") or "").strip().lower()
        if task.status == LegalResearchTaskStatus.FAILED or payload_status == "failed":
            error_detail = str(task.error or (run_payload or {}).get("error") or "unknown_error")
            self._mark_failure_circuit(credential_id=credential.id)
            LegalResearchTaskEventService.record_event(
                task_id=task.id,
                stage="search",
                source="system",
                interface_name="capability_direct_call",
                method="POST",
                status_code=503,
                duration_ms=max(1, int((time.monotonic() - started) * 1000)),
                success=False,
                error_code="LEGAL_RESEARCH_CAPABILITY_FAILED",
                error_message=error_detail,
                request_summary={
                    "intent": payload.intent,
                    "target_count": payload.target_count,
                    "max_candidates": payload.budget.max_candidates,
                },
                response_summary={"status": "failed"},
            )
            raise ServiceUnavailableError(
                message="案例检索能力调用失败",
                code="LEGAL_RESEARCH_CAPABILITY_FAILED",
                errors={"task_id": task.id, "detail": error_detail},
                service_name="legal_research",
            )

        ordered_results = list(task.results.all().order_by("rank", "created_at"))
        filtered_results = self._apply_hard_filters(results=ordered_results, payload=payload)
        hits = [self._serialize_hit(item=result) for result in filtered_results]
        hits = self._apply_intent_profile(hits=hits, payload=payload)
        hits = hits[: max(1, int(payload.target_count))]
        degradation_flags: list[str] = []
        if len(hits) < int(payload.target_count):
            degradation_flags.append("partial_result")
        if ordered_results and len(filtered_results) < len(ordered_results):
            degradation_flags.append("constraint_unsatisfied")
        if not hits:
            if "constraint_unsatisfied" not in degradation_flags:
                degradation_flags.append("constraint_unsatisfied")

        response = AgentSearchResponseV1(
            request_id=uuid.uuid4().hex,
            status=("ok" if not degradation_flags else "partial"),
            degradation_flags=degradation_flags,
            query_trace=self._build_query_trace(task=task, payload=payload, run_payload=run_payload, started=started),
            results=hits,
        )
        logger.info(
            "案例检索能力调用完成",
            extra={
                "task_id": task.id,
                "request_id": response.request_id,
                "intent": payload.intent,
                "status": response.status,
                "degradation_flags": response.degradation_flags,
                "elapsed_ms": response.query_trace.budget_used_ms,
                "result_count": len(response.results),
                "candidates_scanned": response.query_trace.candidates_scanned,
            },
        )
        LegalResearchTaskEventService.record_event(
            task_id=task.id,
            stage="search",
            source="system",
            interface_name="capability_direct_call",
            method="POST",
            status_code=200,
            duration_ms=response.query_trace.budget_used_ms,
            success=True,
            request_summary={
                "intent": payload.intent,
                "target_count": payload.target_count,
                "max_candidates": payload.budget.max_candidates,
                "search_mode": payload.search_mode,
            },
            response_summary={
                "status": response.status,
                "result_count": len(response.results),
                "degradation_flags": response.degradation_flags,
            },
            event_metadata={
                "query_type_metrics": {
                    key: value.model_dump() for key, value in response.query_trace.query_type_metrics.items()
                },
                "candidates_scanned": response.query_trace.candidates_scanned,
                "budget_used_ms": response.query_trace.budget_used_ms,
            },
        )

        if key:
            self._save_idempotent_response(user=user, idempotency_key=key, response=response)
        self._clear_failure_circuit(credential_id=credential.id)
        return response

    def _resolve_credential(self, *, payload: AgentSearchRequestV1, user: Any | None) -> Any:
        if user is None:
            raise PermissionDenied(message="请先登录", code="PERMISSION_DENIED")

        credential_model = _get_account_credential_model()
        credential = (
            credential_model.objects.select_related("lawyer", "lawyer__law_firm")
            .filter(id=payload.credential_id)
            .first()
        )
        if credential is None:
            raise NotFoundError("账号凭证不存在")

        if not user.is_superuser and credential.lawyer.law_firm_id != user.law_firm_id:
            raise PermissionDenied(message="无权限使用该账号凭证", code="PERMISSION_DENIED")

        if not self._task_service._is_weike_credential(credential):
            raise ValidationException("当前仅支持wkxx账号，请选择wkxx凭证")
        return credential

    @staticmethod
    def _build_keyword_and_summary(*, payload: AgentSearchRequestV1) -> tuple[str, str]:
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

    def _execute_with_timeout(self, *, task_id: str, timeout_ms: int) -> dict[str, Any]:
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
        executor = LegalResearchExecutor()
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.THREAD_NAME_PREFIX)
        future = pool.submit(executor.run, task_id=task_id)
        try:
            timeout_seconds = max(1.0, float(timeout_ms) / 1000.0)
            payload = future.result(timeout=timeout_seconds)
            return payload if isinstance(payload, dict) else {}
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _mark_timeout(*, task: LegalResearchTask, timeout_ms: int) -> None:
        task.status = LegalResearchTaskStatus.FAILED
        task.message = f"能力调用超时（{timeout_ms}ms）"
        task.error = f"capability timeout: {timeout_ms}ms"
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])

    @staticmethod
    def _decision_from_metadata(*, metadata: dict[str, Any], score: float) -> str:
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

    @classmethod
    def _serialize_hit(cls, *, item: Any) -> RetrievalHitV1:
        metadata_all = item.metadata if isinstance(item.metadata, dict) else {}
        metadata = (
            metadata_all.get("similarity_structured")
            if isinstance(metadata_all.get("similarity_structured"), dict)
            else {}
        )
        score = float(item.similarity_score or 0.0)
        conflicts_value = metadata.get("key_conflicts")  # type: ignore[union-attr]
        conflicts = [
            str(x).strip() for x in (conflicts_value if isinstance(conflicts_value, list) else []) if str(x).strip()
        ]
        snippets = cls._build_snippets(item=item, metadata=metadata, metadata_all=metadata_all)  # type: ignore[arg-type]
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
            decision=cls._decision_from_metadata(metadata=metadata, score=score),  # type: ignore[arg-type]
            subscores=subscores,
            conflicts=conflicts[:8],
            snippets=snippets,
            why_selected=str(item.match_reason or "")[:300],
            source_url=str(item.source_url or ""),
        )

    @classmethod
    def _build_snippets(
        cls, *, item: Any, metadata: dict[str, Any], metadata_all: dict[str, Any]
    ) -> AgentSearchSnippetsOut:
        snippets_meta = metadata.get("snippets") if isinstance(metadata.get("snippets"), dict) else {}
        extracted = cls._extract_snippets_from_text(cls._extract_content_excerpt(item=item, metadata_all=metadata_all))

        claims = cls._clip_text(snippets_meta.get("claims"), max_chars=cls.SNIPPET_MAX_CHARS) or extracted.get(  # type: ignore[union-attr]
            "claims", ""
        )
        findings = cls._clip_text(snippets_meta.get("findings"), max_chars=cls.SNIPPET_MAX_CHARS) or extracted.get(  # type: ignore[union-attr]
            "findings", ""
        )
        reasoning = (
            cls._clip_text(snippets_meta.get("reasoning"), max_chars=cls.SNIPPET_MAX_CHARS)  # type: ignore[union-attr]
            or extracted.get("reasoning", "")
            or cls._clip_text(getattr(item, "case_digest", ""), max_chars=cls.SNIPPET_MAX_CHARS)
        )
        holdings = cls._clip_text(snippets_meta.get("holdings"), max_chars=cls.SNIPPET_MAX_CHARS) or extracted.get(  # type: ignore[union-attr]
            "holdings", ""
        )
        return AgentSearchSnippetsOut(
            claims=claims,
            findings=findings,
            reasoning=reasoning,
            holdings=holdings,
        )

    @classmethod
    def _extract_content_excerpt(cls, *, item: Any, metadata_all: dict[str, Any]) -> str:
        raw = metadata_all.get("content_excerpt")
        if raw is None:
            raw = metadata_all.get("content_text_excerpt")
        text = str(raw or "").strip()
        if not text:
            text = str(getattr(item, "case_digest", "") or "")
        return cls._normalize_content_text(text)[: cls.SNIPPET_SCAN_MAX_CHARS]

    @classmethod
    def _extract_snippets_from_text(cls, text: str) -> dict[str, str]:
        if not text:
            return {}
        paragraphs = cls._split_snippet_paragraphs(text)
        sections: dict[str, list[str]] = {"claims": [], "findings": [], "reasoning": [], "holdings": []}

        current_label = ""
        for paragraph in paragraphs:
            label = cls._detect_snippet_label(paragraph)
            if label:
                current_label = label
            if not current_label:
                continue
            existing = "\n".join(sections[current_label])
            if len(existing) >= cls.SNIPPET_CAPTURE_MAX_CHARS:
                continue
            sections[current_label].append(paragraph)

        extracted: dict[str, str] = {}
        for label in ("claims", "findings", "reasoning", "holdings"):
            merged = cls._clip_text("\n".join(sections[label]), max_chars=cls.SNIPPET_MAX_CHARS)
            if not merged:
                merged = cls._extract_span_by_marker(text=text, markers=cls.SNIPPET_SECTION_MARKERS[label])
            if merged:
                extracted[label] = merged
        return extracted

    @classmethod
    def _split_snippet_paragraphs(cls, text: str) -> list[str]:
        normalized = cls._normalize_content_text(text)
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

    @classmethod
    def _detect_snippet_label(cls, paragraph: str) -> str:
        for label, markers in cls.SNIPPET_SECTION_MARKERS.items():
            if any(re.search(marker, paragraph) for marker in markers):
                return label
        return ""

    @classmethod
    def _extract_span_by_marker(cls, *, text: str, markers: tuple[str, ...]) -> str:
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

        end = min(len(text), start + cls.SNIPPET_CAPTURE_MAX_CHARS)
        end_candidates: list[int] = []
        for marker_group in cls.SNIPPET_SECTION_MARKERS.values():
            for marker in marker_group:
                match = re.search(marker, text[start + 1 :])
                if match is None:
                    continue
                idx = start + 1 + match.start()
                if idx > start:
                    end_candidates.append(idx)
        if end_candidates:
            end = min(end, min(end_candidates))
        return cls._clip_text(text[start:end], max_chars=cls.SNIPPET_MAX_CHARS)

    @staticmethod
    def _normalize_content_text(text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _clip_text(value: object, *, max_chars: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip()

    @classmethod
    def _apply_intent_profile(
        cls, *, hits: list[RetrievalHitV1], payload: AgentSearchRequestV1
    ) -> list[RetrievalHitV1]:
        if len(hits) <= 1:
            return hits
        intent = str(payload.intent or "similar_case")
        profile = cls.INTENT_PROFILE_WEIGHTS.get(intent, cls.INTENT_PROFILE_WEIGHTS["similar_case"])
        target_court = cls._normalize_text(str(payload.court_scope.court_name or ""))
        signatures = [
            cls._build_result_signature(
                court=hit.court,
                judgment_date=hit.judgment_date,
                title=hit.title,
            )
            for hit in hits
        ]
        signature_counts = Counter(signatures)

        scored: list[tuple[float, float, RetrievalHitV1]] = []
        for hit, signature in zip(hits, signatures, strict=False):
            same_court = bool(target_court and cls._normalize_text(hit.court) == target_court)
            has_reasoning = bool(str(hit.snippets.reasoning or "").strip())
            has_holdings = bool(str(hit.snippets.holdings or "").strip())
            hard_conflict = any(
                any(needle in conflict for needle in cls.HARD_CONFLICT_NEEDLES) for conflict in hit.conflicts
            )

            intent_score = (
                profile["base"] * float(hit.score)
                + profile["facts"] * float(hit.subscores.facts_match)
                + profile["legal"] * float(hit.subscores.legal_relation_match)
                + profile["dispute"] * float(hit.subscores.dispute_match)
                + profile["damage"] * float(hit.subscores.damage_match)
            )
            if same_court:
                intent_score += profile.get("same_court_bonus", 0.0)
            if has_reasoning:
                intent_score += profile.get("reasoning_bonus", 0.0)
            if has_holdings:
                intent_score += profile.get("holdings_bonus", 0.0)
            if hard_conflict:
                intent_score = min(intent_score, 0.62)

            diversity_penalty = min(0.12, 0.04 * max(0, signature_counts[signature] - 1))
            ranked_score = max(0.0, min(1.0, intent_score - diversity_penalty))
            scored.append((ranked_score, float(hit.score), hit))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored]

    @classmethod
    def _build_result_signature(cls, *, court: str, judgment_date: str, title: str) -> str:
        year = cls._extract_year(judgment_date or "")
        normalized_court = cls._normalize_text(court)
        normalized_title = cls._normalize_text(title)[:24]
        return f"{normalized_court}:{year or 0}:{normalized_title}"

    @classmethod
    def _apply_hard_filters(cls, *, results: list[Any], payload: AgentSearchRequestV1) -> list[Any]:
        if not results:
            return []
        filtered = results
        filtered = [item for item in filtered if cls._match_cause_type(item=item, cause_type=payload.cause_type)]
        filtered = [item for item in filtered if cls._match_court_scope(item=item, payload=payload)]
        filtered = [item for item in filtered if cls._match_year_range(item=item, payload=payload)]
        return filtered

    @classmethod
    def _match_cause_type(cls, *, item: Any, cause_type: str) -> bool:
        normalized_cause = cls._normalize_text(cause_type)
        if not normalized_cause:
            return True
        haystack = cls._normalize_text(f"{getattr(item, 'title', '')} {getattr(item, 'case_digest', '')}")
        return normalized_cause in haystack

    @classmethod
    def _match_court_scope(cls, *, item: Any, payload: AgentSearchRequestV1) -> bool:
        mode = str(payload.court_scope.mode or "same_court").strip().lower()
        court_text = str(getattr(item, "court_text", "") or "")
        normalized_item_court = cls._normalize_text(court_text)
        if not normalized_item_court:
            return False

        target_court = str(payload.court_scope.court_name or "").strip()
        normalized_target_court = cls._normalize_text(target_court)
        if mode == "same_court":
            if not normalized_target_court:
                return True
            return normalized_item_court == normalized_target_court

        if mode == "same_level":
            if not normalized_target_court:
                return True
            return cls._extract_court_level(court_text) == cls._extract_court_level(target_court)

        if mode == "region":
            region_keywords = cls._build_region_keywords(
                court_name=target_court,
                region_code=str(payload.court_scope.region_code or ""),
            )
            if not region_keywords:
                return True
            return any(
                cls._normalize_text(keyword) in normalized_item_court
                for keyword in region_keywords
                if str(keyword).strip()
            )

        return True

    @classmethod
    def _match_year_range(cls, *, item: Any, payload: AgentSearchRequestV1) -> bool:
        from_year = payload.year_range.from_year
        to_year = payload.year_range.to
        if from_year is None and to_year is None:
            return True
        year = cls._extract_year(str(getattr(item, "judgment_date", "") or ""))
        if year is None:
            return False
        if from_year is not None and year < int(from_year):
            return False
        if to_year is not None and year > int(to_year):
            return False
        return True

    @classmethod
    def _extract_court_level(cls, text: str) -> str:
        normalized = cls._normalize_text(text)
        for keyword, level in cls.COURT_LEVEL_KEYWORDS:
            if cls._normalize_text(keyword) in normalized:
                return level
        return "unknown"

    @classmethod
    def _build_region_keywords(cls, *, court_name: str, region_code: str) -> list[str]:
        keywords: list[str] = []
        cleaned_name = str(court_name or "").strip()
        if cleaned_name:
            keywords.append(cleaned_name)
        code = re.sub(r"\D+", "", str(region_code or ""))
        if len(code) >= 2:
            province = cls.REGION_CODE_PREFIX.get(code[:2])
            if province:
                keywords.append(province)
        seen: set[str] = set()
        deduped: list[str] = []
        for keyword in keywords:
            marker = cls._normalize_text(keyword)
            if not marker or marker in seen:
                continue
            seen.add(marker)
            deduped.append(keyword)
        return deduped

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "")).lower()

    @staticmethod
    def _extract_year(value: str) -> int | None:
        match = re.search(r"(19|20)\d{2}", str(value or ""))
        if not match:
            return None
        return int(match.group(0))

    @staticmethod
    def _build_query_trace(
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
        query_type_metrics = LegalResearchCapabilityService._build_query_type_metrics(
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

    @staticmethod
    def _build_query_type_metrics(
        *,
        query_trace: dict[str, Any],
        primary_queries: list[str],
        expansion_queries: list[str],
        feedback_queries: list[str],
    ) -> dict[str, AgentSearchQueryTraceOut.QueryTypeMetric]:
        raw_stats = query_trace.get("query_stats")
        query_stats = raw_stats if isinstance(raw_stats, dict) else {}
        primary_set = {LegalResearchCapabilityService._normalize_text(x) for x in primary_queries if x}
        expansion_set = {LegalResearchCapabilityService._normalize_text(x) for x in expansion_queries if x}
        feedback_set = {LegalResearchCapabilityService._normalize_text(x) for x in feedback_queries if x}

        bucket: dict[str, dict[str, int]] = {
            "primary": {"scanned": 0, "matched": 0},
            "expansion": {"scanned": 0, "matched": 0},
            "feedback": {"scanned": 0, "matched": 0},
        }
        for query, metric in query_stats.items():
            query_text = LegalResearchCapabilityService._normalize_text(str(query))
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

    def _payload_hash(self, *, payload: AgentSearchRequestV1, user: Any | None) -> str:
        user_id = getattr(user, "id", None)
        normalized = {
            "user_id": int(user_id) if isinstance(user_id, int) else str(user_id or ""),
            "payload": payload.model_dump(by_alias=True, exclude_none=True),
        }
        serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _cache_key(self, *, kind: str, user: Any | None, idempotency_key: str) -> str:
        user_id = getattr(user, "id", None)
        user_part = str(user_id) if user_id is not None else "anonymous"
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"{self.CACHE_PREFIX}:{kind}:{user_part}:{key_hash}"

    def _failure_circuit_key(self, *, kind: str, credential_id: int) -> str:
        return f"{self.CACHE_PREFIX}:circuit:{kind}:credential:{int(credential_id)}"

    def _is_failure_circuit_open(self, *, credential_id: int) -> bool:
        key = self._failure_circuit_key(kind="open_until", credential_id=credential_id)
        try:
            open_until = float(cache.get(key) or 0.0)
        except Exception:
            open_until = 0.0
        if open_until <= 0:
            return False
        if open_until <= time.time():
            try:
                cache.delete(key)
            except Exception:
                pass
            return False
        return True

    def _mark_failure_circuit(self, *, credential_id: int) -> None:
        count_key = self._failure_circuit_key(kind="failure_count", credential_id=credential_id)
        open_key = self._failure_circuit_key(kind="open_until", credential_id=credential_id)
        try:
            count = int(cache.get(count_key) or 0) + 1
            cache.set(count_key, count, timeout=self.FAILURE_CIRCUIT_COOLDOWN_SECONDS)
            if count >= self.FAILURE_CIRCUIT_THRESHOLD:
                cache.set(
                    open_key,
                    time.time() + self.FAILURE_CIRCUIT_COOLDOWN_SECONDS,
                    timeout=self.FAILURE_CIRCUIT_COOLDOWN_SECONDS,
                )
        except Exception:
            return

    def _clear_failure_circuit(self, *, credential_id: int) -> None:
        count_key = self._failure_circuit_key(kind="failure_count", credential_id=credential_id)
        open_key = self._failure_circuit_key(kind="open_until", credential_id=credential_id)
        try:
            cache.delete_many([count_key, open_key])
        except Exception:
            pass

    def _load_idempotent_response(
        self,
        *,
        user: Any | None,
        idempotency_key: str,
        body_hash: str,
    ) -> AgentSearchResponseV1 | None:
        signature_key = self._cache_key(kind="idempotency_signature", user=user, idempotency_key=idempotency_key)
        response_key = self._cache_key(kind="idempotency_response", user=user, idempotency_key=idempotency_key)
        existing_signature = cache.get(signature_key)
        if existing_signature and str(existing_signature) != body_hash:
            raise ConflictError(
                message="Idempotency-Key 已绑定到其他请求体",
                code="IDEMPOTENCY_CONFLICT",
                errors={"idempotency_key": idempotency_key},
            )
        if not existing_signature:
            cache.set(signature_key, body_hash, timeout=self.IDEMPOTENCY_TTL_SECONDS)
        cached = cache.get(response_key)
        if not cached:
            return None
        if isinstance(cached, AgentSearchResponseV1):
            return cached
        if isinstance(cached, dict):
            return AgentSearchResponseV1.model_validate(cached)
        return None

    def _save_idempotent_response(
        self, *, user: Any | None, idempotency_key: str, response: AgentSearchResponseV1
    ) -> None:
        response_key = self._cache_key(kind="idempotency_response", user=user, idempotency_key=idempotency_key)
        cache.set(response_key, response.model_dump(), timeout=self.IDEMPOTENCY_TTL_SECONDS)
