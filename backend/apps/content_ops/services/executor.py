"""内容运营管道执行器。

流程：检索/直投 → LLM 生成文章/讨论稿 → TTS 合成音频 → 保存结果
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from io import BytesIO
from typing import Any

from django.db import close_old_connections
from django.utils import timezone

from apps.content_ops.models import (
    ContentTask,
    ContentTaskMode,
    ContentTaskOutputMode,
    ContentTaskStatus,
    DiscussionScript,
    DiscussionTurn,
    EpisodeContentSource,
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

            self._check_cancelled(task)

            output_mode = task.output_mode or ContentTaskOutputMode.NARRATION

            # Phase 2: Content generation
            if output_mode in (ContentTaskOutputMode.NARRATION, ContentTaskOutputMode.BOTH):
                self._run_llm_generation(task)
            if output_mode in (ContentTaskOutputMode.DISCUSSION, ContentTaskOutputMode.BOTH):
                self._run_discussion_generation(task)

            self._check_cancelled(task)

            # Phase 3: TTS synthesis
            if output_mode in (ContentTaskOutputMode.NARRATION, ContentTaskOutputMode.BOTH):
                self._run_tts_synthesis(task)
            if output_mode in (ContentTaskOutputMode.DISCUSSION, ContentTaskOutputMode.BOTH):
                self._run_discussion_tts(task)

            self._check_cancelled(task)
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
    def _check_cancelled(task: ContentTask) -> None:
        """Check if task was cancelled, raise if so."""
        task.refresh_from_db(fields=["status"])
        if task.status == ContentTaskStatus.CANCELLED:
            raise RuntimeError("任务已被取消")

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
        """检索模式：通过威科先行搜索裁判文书，并智能筛选最有传播价值的案例。"""
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
            max_candidates=5,
        )
        if not items:
            raise RuntimeError(f"未找到与 '{task.keyword}' 相关的裁判文书")

        # 智能筛选：使用LLM选择最有传播价值的案例
        if len(items) > 1:
            self._update_progress(task, 30, "正在智能筛选最有价值的案例...")
            selected_item = self._select_best_case(items, task.keyword)
        else:
            selected_item = items[0]

        task.source_doc_id = getattr(selected_item, "doc_id", "") or ""

        self._update_progress(task, 40, "正在获取文书详情...")
        self._check_cancelled(task)
        detail = source_client.fetch_case_detail(session=session, item=selected_item)

        task.source_title = getattr(detail, "title", "") or ""
        task.source_court_text = getattr(detail, "court_text", "") or ""
        task.source_judgment_date = getattr(detail, "judgment_date", "") or ""
        task.source_facts = getattr(detail, "content_text", "") or ""
        task.save(
            update_fields=[
                "source_doc_id",
                "source_title",
                "source_court_text",
                "source_judgment_date",
                "source_facts",
                "updated_at",
            ]
        )

        if not task.source_facts:
            raise RuntimeError("未能从裁判文书中提取案件事实")

    def _select_best_case(self, items: list[Any], keyword: str) -> Any:
        """使用LLM从多个案例中选择最有传播价值的一个。"""
        from apps.core.interfaces import ServiceLocator
        from apps.core.llm.config import LLMConfig
        from apps.core.llm.structured_output import clean_text, parse_json_content

        # 构建案例摘要列表
        case_summaries = []
        for i, item in enumerate(items):
            title = getattr(item, "title", "") or f"案例{i + 1}"
            court = getattr(item, "court", "") or "未知法院"
            case_summaries.append(f"[{i}] {title} - {court}")

        cases_text = "\n".join(case_summaries)

        system_prompt = """你是一位资深的法律内容运营专家。请从以下案例中选择最有传播价值的1个。

评估标准：
1. 故事性：是否有引人入胜的情节，适合写成故事
2. 争议性：是否涉及常见纠纷，能引起读者共鸣
3. 教育性：是否能给读者带来实用的法律知识
4. 时效性：是否与当前社会热点相关

