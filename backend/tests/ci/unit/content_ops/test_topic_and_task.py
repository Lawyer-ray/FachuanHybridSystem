"""内容运营选题服务和任务服务测试。"""

from __future__ import annotations

from apps.content_ops.services.topic_service import TopicResult


class TestTopicResult:
    """TopicResult 数据类测试。"""

    def test_creation(self) -> None:
        result = TopicResult(
            topics=[{"title": "测试选题", "description": "测试描述"}],
            model="gpt-4",
            token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        )
        assert len(result.topics) == 1
        assert result.model == "gpt-4"
        assert result.token_usage["prompt_tokens"] == 100

    def test_empty_topics(self) -> None:
        result = TopicResult(topics=[], model="test", token_usage={})
        assert result.topics == []


class TestWeChatPublisherConstants:
    """WeChatPublisher 常量测试。"""

    def test_mp_home_url(self) -> None:
        from apps.wechat_mp.services.publisher import MP_HOME_URL

        assert "mp.weixin.qq.com" in MP_HOME_URL

    def test_publish_error_inheritance(self) -> None:
        from apps.wechat_mp.services.publisher import PublishError

        assert issubclass(PublishError, Exception)
        e = PublishError("发布失败")
        assert str(e) == "发布失败"


class TestContentOpsTaskServiceConstants:
    """ContentOpsTaskService 常量测试。"""

    def test_queued_message(self) -> None:
        from apps.content_ops.services.task_service import _QUEUED_MESSAGE

        assert "已提交队列" in _QUEUED_MESSAGE

    def test_create_pending_message(self) -> None:
        from apps.content_ops.services.task_service import _CREATE_PENDING_MESSAGE

        assert "已创建" in _CREATE_PENDING_MESSAGE
