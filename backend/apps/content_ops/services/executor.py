"""内容运营管道执行器。

流程：检索/直投 → LLM 生成文章 → TTS 合成音频 → 保存结果
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.db import close_old_connections
from django.utils import timezone

from apps.content_ops.models import (
    ContentTask,
    ContentTaskMode,
    ContentTaskStatus,
    GeneratedArticle,
    PodcastEpisode,
    ReviewStatus,
)
from apps.content_ops.services.content_chain import ContentGenerationChain
from apps.content_ops.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class ContentOpsExecutor:
    """内容运营管道执行器。"""

    def run(self, *, task_id: str) -> dict[str, Any]:
        task, early_result = self._acquire_task(task_id)
        if early_result is not None:
            return early_result
        if task is None:
            return {"task_id": task_id, "status": "failed", "error": "任务不存在"}

        try:
            if task.mode == ContentTaskMode.SEARCH:
                self._run_search_mode(task)
            else:
                self._run_direct_mode(task)

            self._run_llm_generation(task)
            self._run_tts_synthesis(task)
            self._mark_completed(task)
            return {"task_id": str(task.pk), "status": "completed"}

        except Exception as e:
            logger.exception("Content ops task failed: %s", task_id)
            self._mark_failed(task, str(e))
            return {"task_id": str(task.pk), "status": "failed", "error": str(e)}

    # -- Task lifecycle --

    @staticmethod
    def _acquire_task(task_id: str) -> tuple[ContentTask | None, dict[str, Any] | None]:
        def _operation() -> tuple[int, ContentTask | None]:
            now = timezone.now()
            updated = ContentTask.objects.filter(
                id=task_id,
                status__in=[ContentTaskStatus.PENDING, ContentTaskStatus.QUEUED],
            ).update(
                status=ContentTaskStatus.RUNNING,
                progress=0,
                error="",
                message="任务已启动",
                started_at=now,
                finished_at=None,
                updated_at=now,
            )
            task = ContentTask.objects.filter(id=task_id).first()
            return int(updated or 0), task

        updated, task = _run_orm_safely(_operation)
        if task is None:
            return None, {"task_id": task_id, "status": "failed", "error": "任务不存在"}
        if updated == 1:
            return task, None
        return None, {"task_id": task_id, "status": task.status}

    @staticmethod
    def _mark_completed(task: ContentTask) -> None:
        task.status = ContentTaskStatus.COMPLETED
        task.progress = 100
        task.message = "任务已完成"
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "progress", "message", "finished_at", "updated_at"])

    @staticmethod
    def _mark_failed(task: ContentTask, error_message: str) -> None:
        task.status = ContentTaskStatus.FAILED
        task.message = "任务执行失败"
        task.error = error_message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])

    @staticmethod
    def _update_progress(task: ContentTask, progress: int, message: str) -> None:
        task.progress = progress
        task.message = message
        task.save(update_fields=["progress", "message", "updated_at"])

    # -- Pipeline phases --

    def _run_search_mode(self, task: ContentTask) -> None:
        """检索模式：通过威科先行搜索裁判文书。"""
        if not task.credential:
            raise RuntimeError("检索模式下凭证不能为空")

        self._update_progress(task, 10, "正在连接威科先行...")

        from apps.legal_research.services.sources import get_case_source_client

        source_client = get_case_source_client("weike")
        session = source_client.open_session(
            username=task.credential.account,
            password=task.credential.password,
            login_url=task.credential.url or None,
        )

        self._update_progress(task, 20, f"正在检索: {task.keyword}")
        items = source_client.search_cases(
            session=session,
            keyword=task.keyword,
            max_candidates=1,
        )
        if not items:
            raise RuntimeError(f"未找到与 '{task.keyword}' 相关的裁判文书")

        item = items[0]
        task.source_doc_id = getattr(item, "doc_id", "") or ""

        self._update_progress(task, 40, "正在获取文书详情...")
        detail = source_client.fetch_case_detail(session=session, item=item)

        task.source_title = getattr(detail, "title", "") or ""
        task.source_court_text = getattr(detail, "court_text", "") or ""
        task.source_judgment_date = getattr(detail, "judgment_date", "") or ""
        task.source_facts = getattr(detail, "facts", "") or ""
        task.save(update_fields=[
            "source_doc_id", "source_title", "source_court_text",
            "source_judgment_date", "source_facts", "updated_at",
        ])

        if not task.source_facts:
            raise RuntimeError("未能从裁判文书中提取案件事实")

    def _run_direct_mode(self, task: ContentTask) -> None:
        """直投模式：直接使用用户提供的内容。"""
        self._update_progress(task, 10, "正在处理直投内容...")
        task.source_facts = task.direct_content
        task.save(update_fields=["source_facts", "updated_at"])

    def _run_llm_generation(self, task: ContentTask) -> None:
        """Phase 3: LLM 生成叙事文章。"""
        self._update_progress(task, 50, "正在生成叙事文章...")

        chain = ContentGenerationChain()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                chain.run(facts=task.source_facts, case_summary=task.case_summary)
            )
        finally:
            loop.close()

        article = GeneratedArticle.objects.create(
            task=task,
            title=result.title,
            content=result.content,
            source_summary=result.summary,
            review_status=ReviewStatus.DRAFT,
            llm_model=result.model,
            token_usage=result.token_usage,
        )
        logger.info("Article created: id=%s, task=%s", article.pk, task.pk)

    def _run_tts_synthesis(self, task: ContentTask) -> None:
        """Phase 4: TTS 合成音频。"""
        self._update_progress(task, 70, "正在合成音频...")

        article = GeneratedArticle.objects.filter(task=task).order_by("-created_at").first()
        if not article:
            raise RuntimeError("未找到生成的文章，无法合成音频")

        tts_service = TTSService()
        audio_bytes = tts_service.synthesize(text=article.content, voice=task.voice)

        episode = PodcastEpisode(
            article=article,
            task=task,
            voice=task.voice,
            file_size_bytes=len(audio_bytes),
        )
        episode.audio_file.save(f"episode_{task.pk}.mp3", _BytesIO(audio_bytes))
        episode.save()

        self._update_progress(task, 90, "音频合成完成")
        logger.info("Episode created: id=%s, task=%s, size=%d", episode.pk, task.pk, len(audio_bytes))


class _BytesIO:
    """Minimal file-like wrapper for bytes, used by FileField.save()."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            result = self._data[self._pos:]
            self._pos = len(self._data)
        else:
            result = self._data[self._pos: self._pos + size]
            self._pos += len(result)
        return result

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = len(self._data) + offset
        return self._pos

    def tell(self) -> int:
        return self._pos


def _run_orm_safely(operation):
    """Run ORM operation safely, even from async context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        from concurrent.futures import ThreadPoolExecutor

        def _wrapped():
            close_old_connections()
            try:
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_wrapped).result()
    return operation()
