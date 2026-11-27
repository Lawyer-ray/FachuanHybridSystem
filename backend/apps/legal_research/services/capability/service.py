"""案例检索能力（capability v1）：执行链、凭证校验、幂等缓存与失败熔断。

本模块只保留**有状态 / 有 IO** 的那部分：建任务、限流与超时执行、凭证校验、
Idempotency-Key 缓存、失败熔断。三块纯函数域已各自独立成兄弟模块，本模块按原
路径 re-export 它们的全部符号，``service.X`` 的历史 import 与测试仍照旧可用：

- ``snippets``      —— 命中 → 结构化片段（``_serialize_hit`` / ``_build_snippets``）；
- ``ranking``       —— 硬过滤与意图画像排序（``_apply_hard_filters`` /
  ``_apply_intent_profile`` / ``_normalize_text`` 等）；
- ``trace_metrics`` —— 关键词、查询轨迹与 decision 折算（``_build_keyword_and_summary`` /
  ``_build_query_trace`` / ``_build_query_type_metrics`` / ``_decision_from_metadata``）。

依赖方向单向：本模块 → 上述三个模块，三个模块都不反向 import 本模块。
``_payload_hash`` / ``_cache_key`` / ``_failure_circuit_*`` / ``_load|_save_idempotent_response``
留在类上：它们读写 ``cache``、持有 ``CACHE_PREFIX`` 等类常量，且测试会把
``LegalResearchCapabilityService._is_failure_circuit_open`` 换成桩函数
（见 tests/ci/unit/test_legal_research_capability_service.py）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
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
from apps.legal_research.schemas.legal_research_schemas import AgentSearchRequestV1, AgentSearchResponseV1
from apps.legal_research.services.task.event_service import LegalResearchTaskEventService
from apps.legal_research.services.task.executor import LegalResearchExecutor
from apps.legal_research.services.task.service import LegalResearchTaskService

# 解耦（2026-11-29）：snippets / ranking / trace_metrics 三块纯函数（原为类上的
# @classmethod 与模块级函数）已下沉到兄弟模块，此处按原路径 re-export。
from .ranking import (
    COURT_LEVEL_KEYWORDS,
    HARD_CONFLICT_NEEDLES,
    INTENT_PROFILE_WEIGHTS,
    REGION_CODE_PREFIX,
    _apply_hard_filters,
    _apply_intent_profile,
    _build_region_keywords,
    _build_result_signature,
    _extract_court_level,
    _extract_year,
    _match_cause_type,
    _match_court_scope,
    _match_year_range,
    _normalize_text,
)
from .snippets import (
    SNIPPET_CAPTURE_MAX_CHARS,
    SNIPPET_MAX_CHARS,
    SNIPPET_SCAN_MAX_CHARS,
    SNIPPET_SECTION_MARKERS,
    _build_snippets,
    _clip_text,
    _detect_snippet_label,
    _extract_content_excerpt,
    _extract_snippets_from_text,
    _extract_span_by_marker,
    _normalize_content_text,
    _serialize_hit,
    _split_snippet_paragraphs,
)
from .trace_metrics import (
    _build_keyword_and_summary,
    _build_query_trace,
    _build_query_type_metrics,
    _decision_from_metadata,
)

logger = logging.getLogger(__name__)


def _get_account_credential_model() -> Any:  # pragma: no cover
    return django_apps.get_model("organization", "AccountCredential")


class LegalResearchCapabilityService:  # pragma: no cover
    IDEMPOTENCY_TTL_SECONDS = 1800
    CACHE_PREFIX = "legal_research:capability:v1"
    THREAD_NAME_PREFIX = "legal-research-capability"
    MAX_DIRECT_CONCURRENCY = 3
    DIRECT_CONCURRENCY_WAIT_SECONDS = 2.0
    _DIRECT_SEMAPHORE = threading.BoundedSemaphore(MAX_DIRECT_CONCURRENCY)
    FAILURE_CIRCUIT_THRESHOLD = 3
    FAILURE_CIRCUIT_COOLDOWN_SECONDS = 180

    def __init__(self) -> None:  # pragma: no cover
        self._task_service = LegalResearchTaskService()

    def search(  # pragma: no cover
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
        keyword, case_summary = _build_keyword_and_summary(payload=payload)
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
            # 调用方未指定时沿用 0.9；长案情段落建议显式降阈值（实测同一批候选
            # 0.9 时 0 命中、0.5 时命中 0.55–0.96，见 docs/harness/backend/integrations.md）。
            min_similarity_score=(
                float(payload.min_similarity_score) if payload.min_similarity_score is not None else 0.9
            ),
            status=LegalResearchTaskStatus.PENDING,
            message="能力调用执行中",
            llm_backend=LLMConfig.get_default_backend(),
            llm_model=LLMConfig.get_openai_compatible_model(),
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
            _mark_timeout(task=task, timeout_ms=timeout_ms)
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
        filtered_results = _apply_hard_filters(results=ordered_results, payload=payload)
        hits = [_serialize_hit(item=result) for result in filtered_results]
        hits = _apply_intent_profile(hits=hits, payload=payload)
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
            query_trace=_build_query_trace(task=task, payload=payload, run_payload=run_payload, started=started),
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

    def _resolve_credential(self, *, payload: AgentSearchRequestV1, user: Any | None) -> Any:  # pragma: no cover
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

    def _execute_with_timeout(self, *, task_id: str, timeout_ms: int) -> dict[str, Any]:  # pragma: no cover
        # 与 legal_research/tasks.execute_legal_research_task 跑的是同一个
        # LegalResearchExecutor.run：同步 Playwright 使执行器线程带运行中循环，
        # 执行器全部 ORM 段已统一经 _run_orm_safely 摆渡（见 tasks.py 注释），
        # 无需 allow_async_unsafe 放行。
        executor = LegalResearchExecutor()
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.THREAD_NAME_PREFIX)
        future = pool.submit(executor.run, task_id=task_id)
        try:
            timeout_seconds = max(1.0, float(timeout_ms) / 1000.0)
            payload = future.result(timeout=timeout_seconds)
            return payload if isinstance(payload, dict) else {}
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _payload_hash(self, *, payload: AgentSearchRequestV1, user: Any | None) -> str:  # pragma: no cover
        user_id = getattr(user, "id", None)
        normalized = {
            "user_id": int(user_id) if isinstance(user_id, int) else str(user_id or ""),
            "payload": payload.model_dump(by_alias=True, exclude_none=True),
        }
        serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _cache_key(self, *, kind: str, user: Any | None, idempotency_key: str) -> str:  # pragma: no cover
        user_id = getattr(user, "id", None)
        user_part = str(user_id) if user_id is not None else "anonymous"
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"{self.CACHE_PREFIX}:{kind}:{user_part}:{key_hash}"

    def _failure_circuit_key(self, *, kind: str, credential_id: int) -> str:  # pragma: no cover
        return f"{self.CACHE_PREFIX}:circuit:{kind}:credential:{int(credential_id)}"

    def _is_failure_circuit_open(self, *, credential_id: int) -> bool:  # pragma: no cover
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
                logger.debug("删除失败熔断缓存键失败（已忽略）", exc_info=True)
                pass
            return False
        return True

    def _mark_failure_circuit(self, *, credential_id: int) -> None:  # pragma: no cover
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
            logger.warning("记录失败熔断计数失败（已忽略）", exc_info=True)
            return

    def _clear_failure_circuit(self, *, credential_id: int) -> None:  # pragma: no cover
        count_key = self._failure_circuit_key(kind="failure_count", credential_id=credential_id)
        open_key = self._failure_circuit_key(kind="open_until", credential_id=credential_id)
        try:
            cache.delete_many([count_key, open_key])
        except (TypeError, ValueError):
            logger.debug("清除失败熔断缓存失败（已忽略）", exc_info=True)
            pass

    def _load_idempotent_response(  # pragma: no cover
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

    def _save_idempotent_response(  # pragma: no cover
        self, *, user: Any | None, idempotency_key: str, response: AgentSearchResponseV1
    ) -> None:
        response_key = self._cache_key(kind="idempotency_response", user=user, idempotency_key=idempotency_key)
        cache.set(response_key, response.model_dump(), timeout=self.IDEMPOTENCY_TTL_SECONDS)


# ↓↓ 由 LegalResearchCapabilityService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _mark_timeout(*, task: LegalResearchTask, timeout_ms: int) -> None:  # pragma: no cover
    task.status = LegalResearchTaskStatus.FAILED
    task.message = f"能力调用超时（{timeout_ms}ms）"
    task.error = f"capability timeout: {timeout_ms}ms"
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
