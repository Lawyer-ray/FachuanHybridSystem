"""Tests for story_viz/tasks.py - generate_story_animation."""

from unittest.mock import MagicMock, patch

import pytest


class TestGenerateStoryAnimation:
    """Test generate_story_animation task."""

    @patch("apps.story_viz.tasks.get_story_animation_workflow_service")
    def test_calls_workflow_service(self, mock_get_service):
        """Calls workflow service with animation_id."""
        from apps.story_viz.tasks import generate_story_animation

        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        generate_story_animation("test-animation-id")

        mock_service.run.assert_called_once_with(animation_id="test-animation-id")

    @patch("apps.story_viz.tasks.get_story_animation_workflow_service")
    def test_raises_on_failure(self, mock_get_service):
        """Re-raises exceptions from workflow service."""
        from apps.story_viz.tasks import generate_story_animation

        mock_service = MagicMock()
        mock_service.run.side_effect = RuntimeError("Pipeline failed")
        mock_get_service.return_value = mock_service

        with pytest.raises(RuntimeError, match="Pipeline failed"):
            generate_story_animation("test-animation-id")

    @patch("apps.story_viz.tasks.get_story_animation_workflow_service")
    def test_logs_exception_on_failure(self, mock_get_service):
        """Logs exception when workflow service fails."""
        from apps.story_viz.tasks import generate_story_animation

        mock_service = MagicMock()
        mock_service.run.side_effect = ValueError("Bad input")
        mock_get_service.return_value = mock_service

        with pytest.raises(ValueError):
            generate_story_animation("bad-id")
