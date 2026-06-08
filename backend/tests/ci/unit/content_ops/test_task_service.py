"""内容运营任务服务测试。"""

from unittest.mock import MagicMock, patch

import pytest

from apps.content_ops.services.task_service import ContentOpsTaskService


class TestContentOpsTaskServiceHelpers:
    """ContentOpsTaskService 辅助方法测试。"""

    def _make_service(self):
        return ContentOpsTaskService()

    # ── _check_permission ──

    def test_check_permission_owner(self):
        svc = self._make_service()
        task = MagicMock()
        task.created_by_id = 1
        user = MagicMock()
        user.is_authenticated = True
        user.id = 1
        # Should not raise
        svc._check_permission(task, user)

    def test_check_permission_non_owner_raises(self):
        svc = self._make_service()
        task = MagicMock()
        task.created_by_id = 1
        user = MagicMock()
        user.is_authenticated = True
        user.id = 2
        from apps.core.exceptions.common import PermissionDenied
        with pytest.raises(PermissionDenied):
            svc._check_permission(task, user)

    def test_check_permission_anonymous(self):
        svc = self._make_service()
        task = MagicMock()
        task.created_by_id = 1
        user = MagicMock()
        user.is_authenticated = False
        # Should not raise for anonymous users
        svc._check_permission(task, user)

    def test_check_permission_none_user(self):
        svc = self._make_service()
        task = MagicMock()
        task.created_by_id = 1
        svc._check_permission(task, None)

    def test_check_permission_no_creator(self):
        svc = self._make_service()
        task = MagicMock()
        task.created_by_id = None
        user = MagicMock()
        user.is_authenticated = True
        svc._check_permission(task, user)

    # ── list_tasks filtering ──

    @patch("apps.content_ops.services.task_service.ContentTask")
    def test_list_tasks_with_mode_filter(self, mock_ct):
        svc = self._make_service()
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.__getitem__ = MagicMock(return_value=[])
        mock_ct.objects.select_related.return_value = qs
        user = MagicMock()
        user.is_authenticated = True
        result = svc.list_tasks(user=user, mode="search")
        qs.filter.assert_called()

    # ── get_task ──

    @patch("apps.content_ops.services.task_service.ContentTask")
    def test_get_task_not_found(self, mock_ct):
        svc = self._make_service()
        qs = MagicMock()
        qs.select_related.return_value = qs
        qs.filter.return_value = qs
        qs.first.return_value = None
        mock_ct.objects.select_related.return_value = qs
        from apps.core.exceptions.common import NotFoundError
        with pytest.raises(NotFoundError):
            svc.get_task(task_id=999, user=None)

    # ── _get_article ──

    @patch("apps.content_ops.services.task_service.GeneratedArticle")
    def test_get_article_not_found(self, mock_model):
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.first.return_value = None
        mock_model.objects.filter.return_value = qs
        from apps.core.exceptions.common import NotFoundError
        with pytest.raises(NotFoundError):
            ContentOpsTaskService._get_article(999)

    # ── _get_episode ──

    @patch("apps.content_ops.services.task_service.PodcastEpisode")
    def test_get_episode_not_found(self, mock_model):
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.first.return_value = None
        mock_model.objects.filter.return_value = qs
        from apps.core.exceptions.common import NotFoundError
        with pytest.raises(NotFoundError):
            ContentOpsTaskService._get_episode(999)

    # ── _get_discussion_script ──

    @patch("apps.content_ops.services.task_service.DiscussionScript")
    def test_get_discussion_script_not_found(self, mock_model):
        qs = MagicMock()
        qs.select_related.return_value = qs
        qs.filter.return_value = qs
        qs.first.return_value = None
        mock_model.objects.select_related.return_value = qs
        from apps.core.exceptions.common import NotFoundError
        with pytest.raises(NotFoundError):
            ContentOpsTaskService._get_discussion_script(999)

    # ── create_task validation ──

    def test_create_task_search_without_keyword_raises(self):
        svc = self._make_service()
        payload = MagicMock()
        payload.mode = "search"
        payload.keyword = None
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.create_task(payload=payload)

    def test_create_task_search_without_credential_raises(self):
        svc = self._make_service()
        payload = MagicMock()
        payload.mode = "search"
        payload.keyword = "test"
        payload.credential_id = None
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.create_task(payload=payload)

    def test_create_task_direct_without_content_raises(self):
        svc = self._make_service()
        payload = MagicMock()
        payload.mode = "direct"
        payload.direct_content = None
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.create_task(payload=payload)

    # ── cancel_task validation ──

    @patch.object(ContentOpsTaskService, "get_task")
    def test_cancel_task_wrong_status(self, mock_get):
        svc = self._make_service()
        task = MagicMock()
        task.status = "completed"
        mock_get.return_value = task
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.cancel_task(task_id=1)

    # ── delete_task validation ──

    @patch.object(ContentOpsTaskService, "get_task")
    def test_delete_task_running_raises(self, mock_get):
        svc = self._make_service()
        task = MagicMock()
        task.status = "running"
        mock_get.return_value = task
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.delete_task(task_id=1)

    # ── retry_task validation ──

    @patch.object(ContentOpsTaskService, "get_task")
    def test_retry_task_not_failed_raises(self, mock_get):
        svc = self._make_service()
        task = MagicMock()
        task.status = "completed"
        mock_get.return_value = task
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.retry_task(task_id=1)

    # ── update_article validation ──

    @patch.object(ContentOpsTaskService, "_get_article")
    def test_update_article_non_draft_raises(self, mock_get):
        svc = self._make_service()
        article = MagicMock()
        article.review_status = "approved"
        mock_get.return_value = article
        from apps.core.exceptions.common import ValidationException
        with pytest.raises(ValidationException):
            svc.update_article(article_id=1, title="new title")

    # ── get_episode_audio ──

    @patch("apps.content_ops.services.task_service.PodcastEpisode")
    def test_get_episode_audio_not_found(self, mock_model):
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.select_related.return_value = qs
        qs.first.return_value = None
        mock_model.objects.filter.return_value = qs
        result = ContentOpsTaskService().get_episode_audio(episode_id=999)
        assert result is None

    @patch("apps.content_ops.services.task_service.PodcastEpisode")
    def test_get_episode_audio_no_audio(self, mock_model):
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.select_related.return_value = qs
        episode = MagicMock()
        episode.audio_file = None
        qs.first.return_value = episode
        mock_model.objects.filter.return_value = qs
        result = ContentOpsTaskService().get_episode_audio(episode_id=1)
        assert result is None

    @patch("apps.content_ops.services.task_service.PodcastEpisode")
    def test_get_episode_audio_wrong_owner(self, mock_model):
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.select_related.return_value = qs
        episode = MagicMock()
        episode.audio_file = MagicMock()
        episode.task.created_by_id = 1
        qs.first.return_value = episode
        mock_model.objects.filter.return_value = qs
        user = MagicMock()
        user.pk = 2
        result = ContentOpsTaskService().get_episode_audio(episode_id=1, user=user)
        assert result is None