请严格按照JSON格式输出：{"selected_index": 0, "reason": "选择理由"}"""

        user_msg = f"检索关键词：{keyword}\n\n找到的案例：\n{cases_text}\n\n请选择最有传播价值的1个案例。"

        try:
            from apps.content_ops.constants import CONTENT_LLM_MODEL

            llm_service = ServiceLocator.get_llm_service()
            model_name = CONTENT_LLM_MODEL
            backend = LLMConfig.resolve_backend_for_model(model_name)

            response = llm_service.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                model=model_name,
                backend=backend,
                temperature=0.3,
            )

            content = clean_text(response.content)
            parsed = parse_json_content(content)

            if isinstance(parsed, dict) and "selected_index" in parsed:
                index = int(parsed["selected_index"])
                if 0 <= index < len(items):
                    reason = parsed.get("reason", "")
                    logger.info("LLM selected case %d: %s", index, reason)
                    return items[index]

        except (TypeError, ValueError) as e:
            logger.warning("Failed to select best case via LLM: %s, using first result", e)

        return items[0]

    def _run_direct_mode(self, task: ContentTask) -> None:
        """直投模式：直接使用用户提供的内容。"""
        self._update_progress(task, 10, "正在处理直投内容...")
        task.source_facts = task.direct_content
        task.save(update_fields=["source_facts", "updated_at"])

    def _run_llm_generation(self, task: ContentTask) -> None:
        """Phase 3: LLM 生成叙事文章。"""
        self._update_progress(task, 50, "正在生成叙事文章...")

        chain = ContentGenerationChain()
        result = chain.run(facts=task.source_facts, case_summary=task.case_summary)

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
        audio_bytes = tts_service.synthesize(
            text=article.content,
            voice=task.voice,
            style_prompt=task.tts_style_prompt or None,
        )

        episode = PodcastEpisode(
            article=article,
            task=task,
            voice=task.voice,
            file_size_bytes=len(audio_bytes),
        )
        episode.audio_file.save(f"episode_{task.pk}.mp3", BytesIO(audio_bytes))  # type: ignore[arg-type]
        episode.save()

        self._update_progress(task, 90, "音频合成完成")
        logger.info("Episode created: id=%s, task=%s, size=%d", episode.pk, task.pk, len(audio_bytes))

    def _run_discussion_generation(self, task: ContentTask) -> None:
        """LLM 生成多人讨论脚本。"""
        self._update_progress(task, 50, "正在生成讨论脚本...")

        speakers = task.discussion_speakers or []
        if not speakers:
            from apps.content_ops.constants import DEFAULT_DISCUSSION_SPEAKERS

            speakers = DEFAULT_DISCUSSION_SPEAKERS

        from apps.content_ops.services.discussion_chain import DiscussionGenerationChain

        chain = DiscussionGenerationChain()
        result = chain.run(
            facts=task.source_facts,
            speakers=speakers,
            case_summary=task.case_summary,
        )

        script = DiscussionScript.objects.create(
            task=task,
            title=result.title,
            topic=result.topic,
            review_status=ReviewStatus.DRAFT,
            llm_model=result.model,
            token_usage=result.token_usage,
        )

        # 创建 speaker -> style_prompt 映射
        style_map = {s["name"]: s.get("style_prompt", "") for s in speakers}

        for i, turn in enumerate(result.turns):
            DiscussionTurn.objects.create(
                script=script,
                speaker_name=turn["speaker"],
                speaker_style_prompt=style_map.get(turn["speaker"], ""),
                text=turn["text"],
                order=i,
            )

        logger.info("Discussion script created: id=%s, task=%s, turns=%d", script.pk, task.pk, len(result.turns))

    def _run_discussion_tts(self, task: ContentTask) -> None:
        """多声音 TTS 合成讨论音频。"""
        self._update_progress(task, 70, "正在合成多人对话音频...")

        script = DiscussionScript.objects.filter(task=task).order_by("-created_at").first()
        if not script:
            raise RuntimeError("未找到讨论脚本，无法合成音频")

        turns = list(script.turns.order_by("order"))
        if not turns:
            raise RuntimeError("讨论脚本没有对话轮次")

        turn_dicts = [
            {"text": t.text, "style_prompt": t.speaker_style_prompt, "speaker": t.speaker_name} for t in turns
        ]

        tts_service = TTSService()
        audio_bytes = tts_service.synthesize_discussion(turns=turn_dicts)

        episode = PodcastEpisode(
            task=task,
            discussion_script=script,
            content_source=EpisodeContentSource.DISCUSSION,
            voice="multi",
            file_size_bytes=len(audio_bytes),
        )
        episode.audio_file.save(f"discussion_{task.pk}.mp3", BytesIO(audio_bytes))  # type: ignore[arg-type]
        episode.save()

        self._update_progress(task, 90, "多人对话音频合成完成")
        logger.info("Discussion episode created: id=%s, task=%s, size=%d", episode.pk, task.pk, len(audio_bytes))


def _run_orm_safely[T](operation: Callable[[], T]) -> T:
    """Run ORM operation safely, even from async context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        from concurrent.futures import ThreadPoolExecutor

        def _wrapped() -> T:
            close_old_connections()
            try:
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_wrapped).result()
    return operation()
