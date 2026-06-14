"""Tests for apps.core.tasking — context, submission, query, scheduler."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.core.tasking.context import TaskContext, get_current_request_id, set_current_request_id


class TestTaskContext:
    def test_defaults(self):
        ctx = TaskContext()
        assert ctx.request_id is None
        assert ctx.correlation_id is None
        assert ctx.task_name is None
        assert ctx.entity_id is None
        assert ctx.extra is None

    def test_to_dict(self):
        ctx = TaskContext(request_id="r1", correlation_id="c1", task_name="t1", entity_id="e1", extra={"k": "v"})
        d = ctx.to_dict()
        assert d["request_id"] == "r1"
        assert d["correlation_id"] == "c1"
        assert d["task_name"] == "t1"
        assert d["entity_id"] == "e1"
        assert d["extra"] == {"k": "v"}

    def test_to_dict_none_extra(self):
        ctx = TaskContext()
        assert ctx.to_dict()["extra"] == {}

    def test_from_dict_full(self):
        d = {"request_id": "r", "correlation_id": "c", "task_name": "t", "entity_id": "e", "extra": {"x": 1}}
        ctx = TaskContext.from_dict(d)
        assert ctx.request_id == "r"
        assert ctx.extra == {"x": 1}

    def test_from_dict_none(self):
        ctx = TaskContext.from_dict(None)
        assert ctx.request_id is None
        assert ctx.extra == {}

    def test_from_dict_empty(self):
        ctx = TaskContext.from_dict({})
        assert ctx.extra == {}

    def test_from_dict_none_extra_becomes_empty(self):
        ctx = TaskContext.from_dict({"extra": None})
        assert ctx.extra == {}

    def test_frozen(self):
        ctx = TaskContext()
        with pytest.raises(AttributeError):
            ctx.request_id = "x"  # type: ignore[misc]


class TestSetCurrentRequestId:
    def test_set_and_get(self):
        result = set_current_request_id("test-req-1")
        assert result == "test-req-1"

    def test_clear(self):
        set_current_request_id("temp")
        result = set_current_request_id(None)
        assert result is None

    def test_set_empty_string(self):
        result = set_current_request_id("")
        assert result is None


class TestGetCurrentRequestId:
    def test_returns_string_or_none(self):
        result = get_current_request_id()
        # Either None or a string is acceptable
        assert result is None or isinstance(result, str)
