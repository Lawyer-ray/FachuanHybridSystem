"""Tests for ContentOpsTaskService."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions.common import NotFoundError, PermissionDenied, ValidationException
from apps.content_ops.services.task_service import ContentOpsTaskService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> ContentOpsTaskService:
    return ContentOpsTaskService()


def _make_payload(**overrides: Any) -> MagicMock:
    payload = MagicMock()
    payload.mode = overrides.get("mode", "search")
    payload.keyword = overrides.get("keyword", "test keyword")
    payload.credential_id = overrides.get("credential_id", 1)
    payload.case_summary = overrides.get("case_summary", "")
    payload.direct_content = overrides.get("direct_content", "")
    payload.voice = overrides.get("voice", "冰糖")
    payload.tts_style_prompt = overrides.get("tts_style_prompt", "")
    payload.output_mode = overrides.get("output_mode", "narration")
    payload.discussion_speakers = overrides.get("discussion_speakers", [])
    return payload


def _make_task(**overrides: Any) -> MagicMock:
    task = MagicMock()
    task.pk = overrides.get("pk", 1)
    task.id = overrides.get("pk", 1)
    task.status = overrides.get("status", "pending")
    task.created_by_id = overrides.get("created_by_id", 10)
    task.created_by = MagicMock()
    task.created_by.is_authenticated = True
    task.created_by.pk = overrides.get("created_by_id", 10)
    task.source_facts = overrides.get("source_facts", "some facts")
    task.case_summary = overrides.get("case_summary", "summary")
    task.discussion_speakers = overrides.get("discussion_speakers", [{"name": "A", "style_prompt": ""}])
    task.delete = MagicMock()
    task.save = MagicMock()
    return task


def _make_article(**overrides: Any) -> MagicMock:
    article = MagicMock()
    article.pk = overrides.get("pk", 1)
    article.review_status = overrides.get("review_status", "draft")
    article.task = overrides.get("task", _make_task())
    article.save = MagicMock()
    return article


def _make_episode(**overrides: Any) -> MagicMock:
    ep = MagicMock()
    ep.pk = overrides.get("pk", 1)
    ep.review_status = overrides.get("review_status", "draft")
    ep.task = overrides.get("task", _make_task())
    ep.audio_file = overrides.get("audio_file", MagicMock())
    ep.save = MagicMock()
    return ep


def _make_script(**overrides: Any) -> MagicMock:
    script = MagicMock()
    script.pk = overrides.get("pk", 1)
    script.review_status = overrides.get("review_status", "draft")
    script.task = overrides.get("task", _make_task())
    script.turns = MagicMock()
    script.save = MagicMock()
    return script


def _make_user(user_id: int = 10, authenticated: bool = True) -> MagicMock:
    user = MagicMock()
    user.pk = user_id
    user.id = user_id
    user.is_authenticated = authenticated
    return user


# ===========================================================================
# Create task tests
# ===========================================================================


class TestCreateTask:
    def test_search_mode_valid(self) -> None:
        svc = _make_service()
        payload = _make_payload(mode="search", keyword="test", credential_id=1)
        user = _make_user()

        with (
            patch("apps.content_ops.services.task_service.ContentTask") as MockTask,
            patch("apps.content_ops.services.task_service.transaction") as mock_tx,
            patch("apps.organization.models.AccountCredential") as MockCred,
            patch.object(svc, "dispatch_task", return_value=True) as mock_dispatch,
        ):
            MockCred.objects.filter.return_value.first.return_value = MagicMock()
            MockTask.return_value = MagicMock()
            mock_tx.atomic.return_value.__enter__ = MagicMock()
            mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)
            result = svc.create_task(payload=payload, user=user)
        mock_dispatch.assert_called_once()

    def test_search_mode_no_keyword_raises(self) -> None:
        svc = _make_service()
        payload = _make_payload(mode="search", keyword=None, credential_id=1)
        with pytest.raises(ValidationException, match="keyword"):
            svc.create_task(payload=payload, user=_make_user())

    def test_search_mode_no_credential_raises(self) -> None:
        svc = _make_service()
        payload = _make_payload(mode="search", keyword="test", credential_id=None)
        with pytest.raises(ValidationException, match="credential_id"):
            svc.create_task(payload=payload, user=_make_user())

    def test_direct_mode_valid(self) -> None:
        svc = _make_service()
        payload = _make_payload(mode="direct", direct_content="content here")
        with (
            patch("apps.content_ops.services.task_service.ContentTask") as MockTask,
            patch("apps.content_ops.services.task_service.transaction") as mock_tx,
            patch.object(svc, "dispatch_task", return_value=True) as mock_dispatch,
        ):
            MockTask.return_value = MagicMock()
            mock_tx.atomic.return_value.__enter__ = MagicMock()
            mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)
            svc.create_task(payload=payload, user=_make_user())
        mock_dispatch.assert_called_once()

    def test_direct_mode_no_content_raises(self) -> None:
        svc = _make_service()
        payload = _make_payload(mode="direct", direct_content=None)
        with pytest.raises(ValidationException, match="direct_content"):
            svc.create_task(payload=payload, user=_make_user())

    def test_credential_not_found_raises(self) -> None:
        svc = _make_service()
        payload = _make_payload(mode="search", keyword="test", credential_id=999)
        user = _make_user()

        with (
            patch("apps.content_ops.services.task_service.ContentTask") as MockTask,
            patch("apps.content_ops.services.task_service.transaction") as mock_tx,
            patch("apps.organization.models.AccountCredential") as MockCred,
        ):
            MockCred.objects.filter.return_value.first.return_value = None
            MockTask.return_value = MagicMock()
            mock_tx.atomic.return_value.__enter__ = MagicMock()
            mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(ValidationException, match="凭证"):
                svc.create_task(payload=payload, user=user)


# ===========================================================================
# Dispatch task tests
# ===========================================================================


class TestDispatchTask:
    def test_success(self) -> None:
        svc = _make_service()
        task = _make_task()
        with patch("apps.content_ops.services.task_service.submit_task", return_value="q-id-123") as mock_submit:
            result = svc.dispatch_task(task=task)
            assert result is True
            assert task.q_task_id == "q-id-123"
            task.save.assert_called()

    def test_failure(self) -> None:
        svc = _make_service()
        task = _make_task()
        with patch("apps.content_ops.services.task_service.submit_task", side_effect=RuntimeError("queue error")):
            result = svc.dispatch_task(task=task)
            assert result is False
            assert task.status == "failed"
            assert "失败" in task.message


# ===========================================================================
# Get task tests
# ===========================================================================


class TestGetTask:
    def test_not_found(self) -> None:
        svc = _make_service()
        with patch("apps.content_ops.services.task_service.ContentTask") as MockTask:
            MockTask.objects.select_related.return_value.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.get_task(task_id=999, user=_make_user())

    def test_permission_denied(self) -> None:
        svc = _make_service()
        task = _make_task(created_by_id=10)
        user = _make_user(user_id=20)
        with patch("apps.content_ops.services.task_service.ContentTask") as MockTask:
            MockTask.objects.select_related.return_value.filter.return_value.first.return_value = task
            with pytest.raises(PermissionDenied):
                svc.get_task(task_id=1, user=user)

    def test_success(self) -> None:
        svc = _make_service()
        task = _make_task(created_by_id=10)
        user = _make_user(user_id=10)
        with patch("apps.content_ops.services.task_service.ContentTask") as MockTask:
            MockTask.objects.select_related.return_value.filter.return_value.first.return_value = task
            result = svc.get_task(task_id=1, user=user)
            assert result == task

    def test_unauthenticated_user_can_access(self) -> None:
        svc = _make_service()
        task = _make_task(created_by_id=10)
        user = _make_user(user_id=20, authenticated=False)
        with patch("apps.content_ops.services.task_service.ContentTask") as MockTask:
            MockTask.objects.select_related.return_value.filter.return_value.first.return_value = task
            result = svc.get_task(task_id=1, user=user)
            assert result == task


# ===========================================================================
# List tasks tests
# ===========================================================================


class TestListTasks:
    def test_returns_list(self) -> None:
        svc = _make_service()
        with patch("apps.content_ops.services.task_service.ContentTask") as MockTask:
            MockTask.objects.select_related.return_value.filter.return_value.__getitem__ = MagicMock(return_value=[])
            MockTask.objects.select_related.return_value.filter.return_value = MockTask.objects.select_related.return_value
            result = svc.list_tasks(user=_make_user(), mode="search")
            assert isinstance(result, list)

    def test_no_user_returns_all(self) -> None:
        svc = _make_service()
        with patch("apps.content_ops.services.task_service.ContentTask") as MockTask:
            MockTask.objects.select_related.return_value.__getitem__ = MagicMock(return_value=[])
            result = svc.list_tasks(user=None)
            assert isinstance(result, list)


# ===========================================================================
# Article approve / reject tests
# ===========================================================================


class TestApproveArticle:
    def test_approve(self) -> None:
        svc = _make_service()
        article = _make_article()
        user = _make_user()
        with patch.object(svc, "_get_article", return_value=article):
            result = svc.approve_article(article_id=1, user=user, notes="good")
            assert article.review_status == "approved"
            assert article.reviewer_notes == "good"
            article.save.assert_called()


class TestRejectArticle:
    def test_reject(self) -> None:
        svc = _make_service()
        article = _make_article()
        user = _make_user()
        with patch.object(svc, "_get_article", return_value=article):
            result = svc.reject_article(article_id=1, user=user, notes="bad")
            assert article.review_status == "rejected"
            article.save.assert_called()


class TestGetArticleNotFound:
    def test_not_found(self) -> None:
        with patch("apps.content_ops.services.task_service.GeneratedArticle") as MockArt:
            MockArt.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                ContentOpsTaskService._get_article(999)


# ===========================================================================
# Episode approve / reject tests
# ===========================================================================


class TestApproveEpisode:
    def test_approve(self) -> None:
        svc = _make_service()
        episode = _make_episode()
        user = _make_user()
        with patch.object(svc, "_get_episode", return_value=episode):
            result = svc.approve_episode(episode_id=1, user=user, notes="ok")
            assert episode.review_status == "approved"
            episode.save.assert_called()


class TestRejectEpisode:
    def test_reject(self) -> None:
        svc = _make_service()
        episode = _make_episode()
        user = _make_user()
        with patch.object(svc, "_get_episode", return_value=episode):
            result = svc.reject_episode(episode_id=1, user=user, notes="no")
            assert episode.review_status == "rejected"
            episode.save.assert_called()


class TestGetEpisodeNotFound:
    def test_not_found(self) -> None:
        with patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp:
            MockEp.objects.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                ContentOpsTaskService._get_episode(999)


# ===========================================================================
# Update article tests
# ===========================================================================


class TestUpdateArticle:
    def test_update_draft(self) -> None:
        svc = _make_service()
        article = _make_article(review_status="draft")
        with patch.object(svc, "_get_article", return_value=article):
            result = svc.update_article(article_id=1, title="New Title", content="New Content")
            assert article.title == "New Title"
            assert article.content == "New Content"
            article.save.assert_called()

    def test_update_non_draft_raises(self) -> None:
        svc = _make_service()
        article = _make_article(review_status="approved")
        with patch.object(svc, "_get_article", return_value=article):
            with pytest.raises(ValidationException, match="草稿"):
                svc.update_article(article_id=1, title="X")


# ===========================================================================
# Retry task tests
# ===========================================================================


class TestRetryTask:
    def test_retry_failed(self) -> None:
        svc = _make_service()
        task = _make_task(status="failed")
        user = _make_user()
        with (
            patch.object(svc, "get_task", return_value=task),
            patch("apps.content_ops.services.task_service.GeneratedArticle") as MockArt,
            patch("apps.content_ops.services.task_service.DiscussionScript") as MockDS,
            patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp,
            patch.object(svc, "dispatch_task", return_value=True),
        ):
            result = svc.retry_task(task_id=1, user=user)
            assert task.status == "pending"
            assert task.progress == 0
            assert task.error == ""
            MockArt.objects.filter.return_value.delete.assert_called()
            MockDS.objects.filter.return_value.delete.assert_called()
            MockEp.objects.filter.return_value.delete.assert_called()

    def test_retry_non_failed_raises(self) -> None:
        svc = _make_service()
        task = _make_task(status="running")
        with patch.object(svc, "get_task", return_value=task):
            with pytest.raises(ValidationException, match="失败"):
                svc.retry_task(task_id=1, user=_make_user())


# ===========================================================================
# Cancel task tests
# ===========================================================================


class TestCancelTask:
    def test_cancel_pending(self) -> None:
        svc = _make_service()
        task = _make_task(status="pending")
        with patch.object(svc, "get_task", return_value=task):
            result = svc.cancel_task(task_id=1, user=_make_user())
            assert task.status == "cancelled"
            task.save.assert_called()

    def test_cancel_non_cancellable_raises(self) -> None:
        svc = _make_service()
        task = _make_task(status="completed")
        with patch.object(svc, "get_task", return_value=task):
            with pytest.raises(ValidationException):
                svc.cancel_task(task_id=1, user=_make_user())


# ===========================================================================
# Delete task tests
# ===========================================================================


class TestDeleteTask:
    def test_delete_pending(self) -> None:
        svc = _make_service()
        task = _make_task(status="pending")
        with patch.object(svc, "get_task", return_value=task):
            svc.delete_task(task_id=1, user=_make_user())
            task.delete.assert_called_once()

    def test_delete_running_raises(self) -> None:
        svc = _make_service()
        task = _make_task(status="running")
        with patch.object(svc, "get_task", return_value=task):
            with pytest.raises(ValidationException, match="执行"):
                svc.delete_task(task_id=1, user=_make_user())

    def test_delete_queued_raises(self) -> None:
        svc = _make_service()
        task = _make_task(status="queued")
        with patch.object(svc, "get_task", return_value=task):
            with pytest.raises(ValidationException):
                svc.delete_task(task_id=1, user=_make_user())


# ===========================================================================
# Discussion script tests
# ===========================================================================


class TestListDiscussionScripts:
    def test_returns_list(self) -> None:
        svc = _make_service()
        task = _make_task()
        with patch.object(svc, "get_task", return_value=task), \
             patch("apps.content_ops.services.task_service.DiscussionScript") as MockDS:
            MockDS.objects.filter.return_value.order_by.return_value = []
            result = svc.list_discussion_scripts(task_id=1, user=_make_user())
            assert isinstance(result, list)


class TestGetDiscussionScript:
    def test_not_found(self) -> None:
        with patch("apps.content_ops.services.task_service.DiscussionScript") as MockDS:
            MockDS.objects.select_related.return_value.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                ContentOpsTaskService._get_discussion_script(999)


class TestApproveDiscussionScript:
    def test_approve(self) -> None:
        svc = _make_service()
        script = _make_script()
        user = _make_user()
        with patch.object(svc, "_get_discussion_script", return_value=script):
            result = svc.approve_discussion_script(script_id=1, user=user, notes="ok")
            assert script.review_status == "approved"
            script.save.assert_called()


class TestRejectDiscussionScript:
    def test_reject(self) -> None:
        svc = _make_service()
        script = _make_script()
        user = _make_user()
        with patch.object(svc, "_get_discussion_script", return_value=script):
            result = svc.reject_discussion_script(script_id=1, user=user, notes="no")
            assert script.review_status == "rejected"
            script.save.assert_called()


# ===========================================================================
# Update discussion turn tests
# ===========================================================================


class TestUpdateDiscussionTurn:
    def test_update_draft_turn(self) -> None:
        svc = _make_service()
        script = _make_script(review_status="draft")
        turn = MagicMock()
        turn.script = script
        turn.text = "old text"
        turn.speaker_style_prompt = "old"
        turn.save = MagicMock()
        with patch("apps.content_ops.services.task_service.DiscussionTurn") as MockTurn:
            MockTurn.objects.select_related.return_value.filter.return_value.first.return_value = turn
            result = svc.update_discussion_turn(turn_id=1, text="new text", user=_make_user())
            assert turn.text == "new text"
            turn.save.assert_called()

    def test_update_non_draft_raises(self) -> None:
        svc = _make_service()
        script = _make_script(review_status="approved")
        turn = MagicMock()
        turn.script = script
        with patch("apps.content_ops.services.task_service.DiscussionTurn") as MockTurn:
            MockTurn.objects.select_related.return_value.filter.return_value.first.return_value = turn
            with pytest.raises(ValidationException, match="草稿"):
                svc.update_discussion_turn(turn_id=1, text="X", user=_make_user())

    def test_turn_not_found(self) -> None:
        with patch("apps.content_ops.services.task_service.DiscussionTurn") as MockTurn:
            MockTurn.objects.select_related.return_value.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc = ContentOpsTaskService()
                svc.update_discussion_turn(turn_id=999, text="X", user=_make_user())


# ===========================================================================
# Regenerate article tests
# ===========================================================================


class TestRegenerateArticle:
    _LAZY_CHAIN = "apps.content_ops.services.content_chain.ContentGenerationChain"

    def test_regenerate(self) -> None:
        svc = _make_service()
        task = _make_task(source_facts="facts here", case_summary="summary")
        article = _make_article(task=task)
        user = _make_user()

        mock_result = MagicMock()
        mock_result.title = "New Title"
        mock_result.content = "New Content"
        mock_result.summary = "New Summary"
        mock_result.model = "gpt-4"
        mock_result.token_usage = 100

        with (
            patch.object(svc, "_get_article", return_value=article),
            patch(self._LAZY_CHAIN) as MockChain,
        ):
            MockChain.return_value.run.return_value = mock_result
            result = svc.regenerate_article(article_id=1, user=user)
            assert article.title == "New Title"
            assert article.review_status == "draft"
            article.save.assert_called()

    def test_no_source_facts_raises(self) -> None:
        svc = _make_service()
        task = _make_task(source_facts=None)
        article = _make_article(task=task)
        with patch.object(svc, "_get_article", return_value=article):
            with pytest.raises(ValidationException, match="案件事实"):
                svc.regenerate_article(article_id=1, user=_make_user())


# ===========================================================================
# Regenerate discussion script tests
# ===========================================================================


class TestRegenerateDiscussionScript:
    _LAZY_DISC_CHAIN = "apps.content_ops.services.discussion_chain.DiscussionGenerationChain"

    def test_regenerate(self) -> None:
        svc = _make_service()
        task = _make_task(source_facts="facts", discussion_speakers=[{"name": "A", "style_prompt": "style"}])
        script = _make_script(task=task)
        user = _make_user()

        mock_result = MagicMock()
        mock_result.title = "New Title"
        mock_result.topic = "New Topic"
        mock_result.model = "gpt-4"
        mock_result.token_usage = 100
        mock_result.turns = [{"speaker": "A", "text": "Hello"}]

        with (
            patch.object(svc, "_get_discussion_script", return_value=script),
            patch(self._LAZY_DISC_CHAIN) as MockChain,
            patch("apps.content_ops.services.task_service.DiscussionTurn") as MockTurn,
        ):
            MockChain.return_value.run.return_value = mock_result
            result = svc.regenerate_discussion_script(script_id=1, user=user)
            assert script.review_status == "draft"
            script.save.assert_called()

    def test_no_source_facts_raises(self) -> None:
        svc = _make_service()
        task = _make_task(source_facts=None)
        script = _make_script(task=task)
        with patch.object(svc, "_get_discussion_script", return_value=script):
            with pytest.raises(ValidationException, match="案件事实"):
                svc.regenerate_discussion_script(script_id=1, user=_make_user())


# ===========================================================================
# Synthesize discussion tests
# ===========================================================================


class TestSynthesizeDiscussion:
    _LAZY_TTS = "apps.content_ops.services.tts_service.TTSService"

    def test_synthesize(self) -> None:
        svc = _make_service()
        task = _make_task()
        script = _make_script(task=task)
        turn = MagicMock()
        turn.text = "Hello"
        turn.speaker_style_prompt = "style"
        turn.speaker_name = "A"
        script.turns.order_by.return_value = [turn]
        user = _make_user()

        with (
            patch.object(svc, "_get_discussion_script", return_value=script),
            patch(self._LAZY_TTS) as MockTTS,
            patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp,
            patch("apps.content_ops.services.task_service.ContentFile") as MockCF,
        ):
            MockTTS.return_value.synthesize_discussion.return_value = b"audio-data"
            result = svc.synthesize_discussion(script_id=1, user=user)
            MockTTS.return_value.synthesize_discussion.assert_called_once()

    def test_no_turns_raises(self) -> None:
        svc = _make_service()
        task = _make_task()
        script = _make_script(task=task)
        script.turns.order_by.return_value = []
        with patch.object(svc, "_get_discussion_script", return_value=script):
            with pytest.raises(ValidationException, match="对话轮次"):
                svc.synthesize_discussion(script_id=1, user=_make_user())


# ===========================================================================
# Permission check tests
# ===========================================================================


class TestCheckPermission:
    def test_authenticated_user_owner(self) -> None:
        task = _make_task(created_by_id=10)
        user = _make_user(user_id=10)
        # Should not raise
        ContentOpsTaskService._check_permission(task, user)

    def test_authenticated_user_not_owner(self) -> None:
        task = _make_task(created_by_id=10)
        user = _make_user(user_id=20)
        with pytest.raises(PermissionDenied):
            ContentOpsTaskService._check_permission(task, user)

    def test_unauthenticated_user(self) -> None:
        task = _make_task(created_by_id=10)
        user = _make_user(user_id=20, authenticated=False)
        # Should not raise
        ContentOpsTaskService._check_permission(task, user)

    def test_no_user(self) -> None:
        task = _make_task(created_by_id=10)
        ContentOpsTaskService._check_permission(task, None)


# ===========================================================================
# Get episode audio tests
# ===========================================================================


class TestGetEpisodeAudio:
    def test_returns_episode(self) -> None:
        svc = _make_service()
        ep = _make_episode()
        with patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp:
            MockEp.objects.filter.return_value.select_related.return_value.first.return_value = ep
            result = svc.get_episode_audio(episode_id=1, user=_make_user())
            assert result == ep

    def test_no_audio_file(self) -> None:
        svc = _make_service()
        ep = _make_episode(audio_file=None)
        with patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp:
            MockEp.objects.filter.return_value.select_related.return_value.first.return_value = ep
            result = svc.get_episode_audio(episode_id=1, user=_make_user())
            assert result is None

    def test_not_found(self) -> None:
        with patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp:
            MockEp.objects.filter.return_value.select_related.return_value.first.return_value = None
            result = ContentOpsTaskService().get_episode_audio(episode_id=999, user=_make_user())
            assert result is None


# ===========================================================================
# List articles / episodes tests
# ===========================================================================


class TestListArticles:
    def test_returns_list(self) -> None:
        svc = _make_service()
        with patch.object(svc, "get_task", return_value=_make_task()), \
             patch("apps.content_ops.services.task_service.GeneratedArticle") as MockArt:
            MockArt.objects.filter.return_value.order_by.return_value = []
            result = svc.list_articles(task_id=1, user=_make_user())
            assert isinstance(result, list)


class TestListEpisodes:
    def test_returns_list(self) -> None:
        svc = _make_service()
        with patch.object(svc, "get_task", return_value=_make_task()), \
             patch("apps.content_ops.services.task_service.PodcastEpisode") as MockEp:
            MockEp.objects.filter.return_value.order_by.return_value = []
            result = svc.list_episodes(task_id=1, user=_make_user())
            assert isinstance(result, list)
