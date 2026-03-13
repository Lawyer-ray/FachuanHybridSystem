from __future__ import annotations

import logging

from django.utils import timezone

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.legal_research.models import LegalResearchResult, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.schemas import LegalResearchTaskCreateIn
from apps.legal_research.services.keywords import normalize_keyword_query
from apps.legal_research.services.llm_preflight import verify_siliconflow_connectivity
from apps.organization.models import AccountCredential, Lawyer

logger = logging.getLogger(__name__)


class LegalResearchTaskService:
    _WEIKE_URL_KEYWORD = "wkinfo.com.cn"

    def create_task(self, *, payload: LegalResearchTaskCreateIn, user: Lawyer | None) -> LegalResearchTask:
        credential = AccountCredential.objects.select_related("lawyer", "lawyer__law_firm").filter(id=payload.credential_id).first()
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
            target_count=payload.target_count,
            max_candidates=payload.max_candidates,
            min_similarity_score=payload.min_similarity_score,
            status=LegalResearchTaskStatus.PENDING,
            message="任务已创建，等待调度",
            llm_backend="siliconflow",
            llm_model=(payload.llm_model.strip() if payload.llm_model else LLMConfig.get_default_model()),
        )

        try:
            verify_siliconflow_connectivity(model=task.llm_model)
        except ValidationException as exc:
            task.status = LegalResearchTaskStatus.FAILED
            task.message = "LLM连通性检查失败，请更换模型后重试"
            task.error = str(exc)
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
            logger.warning(
                "案例检索任务创建失败：LLM连通性检查未通过",
                extra={"task_id": str(task.id), "llm_model": task.llm_model, "error": str(exc)},
            )
            return task

        try:
            q_task_id = ServiceLocator.get_task_submission_service().submit(
                "apps.legal_research.tasks.execute_legal_research_task",
                args=[str(task.id)],
                task_name=f"legal_research_{task.id}",
                timeout=3600,
            )
        except Exception as exc:
            task.status = LegalResearchTaskStatus.FAILED
            task.message = "任务提交失败"
            task.error = str(exc)
            task.finished_at = timezone.now()
            task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])
            raise

        task.q_task_id = q_task_id
        task.status = LegalResearchTaskStatus.QUEUED
        task.message = "任务已提交到队列"
        task.save(update_fields=["q_task_id", "status", "message", "updated_at"])

        logger.info(
            "案例检索任务已创建",
            extra={
                "task_id": str(task.id),
                "credential_id": credential.id,
                "created_by": user.id,
            },
        )
        return task

    def get_task(self, *, task_id: int, user: Lawyer | None) -> LegalResearchTask:
        task = (
            LegalResearchTask.objects.select_related("credential", "credential__lawyer", "credential__lawyer__law_firm")
            .filter(id=task_id)
            .first()
        )
        if task is None:
            raise NotFoundError("任务不存在")

        self._check_permission(task=task, user=user)
        return task

    def list_results(self, *, task_id: int, user: Lawyer | None) -> list[LegalResearchResult]:
        task = self.get_task(task_id=task_id, user=user)
        return list(task.results.all().order_by("rank", "created_at"))

    def get_result(self, *, task_id: int, result_id: int, user: Lawyer | None) -> LegalResearchResult:
        task = self.get_task(task_id=task_id, user=user)
        result = task.results.filter(id=result_id).first()
        if result is None:
            raise NotFoundError("检索结果不存在")
        return result

    @staticmethod
    def _check_permission(*, task: LegalResearchTask, user: Lawyer | None) -> None:
        if user is None:
            raise PermissionDenied(message="请先登录", code="PERMISSION_DENIED")

        if user.is_superuser:
            return

        if task.created_by_id == user.id:
            return

        if task.credential.lawyer.law_firm_id == user.law_firm_id:
            return

        raise PermissionDenied(message="无权限访问该任务", code="PERMISSION_DENIED")

    def ensure_task_ready_for_download(self, *, task_id: int, user: Lawyer | None) -> LegalResearchTask:
        task = self.get_task(task_id=task_id, user=user)
        if task.status not in (LegalResearchTaskStatus.COMPLETED, LegalResearchTaskStatus.RUNNING):
            raise ValidationException("任务尚未生成可下载结果")
        return task

    @classmethod
    def _is_weike_credential(cls, credential: AccountCredential) -> bool:
        site_name = (credential.site_name or "").strip().lower()
        url = (credential.url or "").strip().lower()
        return ("wkxx" in site_name) or (site_name == "wk") or ("weike" in site_name) or ("wkinfo" in site_name) or (
            cls._WEIKE_URL_KEYWORD in url
        )
