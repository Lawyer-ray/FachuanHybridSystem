"""Coverage tests for content_ops.services.topic_service and discussion_chain."""

from unittest.mock import MagicMock, patch

import pytest


class TestTopicResult:
    def test_topic_result(self):
        from apps.content_ops.services.topic_service import TopicResult

        result = TopicResult(
            topics=[{"title": "test"}],
            model="gpt-4",
            token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        assert len(result.topics) == 1
        assert result.model == "gpt-4"


class TestDiscussionOutput:
    def test_discussion_output(self):
        from apps.content_ops.services.discussion_chain import DiscussionOutput

        output = DiscussionOutput(
            title="Test",
            topic="topic",
            turns=[{"speaker": "A", "text": "hello"}],
            model="gpt-4",
            token_usage={},
        )
        assert output.title == "Test"
        assert len(output.turns) == 1


class TestDiscussionTurnResult:
    def test_model(self):
        from apps.content_ops.services.discussion_chain import DiscussionTurnResult

        turn = DiscussionTurnResult(speaker="Alice", text="Hello")
        assert turn.speaker == "Alice"
        assert turn.text == "Hello"


class TestDiscussionResult:
    def test_model(self):
        from apps.content_ops.services.discussion_chain import DiscussionResult, DiscussionTurnResult

        result = DiscussionResult(
            title="title",
            topic="topic",
            turns=[DiscussionTurnResult(speaker="A", text="B")],
        )
        assert len(result.turns) == 1
