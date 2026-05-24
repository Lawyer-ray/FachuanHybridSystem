from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Schema


class TTSTestIn(Schema):
    """Request body for TTS test endpoint."""

    text: str
    voice: str = "冰糖"
    audio_format: str = "mp3"
    style_prompt: str = ""


class ContentTaskCreateIn(Schema):
    mode: str = "search"
    credential_id: int | None = None
    keyword: str | None = None
    case_summary: str = ""
    direct_content: str | None = None
    voice: str = "冰糖"
    tts_style_prompt: str = ""
    output_mode: str = "narration"
    discussion_speakers: list[dict[str, Any]] = []


class TopicSuggestIn(Schema):
    """选题建议请求参数。"""

    model: str = ""


class ReviewActionIn(Schema):
    notes: str = ""


class ArticleUpdateIn(Schema):
    title: str | None = None
    content: str | None = None


class BatchReviewIn(Schema):
    ids: list[int]
    notes: str = ""

    @staticmethod
    def validate_ids(ids: list[int]) -> list[int]:
        if len(ids) > 100:
            raise ValueError("单次批量操作最多 100 条")
        return ids


class DiscussionTurnUpdateIn(Schema):
    text: str | None = None
    speaker_style_prompt: str | None = None


class GeneratedArticleOut(Schema):
    id: int
    title: str
    content: str
    source_summary: str
    review_status: str
    reviewer_notes: str
    llm_model: str
    token_usage: dict
    created_at: datetime
    updated_at: datetime


class PodcastEpisodeOut(Schema):
    id: int
    article_id: int | None = None
    discussion_script_id: int | None = None
    content_source: str = "article"
    voice: str
    audio_url: str = ""
    duration_seconds: int | None = None
    file_size_bytes: int | None = None
    review_status: str
    reviewer_notes: str
    created_at: datetime
    updated_at: datetime


class DiscussionTurnOut(Schema):
    id: int
    speaker_name: str
    speaker_style_prompt: str
    text: str
    order: int


class DiscussionScriptOut(Schema):
    id: int
    title: str
    topic: str
    review_status: str
    reviewer_notes: str
    turns: list[DiscussionTurnOut]
    llm_model: str
    token_usage: dict
    created_at: datetime
    updated_at: datetime


class ContentTaskOut(Schema):
    id: int
    mode: str
    keyword: str
    case_summary: str
    voice: str
    tts_style_prompt: str
    output_mode: str = "narration"
    discussion_speakers: list[dict[str, Any]] = []
    source_title: str
    source_court_text: str
    source_judgment_date: str
    status: str
    progress: int
    message: str
    error: str
    created_at: datetime
    updated_at: datetime


class TopicSuggestionOut(Schema):
    title: str
    description: str
    suggested_keyword: str
