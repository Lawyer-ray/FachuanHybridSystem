from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.apps import apps as django_apps
from django.utils import timezone

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.legal_research.models import (
    LegalResearchResult,
    LegalResearchSearchMode,
    LegalResearchTask,
    LegalResearchTaskStatus,
)
from apps.legal_research.schemas import LegalResearchTaskCreateIn
from apps.legal_research.services.keywords import normalize_keyword_query
from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity
from apps.legal_research.services.task_state_sync import sync_failed_queue_state

logger = logging.getLogger(__name__)


def _get_account_credential_model() -> Any:
    return django_apps.get_model("organization", "AccountCredential")


class LegalResearchTaskService:
    _WEIKE_URL_KEYWORD = "wkinfo.com.cn"
    PRECHECK_FAILED_MESSAGE = "LLM连通性检查失败，请更换模型后重试"
    QUEUED_MESSAGE = "任务已提交到队列"
    CREATE_PENDING_MESSAGE = "任务已创建，等待调度"
    RETRY_PENDING_MESSAGE = "任务已重置，等待调度"

    def create_task(self, *, payload: LegalResearchTaskCreateIn, user: Any | None) -> LegalResearchTask:
        credential_model = _get_account_credential_model()
        credential = (
            credential_model.objects.select_related("lawyer", "lawyer__law_firm")
            .filter(id=payload.credential_id)
            .first()
        )
        if credential is None:
            raise NotFoundError("账号凭证不存在")

        if user is None:
            raise PermissionDenied(message="请先登录", code="PERMISSION_DENIED")

        if not user.is_superuser and credential.lawyer.law_firm_id != user.law_firm_id:
            raise PermissionDenied(message="无权限使用该账号凭证", code="PERMISSION_DENIED")

        if not self._is_weike_credential(credential):
            raise ValidationException("当前仅支持wkxx账号，请选择wkxx凭证")

        normalized_keyword = normalize_keyword_query(payload.keyword)
        if not normalized_keyword:
            raise ValidationException("请至少输入一个有效检索关键词")

        task = LegalResearchTask.objects.create(
            created_by=user,
            credential=credential,
            keyword=normalized_keyword,
            case_summary=payload.case_summary.strip(),
            search_mode=payload.search_mode or LegalResearchSearchMode.EXPANDED,
            target_count=payload.target_count,
            max_candidates=payload.max_candidates,
            min_similarity_score=payload.min_similarity_score,
            status=LegalResearchTaskStatus.PENDING,
            message=self.CREATE_PENDING_MESSAGE,
            llm_backend="siliconflow",
            llm_model=(payload.llm_model.strip() if payload.llm_model else LLMConfig.get_default_model()),
        )

        queued = self.dispatch_task(task=task, queue_failure_message="任务提交失败", raise_on_submit_error=True)
        if not queued:
            return task

        logger.info(
            "案例检索任务已创建",
            extra={
                "task_id": str(task.id),
                "credential_id": credential.id,
                "created_by": user.id,
            },
        )
        return task

    def reset_task_for_dispatch(
        self,
        *,
        task: LegalResearchTask,
        pending_message: str | None = None,
        clear_results: bool = False,
    ) -> None:
        if clear_results:
            LegalResearchResult.objects.filter(task=task).delete()

        task.status = LegalResearchTaskStatus.PENDING
        task.progress = 0
        task.scanned_count = 0
        task.matched_count = 0
        task.candidate_count = 0
        task.error = ""
        task.message = (pending_message or self.RETRY_PENDING_MESSAGE)[:255]
        task.started_at = None
        task.finished_at = None
        task.q_task_id = ""
        task.source = "weike"
        task.llm_backend = "siliconflow"
        if not task.llm_model:
            task.llm_model = LLMConfig.get_default_model()
        task.save(
            update_fields=[
                "status",
                "progress",
                "scanned_count",
                "matched_count",
                "candidate_count",
                "error",
                "message",
                "started_at",
                "finished_at",
                "q_task_id",
                "source",
                "llm_backend",
                "llm_model",
                "updated_at",
            ]
        )

    def dispatch_task(
        self,
        *,
        task: LegalResearchTask,
        queue_failure_message: str = "任务提交失败",
        raise_on_submit_error: bool = False,
        precheck: Callable[..., None] | None = None,
    ) -> bool:
        checker = precheck or verify_siliconflow_connectivity
        try:
            checker(model=task.llm_model)
        except ValidationException as exc:
            self._mark_precheck_failed(task=task, error_message=str(exc))
            logger.warning(
                "案例检索任务启动失败：LLM连通性检查未通过",
                extra={"task_id": str(task.id), "llm_model": task.llm_model, "error": str(exc)},
            )
            return False

        try:
            q_task_id = ServiceLocator.get_task_submission_service().submit(
                "apps.legal_research.tasks.execute_legal_research_task",
                args=[str(task.id)],
                task_name=f"legal_research_{task.id}",
                timeout=3600,
            )
        except Exception as exc:
            self._mark_submit_failed(task=task, error_message=str(exc), queue_failure_message=queue_failure_message)
            if raise_on_submit_error:
                raise
            return False

        task.q_task_id = q_task_id
        task.status = LegalResearchTaskStatus.QUEUED
        task.message = self.QUEUED_MESSAGE
        task.save(update_fields=["q_task_id", "status", "message", "updated_at"])
        return True

    def get_task(self, *, task_id: int, user: Any | None) -> LegalResearchTask:
        task = (
            LegalResearchTask.objects.select_related("credential", "credential__lawyer", "credential__lawyer__law_firm")
            .filter(id=task_id)
            .first()
        )
        if task is None:
            raise NotFoundError("任务不存在")

        self._check_permission(task=task, user=user)
        sync_failed_queue_state(task=task, failed_message="任务执行失败（队列状态自动回填）")
        return task

    def list_results(self, *, task_id: int, user: Any | None) -> list[LegalResearchResult]:
        task = self.get_task(task_id=task_id, user=user)
        return list(task.results.all().order_by("rank", "created_at"))

    def get_result(self, *, task_id: int, result_id: int, user: Any | None) -> LegalResearchResult:
        task = self.get_task(task_id=task_id, user=user)
        result = task.results.filter(id=result_id).first()
        if result is None:
            raise NotFoundError("检索结果不存在")
        return result

    @staticmethod
    def _check_permission(*, task: LegalResearchTask, user: Any | None) -> None:
        if user is None:
            raise PermissionDenied(message="请先登录", code="PERMISSION_DENIED")

        if user.is_superuser:
            return

        if task.created_by_id == user.id:
            return

        if task.credential.lawyer.law_firm_id == user.law_firm_id:
            return

        raise PermissionDenied(message="无权限访问该任务", code="PERMISSION_DENIED")

    def ensure_task_ready_for_download(self, *, task_id: int, user: Any | None) -> LegalResearchTask:
        task = self.get_task(task_id=task_id, user=user)
        if task.status not in (LegalResearchTaskStatus.COMPLETED, LegalResearchTaskStatus.RUNNING):
            raise ValidationException("任务尚未生成可下载结果")
        return task

    @classmethod
    def _is_weike_credential(cls, credential: Any) -> bool:
        site_name = (credential.site_name or "").strip().lower()
        url = (credential.url or "").strip().lower()
        return (
            ("wkxx" in site_name)
            or (site_name == "wk")
            or ("weike" in site_name)
            or ("wkinfo" in site_name)
            or (cls._WEIKE_URL_KEYWORD in url)
        )

    def _mark_precheck_failed(self, *, task: LegalResearchTask, error_message: str) -> None:
        task.status = LegalResearchTaskStatus.FAILED
        task.message = self.PRECHECK_FAILED_MESSAGE
        task.error = error_message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])

    @staticmethod
    def _mark_submit_failed(
        *,
        task: LegalResearchTask,
        error_message: str,
        queue_failure_message: str,
    ) -> None:
        task.status = LegalResearchTaskStatus.FAILED
        task.message = queue_failure_message[:255] or "任务提交失败"
        task.error = error_message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
