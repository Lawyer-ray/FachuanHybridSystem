"""Tests for wechat_mp schemas and API."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from apps.wechat_mp.schemas import (
    PublishTaskCreate,
    PublishTaskOut,
    WeChatAccountOut,
)


class TestWeChatAccountOut:
    def test_valid_schema(self) -> None:
        data = {
            "id": 1,
            "name": "测试公众号",
            "mp_url": "https://mp.weixin.qq.com/test",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
        }
        schema = WeChatAccountOut(**data)
        assert schema.id == 1
        assert schema.name == "测试公众号"
        assert schema.is_active is True


class TestPublishTaskCreate:
    def test_valid_schema(self) -> None:
        schema = PublishTaskCreate(
            title="测试文章",
            content_md="# Hello",
            account_id=1,
        )
        assert schema.title == "测试文章"
        assert schema.save_as_draft is True
        assert schema.format_method == "rule"

    def test_custom_values(self) -> None:
        schema = PublishTaskCreate(
            title="Test",
            content_md="content",
            account_id=2,
            save_as_draft=False,
            format_method="llm",
        )
        assert schema.save_as_draft is False
        assert schema.format_method == "llm"

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            PublishTaskCreate(title="Test")  # missing content_md and account_id


class TestPublishTaskOut:
    def test_valid_schema(self) -> None:
        data = {
            "id": 1,
            "account_id": 1,
            "title": "Test",
            "status": "completed",
            "save_as_draft": True,
            "format_method": "rule",
            "result_data": {},
            "error_message": "",
            "created_at": "2024-01-01T00:00:00",
            "started_at": None,
            "finished_at": None,
        }
        schema = PublishTaskOut(**data)
        assert schema.id == 1
        assert schema.status == "completed"
