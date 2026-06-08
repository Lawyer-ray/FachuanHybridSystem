"""Coverage tests for core.llm.prompts.base, core.api.pagination, core.models.querysets, core.http.streaming, core.infrastructure.asgi_lifespan."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestPromptManager:
    def test_register_and_get(self):
        from apps.core.llm.prompts.base import PromptManager, CodePromptTemplate
        PromptManager.clear()
        t = CodePromptTemplate(name="test_greet", template="Hello {name}", description="greet", variables=["name"])
        PromptManager.register(t)
        result = PromptManager.get("test_greet")
        assert result.name == "test_greet"

    def test_render(self):
        from apps.core.llm.prompts.base import PromptManager, CodePromptTemplate
        PromptManager.clear()
        t = CodePromptTemplate(name="test_render2", template="Hi {user} at {place}", description="", variables=["user", "place"])
        PromptManager.register(t)
        result = PromptManager.render("test_render2", user="Alice", place="Beijing")
        assert result == "Hi Alice at Beijing"

    def test_render_missing_vars(self):
        from apps.core.llm.prompts.base import PromptManager, CodePromptTemplate
        from apps.core.exceptions import ValidationException
        PromptManager.clear()
        t = CodePromptTemplate(name="test_miss", template="{a} {b}", description="", variables=["a", "b"])
        PromptManager.register(t)
        with pytest.raises(ValidationException):
            PromptManager.render("test_miss", a="x")

    def test_get_not_found(self):
        from apps.core.llm.prompts.base import PromptManager
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            PromptManager.get("nonexistent_prompt_xyz")

    def test_list_templates(self):
        from apps.core.llm.prompts.base import PromptManager, CodePromptTemplate
        PromptManager.clear()
        PromptManager.register(CodePromptTemplate(name="t1", template="a", description=""))
        PromptManager.register(CodePromptTemplate(name="t2", template="b", description=""))
        names = PromptManager.list_templates()
        assert "t1" in names and "t2" in names

    def test_clear(self):
        from apps.core.llm.prompts.base import PromptManager, CodePromptTemplate
        PromptManager.clear()
        PromptManager.register(CodePromptTemplate(name="t_clear", template="x", description=""))
        assert len(PromptManager.list_templates()) >= 1
        PromptManager.clear()
        assert len(PromptManager.list_templates()) == 0


class TestPaginateQueryset:
    def test_basic_pagination(self):
        from apps.core.api.pagination import paginate_queryset
        qs = MagicMock()
        qs.count.return_value = 100
        qs.__getitem__ = lambda self, key: list(range(key.start or 0, key.stop or 20))
        result = paginate_queryset(qs, page=1, page_size=20)
        assert result["total"] == 100
        assert result["page"] == 1
        assert result["page_size"] == 20
        assert result["total_pages"] == 5

    def test_page_less_than_1(self):
        from apps.core.api.pagination import paginate_queryset
        qs = MagicMock()
        qs.count.return_value = 10
        qs.__getitem__ = lambda self, key: []
        result = paginate_queryset(qs, page=0, page_size=5)
        assert result["page"] == 1

    def test_page_size_capped(self):
        from apps.core.api.pagination import paginate_queryset
        qs = MagicMock()
        qs.count.return_value = 10
        qs.__getitem__ = lambda self, key: []
        result = paginate_queryset(qs, page=1, page_size=999, max_page_size=50)
        assert result["page_size"] == 50


class TestLifespanApp:
    @pytest.mark.asyncio
    async def test_startup_complete(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp
        startup_fn = AsyncMock()
        app = LifespanApp(on_startup=startup_fn)
        messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
        idx = 0
        sent = []
        async def receive():
            nonlocal idx
            msg = messages[idx]
            idx += 1
            return msg
        async def send(msg):
            sent.append(msg)
        await app({}, receive, send)
        startup_fn.assert_awaited_once()
        assert sent[0]["type"] == "lifespan.startup.complete"
        assert sent[1]["type"] == "lifespan.shutdown.complete"

    @pytest.mark.asyncio
    async def test_startup_failure(self):
        from apps.core.infrastructure.asgi_lifespan import LifespanApp
        async def failing_startup():
            raise RuntimeError("boom")
        app = LifespanApp(on_startup=failing_startup)
        sent = []
        msg_idx = 0
        msgs = [{"type": "lifespan.startup"}]
        async def receive():
            nonlocal msg_idx
            m = msgs[msg_idx]
            msg_idx += 1
            return m
        async def send(msg):
            sent.append(msg)
        await app({}, receive, send)
        assert sent[0]["type"] == "lifespan.startup.failed"


class TestHttpErrorSummary:
    def test_summarize_json_error(self):
        from apps.core.llm.backends.http_error_summary import summarize_http_error_response
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {"content-type": "application/json", "x-request-id": "req-123"}
        resp.json.return_value = {"error": {"message": "bad request", "code": "INVALID"}}
        resp.text = '{"error": {"message": "bad request"}}'
        result = summarize_http_error_response(resp)
        assert result["status_code"] == 400
        assert result["upstream_request_id"] == "req-123"
        assert result["upstream_error_message"] == "bad request"

    def test_summarize_text_fallback(self):
        from apps.core.llm.backends.http_error_summary import summarize_http_error_response
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        resp.json.side_effect = ValueError("not json")
        resp.text = "Internal Server Error"
        result = summarize_http_error_response(resp)
        assert result["status_code"] == 500
        assert "upstream_error_text" in result

    def test_truncate(self):
        from apps.core.llm.backends.http_error_summary import _truncate
        assert _truncate("hello", 10) == "hello"
        assert _truncate("a" * 250, 200).endswith("...")
