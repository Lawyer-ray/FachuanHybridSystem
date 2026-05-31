from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import Any

from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseBase
from ninja import Router

from apps.content_ops.schemas.content_ops_schemas import (
    ArticleUpdateIn,
    BatchReviewIn,
    ContentTaskCreateIn,
    ContentTaskOut,
    DiscussionScriptOut,
    DiscussionTurnOut,
    DiscussionTurnUpdateIn,
    GeneratedArticleOut,
    HotTopicOut,
    HotTopicRefreshIn,
    PodcastEpisodeOut,
    ReviewActionIn,
    TopicInspirationIn,
    TopicSuggestIn,
    TopicSuggestionOut,
    TTSTestIn,
)
from apps.content_ops.services.task_service import ContentOpsTaskService
from apps.content_ops.services.tts_service import TTS_VOICES, TTSService
from apps.core.security.auth import JWTOrSessionAuth

logger = logging.getLogger("apps.content_ops.api")

router = Router(tags=["内容运营"], auth=JWTOrSessionAuth())

_task_service = ContentOpsTaskService()

# --- TTS 测试 ---

@router.post("/tts/test")
def tts_test(request: HttpRequest, payload: TTSTestIn) -> dict[str, str] | FileResponse | HttpResponse:
    """Test TTS synthesis. Returns an MP3/WAV audio file for preview."""
    if not payload.text.strip():
        return {"error": "text 不能为空"}
    if len(payload.text) > 2000:
        return {"error": "text 不能超过 2000 字"}
    # VoiceDesign mode skips voice validation
    if not payload.style_prompt and payload.voice not in TTS_VOICES:
        return {"error": f"不支持的音色: {payload.voice}，可选: {', '.join(TTS_VOICES.keys())}"}

    try:
        service = TTSService()
        audio_bytes = service.synthesize(
            text=payload.text,
            voice=payload.voice,
            audio_format=payload.audio_format,
            style_prompt=payload.style_prompt or None,
        )
    except Exception as e:
        logger.error("TTS test failed: %s", e)
        return {"error": str(e)}

    content_type = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "pcm": "audio/pcm",
        "pcm16": "audio/pcm",
    }.get(payload.audio_format, "audio/mpeg")

    suffix = f".{payload.audio_format}"
    response = HttpResponse(audio_bytes, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="tts_test{suffix}"'
    return response

# --- 选题建议 ---

@router.post("/topics/suggest", response=list[TopicSuggestionOut])
def topic_suggest(request: HttpRequest, payload: TopicSuggestIn) -> list[dict[str, str]]:
    """获取选题建议（纯 LLM 推荐）。"""
    from apps.content_ops.services.topic_service import TopicService

    try:
        result = TopicService().suggest(model=payload.model or None)
        return result.topics
    except Exception as e:
        logger.error("Topic suggestion failed: %s", e)
        return []

@router.get("/topics/hot", response=list[HotTopicOut])
def get_hot_topics(request: HttpRequest, source: str | None = None) -> list[dict[str, Any]]:
    """获取热点话题列表（从缓存读取，30 分钟刷新一次）。"""
    from apps.content_ops.services.hot_topic_service import HotTopicService

    try:
        items = HotTopicService().get_hot_topics(source=source or None)
        return [
            {
                "rank": item.rank,
                "title": item.title,
                "heat": item.heat,
                "url": item.url,
                "source": item.source,
            }
            for item in items
        ]
    except Exception as e:
        logger.error("Get hot topics failed: %s", e)
        return []

@router.post("/topics/hot/refresh", response=list[HotTopicOut])
def refresh_hot_topics(request: HttpRequest, payload: HotTopicRefreshIn) -> list[dict[str, Any]]:
    """强制刷新热点话题（绕过缓存）。"""
    from apps.content_ops.services.hot_topic_service import HotTopicService

    try:
        items = HotTopicService().refresh(source=payload.source or None)
        return [
            {
                "rank": item.rank,
                "title": item.title,
                "heat": item.heat,
                "url": item.url,
                "source": item.source,
            }
            for item in items
        ]
    except Exception as e:
        logger.error("Refresh hot topics failed: %s", e)
        return []

@router.post("/topics/inspiration", response=list[TopicSuggestionOut])
def topic_inspiration(request: HttpRequest, payload: TopicInspirationIn) -> list[dict[str, str]]:
    """基于热点话题的 AI 选题灵感。"""
    from apps.content_ops.services.hot_topic_service import HotTopicService
    from apps.content_ops.services.topic_service import TopicService

    try:
        hot_topics = HotTopicService().get_hot_topics()
        if not hot_topics:
            return []
        result = TopicService().suggest_from_trends(hot_topics=hot_topics, model=payload.model or None)
        return result.topics
    except Exception as e:
        logger.error("Topic inspiration failed: %s", e)
        return []

# --- 翻译 ---

@router.post("/topics/translate")
def translate_topics(request: HttpRequest) -> dict[str, Any]:
    """批量翻译热点话题标题。"""
    from apps.core.llm.service import LLMService

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {"translations": []}

    titles = body.get("titles", [])
    if not titles:
        return {"translations": []}

    # 构建批量翻译 prompt
    titles_text = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    prompt = f"""请将以下英文标题翻译成中文，保持简洁准确。
每行一个翻译结果，只返回翻译后的标题，不要添加序号或其他内容。

{titles_text}"""

    try:
        llm = LLMService()
        messages = [
            {"role": "system", "content": "你是一个专业的翻译助手，擅长法律科技领域的翻译。"},
            {"role": "user", "content": prompt},
        ]
        response = llm.chat(messages=messages, backend="openai_compatible")
        result = response.content if hasattr(response, "content") else str(response)
        translations = [line.strip() for line in result.strip().split("\n") if line.strip()]
        # 确保翻译数量匹配
        if len(translations) < len(titles):
            translations.extend(titles[len(translations) :])
        return {"translations": translations[: len(titles)]}
    except Exception as e:
        logger.error("Translation failed: %s", e)
        return {"translations": titles}  # 失败时返回原文

# --- 任务管理 ---

@router.post("/tasks", response=ContentTaskOut)
def create_task(request: HttpRequest, payload: ContentTaskCreateIn) -> ContentTaskOut:
    """创建内容运营任务。"""
    task = _task_service.create_task(payload=payload, user=request.user)
    return _task_to_out(task)

@router.get("/tasks", response=list[ContentTaskOut])
def list_tasks(request: HttpRequest, mode: str | None = None) -> list[ContentTaskOut]:
    """列出当前用户的任务。"""
    tasks = _task_service.list_tasks(user=request.user, mode=mode)
    return [_task_to_out(t) for t in tasks]

@router.get("/tasks/{task_id}", response=ContentTaskOut)
def get_task(request: HttpRequest, task_id: int) -> ContentTaskOut:
    """获取任务详情。"""
    task = _task_service.get_task(task_id=task_id, user=request.user)
    return _task_to_out(task)

@router.post("/tasks/{task_id}/retry", response=ContentTaskOut)
def retry_task(request: HttpRequest, task_id: int) -> ContentTaskOut:
    """重试失败的任务。"""
    task = _task_service.retry_task(task_id=task_id, user=request.user)
    return _task_to_out(task)

@router.post("/tasks/{task_id}/cancel", response=ContentTaskOut)
def cancel_task(request: HttpRequest, task_id: int) -> ContentTaskOut:
    """取消运行中的任务。"""
    task = _task_service.cancel_task(task_id=task_id, user=request.user)
    return _task_to_out(task)

@router.delete("/tasks/{task_id}")
def delete_task(request: HttpRequest, task_id: int) -> dict[str, str]:
    """删除任务。"""
    _task_service.delete_task(task_id=task_id, user=request.user)
    return {"message": "任务已删除"}

@router.get("/tasks/{task_id}/articles", response=list[GeneratedArticleOut])
def list_articles(request: HttpRequest, task_id: int) -> list[GeneratedArticleOut]:
    """列出任务关联的文章。"""
    articles = _task_service.list_articles(task_id=task_id, user=request.user)
    return [_article_to_out(a) for a in articles]

@router.get("/tasks/{task_id}/episodes", response=list[PodcastEpisodeOut])
def list_episodes(request: HttpRequest, task_id: int) -> list[PodcastEpisodeOut]:
    """列出任务关联的播客单集。"""
    episodes = _task_service.list_episodes(task_id=task_id, user=request.user)
    return [_episode_to_out(e) for e in episodes]

@router.get("/tasks/{task_id}/discussions", response=list[DiscussionScriptOut])
def list_discussion_scripts(request: HttpRequest, task_id: int) -> list[DiscussionScriptOut]:
    """列出任务关联的讨论稿。"""
    scripts = _task_service.list_discussion_scripts(task_id=task_id, user=request.user)
    return [_discussion_script_to_out(s) for s in scripts]

@router.get("/discussions/{script_id}", response=DiscussionScriptOut)
def get_discussion_script(request: HttpRequest, script_id: int) -> DiscussionScriptOut:
    """获取讨论稿详情（含轮次）。"""
    script = _task_service.get_discussion_script(script_id=script_id, user=request.user)
    return _discussion_script_to_out(script)

@router.put("/discussions/turns/{turn_id}", response=DiscussionTurnOut)
def update_discussion_turn(request: HttpRequest, turn_id: int, payload: DiscussionTurnUpdateIn) -> DiscussionTurnOut:
    """编辑讨论稿单轮对话。"""
    turn = _task_service.update_discussion_turn(
        turn_id=turn_id, text=payload.text, speaker_style_prompt=payload.speaker_style_prompt, user=request.user
    )
    return _discussion_turn_to_out(turn)

@router.post("/discussions/{script_id}/approve", response=DiscussionScriptOut)
def approve_discussion_script(request: HttpRequest, script_id: int, payload: ReviewActionIn) -> DiscussionScriptOut:
    """审核通过讨论稿。"""
    script = _task_service.approve_discussion_script(script_id=script_id, user=request.user, notes=payload.notes)
    return _discussion_script_to_out(script)

@router.post("/discussions/{script_id}/reject", response=DiscussionScriptOut)
def reject_discussion_script(request: HttpRequest, script_id: int, payload: ReviewActionIn) -> DiscussionScriptOut:
    """驳回讨论稿。"""
    script = _task_service.reject_discussion_script(script_id=script_id, user=request.user, notes=payload.notes)
    return _discussion_script_to_out(script)

@router.post("/discussions/{script_id}/regenerate", response=DiscussionScriptOut)
def regenerate_discussion_script(request: HttpRequest, script_id: int) -> DiscussionScriptOut:
    """重新生成讨论稿。"""
    script = _task_service.regenerate_discussion_script(script_id=script_id, user=request.user)
    return _discussion_script_to_out(script)

@router.post("/discussions/{script_id}/synthesize", response=PodcastEpisodeOut)
def synthesize_discussion(request: HttpRequest, script_id: int) -> PodcastEpisodeOut:
    """编辑后重新合成讨论稿音频。"""
    episode = _task_service.synthesize_discussion(script_id=script_id, user=request.user)
    return _episode_to_out(episode)

# --- 审核 ---

@router.post("/articles/{article_id}/approve", response=GeneratedArticleOut)
def approve_article(request: HttpRequest, article_id: int, payload: ReviewActionIn) -> GeneratedArticleOut:
    """审核通过文章。"""
    article = _task_service.approve_article(article_id=article_id, user=request.user, notes=payload.notes)
    return _article_to_out(article)

@router.post("/articles/{article_id}/reject", response=GeneratedArticleOut)
def reject_article(request: HttpRequest, article_id: int, payload: ReviewActionIn) -> GeneratedArticleOut:
    """驳回文章。"""
    article = _task_service.reject_article(article_id=article_id, user=request.user, notes=payload.notes)
    return _article_to_out(article)

@router.put("/articles/{article_id}", response=GeneratedArticleOut)
def update_article(request: HttpRequest, article_id: int, payload: ArticleUpdateIn) -> GeneratedArticleOut:
    """编辑文章内容。"""
    article = _task_service.update_article(
        article_id=article_id, title=payload.title, content=payload.content, user=request.user
    )
    return _article_to_out(article)

@router.post("/articles/{article_id}/regenerate", response=GeneratedArticleOut)
def regenerate_article(request: HttpRequest, article_id: int) -> GeneratedArticleOut:
    """重新生成文章。"""
    article = _task_service.regenerate_article(article_id=article_id, user=request.user)
    return _article_to_out(article)

@router.post("/articles/batch/approve")
def batch_approve_articles(request: HttpRequest, payload: BatchReviewIn) -> dict[str, Any]:
    """批量审核通过文章。"""
    results: list[dict[str, Any]] = []
    for article_id in payload.ids:
        try:
            _task_service.approve_article(article_id=article_id, user=request.user, notes=payload.notes)
            results.append({"id": article_id, "success": True})
        except Exception as e:
            results.append({"id": article_id, "success": False, "error": str(e)})
    return {"results": results}

@router.post("/episodes/batch/approve")
def batch_approve_episodes(request: HttpRequest, payload: BatchReviewIn) -> dict[str, Any]:
    """批量审核通过播客单集。"""
    results: list[dict[str, Any]] = []
    for episode_id in payload.ids:
        try:
            _task_service.approve_episode(episode_id=episode_id, user=request.user, notes=payload.notes)
            results.append({"id": episode_id, "success": True})
        except Exception as e:
            results.append({"id": episode_id, "success": False, "error": str(e)})
    return {"results": results}

@router.post("/episodes/{episode_id}/approve", response=PodcastEpisodeOut)
def approve_episode(request: HttpRequest, episode_id: int, payload: ReviewActionIn) -> PodcastEpisodeOut:
    """审核通过播客单集。"""
    episode = _task_service.approve_episode(episode_id=episode_id, user=request.user, notes=payload.notes)
    return _episode_to_out(episode)

@router.post("/episodes/{episode_id}/reject", response=PodcastEpisodeOut)
def reject_episode(request: HttpRequest, episode_id: int, payload: ReviewActionIn) -> PodcastEpisodeOut:
    """驳回播客单集。"""
    episode = _task_service.reject_episode(episode_id=episode_id, user=request.user, notes=payload.notes)
    return _episode_to_out(episode)

# --- 音频流 ---

@router.get("/episodes/{episode_id}/audio")
def episode_audio(request: HttpRequest, episode_id: int) -> dict[str, str] | FileResponse | HttpResponseBase:
    """获取播客单集音频。"""
    episode = _task_service.get_episode_audio(episode_id=episode_id, user=request.user)
    if not episode:
        return {"error": "音频不存在"}

    from apps.core.http.streaming import build_range_file_response

    return build_range_file_response(request, episode.audio_file.path)

# --- RSS ---

@router.get("/rss", auth=None)
def podcast_rss_feed(request: HttpRequest) -> HttpResponse:
    """播客 RSS Feed（无需认证）。"""
    from apps.content_ops.services.rss_service import RSSService

    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    xml = RSSService().generate_feed(request_host=f"{scheme}://{host}")

    return HttpResponse(xml, content_type="application/rss+xml; charset=utf-8")

# --- Helpers ---

def _task_to_out(task: Any) -> ContentTaskOut:
    return ContentTaskOut(
        id=task.pk,
        mode=task.mode,
        keyword=task.keyword,
        case_summary=task.case_summary,
        voice=task.voice,
        tts_style_prompt=task.tts_style_prompt,
        output_mode=task.output_mode or "narration",
        discussion_speakers=task.discussion_speakers or [],
        source_title=task.source_title,
        source_court_text=task.source_court_text,
        source_judgment_date=task.source_judgment_date,
        status=task.status,
        progress=task.progress,
        message=task.message,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )

def _article_to_out(article: Any) -> GeneratedArticleOut:
    return GeneratedArticleOut(
        id=article.pk,
        title=article.title,
        content=article.content,
        source_summary=article.source_summary,
        review_status=article.review_status,
        reviewer_notes=article.reviewer_notes,
        llm_model=article.llm_model,
        token_usage=article.token_usage or {},
        created_at=article.created_at,
        updated_at=article.updated_at,
    )

def _episode_to_out(episode: Any) -> PodcastEpisodeOut:
    audio_url = ""
    if episode.audio_file:
        audio_url = episode.audio_file.url
    return PodcastEpisodeOut(
        id=episode.pk,
        article_id=episode.article_id,
        discussion_script_id=episode.discussion_script_id,
        content_source=episode.content_source or "article",
        voice=episode.voice,
        audio_url=audio_url,
        duration_seconds=episode.duration_seconds,
        file_size_bytes=episode.file_size_bytes,
        review_status=episode.review_status,
        reviewer_notes=episode.reviewer_notes,
        created_at=episode.created_at,
        updated_at=episode.updated_at,
    )

def _discussion_turn_to_out(turn: Any) -> DiscussionTurnOut:
    return DiscussionTurnOut(
        id=turn.pk,
        speaker_name=turn.speaker_name,
        speaker_style_prompt=turn.speaker_style_prompt,
        text=turn.text,
        order=turn.order,
    )

def _discussion_script_to_out(script: Any) -> DiscussionScriptOut:
    turns = list(script.turns.order_by("order"))
    return DiscussionScriptOut(
        id=script.pk,
        title=script.title,
        topic=script.topic,
        review_status=script.review_status,
        reviewer_notes=script.reviewer_notes,
        turns=[_discussion_turn_to_out(t) for t in turns],
        llm_model=script.llm_model,
        token_usage=script.token_usage or {},
        created_at=script.created_at,
        updated_at=script.updated_at,
    )
