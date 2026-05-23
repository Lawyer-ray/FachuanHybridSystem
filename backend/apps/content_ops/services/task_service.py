"""任务服务 — ContentTask 的 CRUD、审核、队列提交。"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.content_ops.models import (
    ContentTask,
    ContentTaskMode,
    ContentTaskStatus,
    GeneratedArticle,
    PodcastEpisode,
    ReviewStatus,
)
from apps.core.exceptions.common import NotFoundError, PermissionDenied, ValidationException
from apps.core.tasking.convenience import submit_task

logger = logging.getLogger(__name__)

_QUEUED_MESSAGE = "任务已提交队列，等待执行"
_CREATE_PENDING_MESSAGE = "任务已创建，等待提交"


class ContentOpsTaskService:
    """ContentTask 的业务操作。"""

    def create_task(self, *, payload: Any, user: Any | None = None) -> ContentTask:
        """创建内容运营任务并提交队列。"""
        mode = getattr(payload, "mode", ContentTaskMode.SEARCH)

        if mode == ContentTaskMode.SEARCH:
            if not getattr(payload, "keyword", None):
                raise ValidationException("检索模式下 keyword 不能为空")
            if not getattr(payload, "credential_id", None):
                raise ValidationException("检索模式下 credential_id 不能为空")
        elif mode == ContentTaskMode.DIRECT:
            if not getattr(payload, "direct_content", None):
                raise ValidationException("直投模式下 direct_content 不能为空")

        with transaction.atomic():
            task = ContentTask(
                created_by=user if user and user.is_authenticated else None,
                mode=mode,
                keyword=getattr(payload, "keyword", "") or "",
                case_summary=getattr(payload, "case_summary", "") or "",
                direct_content=getattr(payload, "direct_content", "") or "",
                voice=getattr(payload, "voice", "冰糖") or "冰糖",
                tts_style_prompt=getattr(payload, "tts_style_prompt", "") or "",
                status=ContentTaskStatus.PENDING,
                message=_CREATE_PENDING_MESSAGE,
            )
            if mode == ContentTaskMode.SEARCH and getattr(payload, "credential_id", None):
                from apps.organization.models import AccountCredential

                cred = AccountCredential.objects.filter(
                    id=payload.credential_id,
                    lawyer=user,
                ).first()
                if not cred:
                    raise ValidationException("凭证不存在或无权限")
                task.credential = cred
            task.save()

        self.dispatch_task(task=task)
        return task

    def dispatch_task(self, *, task: ContentTask) -> bool:
        """将任务提交到 Django Q 队列。"""
        try:
            q_task_id = submit_task(
                "apps.content_ops.tasks.execute_content_ops_task",
                str(task.pk),
                task_name=f"content_ops_{task.pk}",
            )
            task.q_task_id = q_task_id
            task.status = ContentTaskStatus.QUEUED
            task.message = _QUEUED_MESSAGE
            task.save(update_fields=["q_task_id", "status", "message", "updated_at"])
            return True
        except Exception as e:
            logger.exception("Failed to dispatch content_ops task %s", task.pk)
            task.status = ContentTaskStatus.FAILED
            task.message = "任务提交失败"
            task.error = str(e)
            task.save(update_fields=["status", "message", "error", "updated_at"])
            return False

    def get_task(self, *, task_id: int, user: Any | None = None) -> ContentTask:
        """获取任务详情（含权限检查）。"""
        task = (
            ContentTask.objects.select_related("created_by", "credential")
            .filter(id=task_id)
            .first()
        )
        if not task:
            raise NotFoundError(f"任务 {task_id} 不存在")
        self._check_permission(task, user)
        return task

    def list_tasks(self, *, user: Any | None = None, mode: str | None = None) -> list[ContentTask]:
        """列出当前用户的任务。"""
        qs = ContentTask.objects.select_related("created_by")
        if user and user.is_authenticated:
            qs = qs.filter(created_by=user)
        if mode:
            qs = qs.filter(mode=mode)
        return list(qs[:50])

    def list_articles(self, *, task_id: int, user: Any | None = None) -> list[GeneratedArticle]:
        """列出任务关联的文章。"""
        task = self.get_task(task_id=task_id, user=user)
        return list(GeneratedArticle.objects.filter(task=task).order_by("-created_at"))

    def list_episodes(self, *, task_id: int, user: Any | None = None) -> list[PodcastEpisode]:
        """列出任务关联的播客单集。"""
        task = self.get_task(task_id=task_id, user=user)
        return list(PodcastEpisode.objects.filter(task=task).order_by("-created_at"))

    def approve_article(self, *, article_id: int, user: Any | None = None, notes: str = "") -> GeneratedArticle:
        """审核通过文章。"""
        article = self._get_article(article_id)
        article.review_status = ReviewStatus.APPROVED
        article.reviewer_notes = notes
        article.reviewed_by = user if user and user.is_authenticated else None
        article.reviewed_at = timezone.now()
        article.save(update_fields=["review_status", "reviewer_notes", "reviewed_by", "reviewed_at", "updated_at"])
        return article

    def reject_article(self, *, article_id: int, user: Any | None = None, notes: str = "") -> GeneratedArticle:
        """驳回文章。"""
        article = self._get_article(article_id)
        article.review_status = ReviewStatus.REJECTED
        article.reviewer_notes = notes
        article.reviewed_by = user if user and user.is_authenticated else None
        article.reviewed_at = timezone.now()
        article.save(update_fields=["review_status", "reviewer_notes", "reviewed_by", "reviewed_at", "updated_at"])
        return article

    def approve_episode(self, *, episode_id: int, user: Any | None = None, notes: str = "") -> PodcastEpisode:
        """审核通过播客单集。"""
        episode = self._get_episode(episode_id)
        episode.review_status = ReviewStatus.APPROVED
        episode.reviewer_notes = notes
        episode.reviewed_by = user if user and user.is_authenticated else None
        episode.reviewed_at = timezone.now()
        episode.save(update_fields=["review_status", "reviewer_notes", "reviewed_by", "reviewed_at", "updated_at"])
        return episode

    def reject_episode(self, *, episode_id: int, user: Any | None = None, notes: str = "") -> PodcastEpisode:
        """驳回播客单集。"""
        episode = self._get_episode(episode_id)
        episode.review_status = ReviewStatus.REJECTED
        episode.reviewer_notes = notes
        episode.reviewed_by = user if user and user.is_authenticated else None
        episode.reviewed_at = timezone.now()
        episode.save(update_fields=["review_status", "reviewer_notes", "reviewed_by", "reviewed_at", "updated_at"])
        return episode

    @staticmethod
    def _get_article(article_id: int) -> GeneratedArticle:
        article = GeneratedArticle.objects.filter(id=article_id).first()
        if not article:
            raise NotFoundError(f"文章 {article_id} 不存在")
        return article

    @staticmethod
    def _get_episode(episode_id: int) -> PodcastEpisode:
        episode = PodcastEpisode.objects.filter(id=episode_id).first()
        if not episode:
            raise NotFoundError(f"播客单集 {episode_id} 不存在")
        return episode

    @staticmethod
    def _check_permission(task: ContentTask, user: Any | None) -> None:
        if user and user.is_authenticated and task.created_by_id and task.created_by_id != user.id:
            raise PermissionDenied("无权访问此任务")
