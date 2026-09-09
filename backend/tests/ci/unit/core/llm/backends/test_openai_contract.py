"""openai_compatible 后端的契约测试。

用 httpx2.MockTransport 截获真实 openai SDK 的线上请求,锁定
chat / embed 两个核心契约:
- 请求契约:发往上游的 payload(model/messages/temperature/max_tokens) 与归一化行为;
- 响应契约:上游响应到 LLMResponse / 向量列表 的解析映射。

不依赖真实网络,便于在 CI 中稳定回归。
"""

from __future__ import annotations

import json

import httpx2
import openai
import pytest

from apps.core.llm.backends.base import BackendConfig
from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

CHAT_RESPONSE = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "合约要点如下", "reasoning_content": None},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
}

EMBED_RESPONSE = {
    "object": "list",
    "data": [
        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"object": "embedding", "index": 1, "embedding": [0.4, 0.5]},
    ],
    "model": "text-embedding-3-small",
    "usage": {"prompt_tokens": 3, "total_tokens": 3},
}


def _cfg(**kwargs) -> BackendConfig:
    defaults = {
        "name": "oai",
        "enabled": True,
        "priority": 1,
        "api_key": "sk-test",  # pragma: allowlist secret
        "base_url": "http://mocked.local/v1",
        "default_model": "gpt-4o",
        "embedding_model": "text-embedding-3-small",
    }
    defaults.update(kwargs)
    return BackendConfig(**defaults)


class _Recorder:
    """记录每次上游请求,并按 path 返回对应契约响应。"""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.url.path.endswith("/embeddings"):
            return httpx2.Response(200, json=EMBED_RESPONSE)
        return httpx2.Response(200, json=CHAT_RESPONSE)


def _sync_client(recorder: _Recorder) -> openai.OpenAI:
    transport = httpx2.MockTransport(recorder.handler)
    http_client = httpx2.Client(transport=transport, timeout=10)
    return openai.OpenAI(api_key="sk-test", base_url="http://mocked.local/v1", http_client=http_client)  # pragma: allowlist secret


def _async_client(recorder: _Recorder) -> openai.AsyncOpenAI:
    import httpx2

    transport = httpx2.MockTransport(recorder.handler)
    http_client = httpx2.AsyncClient(transport=transport, timeout=10)
    return openai.AsyncOpenAI(api_key="sk-test", base_url="http://mocked.local/v1", http_client=http_client)  # pragma: allowlist secret


def _patch_sync(monkeypatch, recorder: _Recorder) -> None:
    monkeypatch.setattr(
        OpenAICompatibleBackend, "_build_sync_client", lambda self, timeout_seconds=None: _sync_client(recorder)
    )


def _patch_async(monkeypatch, recorder: _Recorder) -> None:
    async def _build(self, timeout_seconds=None):
        return _async_client(recorder)

    monkeypatch.setattr(OpenAICompatibleBackend, "_build_async_client", _build)


class TestChatContract:
    def test_request_payload_and_response_mapping(self, monkeypatch):
        recorder = _Recorder()
        _patch_sync(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg())

        resp = backend.chat(
            messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "你好"}],
            temperature=0.2,
            max_tokens=64,
        )

        assert len(recorder.requests) == 1
        body = json.loads(recorder.requests[0].read())
        assert body["model"] == "gpt-4o"
        assert body["messages"] == [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "你好"},
        ]
        assert body["temperature"] == 0.2
        assert body["max_tokens"] == 64

        assert resp.content == "合约要点如下"
        assert resp.model == "gpt-4o"
        assert resp.prompt_tokens == 12
        assert resp.completion_tokens == 7
        assert resp.total_tokens == 19
        assert resp.backend == "openai_compatible"

    def test_messages_normalized(self, monkeypatch):
        recorder = _Recorder()
        _patch_sync(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg())

        backend.chat(messages=[{"role": "assistant", "content": "a"}, {"role": "unknown", "content": "u"}])

        body = json.loads(recorder.requests[0].read())
        assert body["messages"] == [
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "u"},  # 非法 role 归一化为 user
        ]
        # 未显式传 max_tokens 时不出现在 payload
        assert "max_tokens" not in body

    def test_model_default_and_overflow_role(self, monkeypatch):
        recorder = _Recorder()
        _patch_sync(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg(default_model="deepseek-chat"))

        backend.chat(messages=[{"content": "x"}])

        body = json.loads(recorder.requests[0].read())
        assert body["model"] == "deepseek-chat"
        assert body["messages"] == [{"role": "user", "content": "x"}]  # 缺省 role 归 user


class TestEmbedContract:
    def test_request_payload_and_vector_mapping(self, monkeypatch):
        recorder = _Recorder()
        _patch_sync(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg())

        vectors = backend.embed_texts(["甲", "乙"])

        assert len(recorder.requests) == 1
        body = json.loads(recorder.requests[0].read())
        assert body["model"] == "text-embedding-3-small"
        assert body["input"] == ["甲", "乙"]

        assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5]]

    def test_empty_input_skips_request(self, monkeypatch):
        recorder = _Recorder()
        _patch_sync(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg())

        assert backend.embed_texts([]) == []
        assert len(recorder.requests) == 0


class TestAsyncContract:
    @pytest.mark.asyncio
    async def test_achat(self, monkeypatch):
        recorder = _Recorder()
        _patch_async(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg())

        resp = await backend.achat(messages=[{"role": "user", "content": "hi"}], temperature=0.5)

        assert len(recorder.requests) == 1
        body = json.loads(recorder.requests[0].read())
        assert body["model"] == "gpt-4o"
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        assert body["temperature"] == 0.5
        assert resp.content == "合约要点如下"
        assert resp.total_tokens == 19

    @pytest.mark.asyncio
    async def test_aembed(self, monkeypatch):
        recorder = _Recorder()
        _patch_async(monkeypatch, recorder)
        backend = OpenAICompatibleBackend(config=_cfg())

        vectors = await backend.aembed_texts(["仅一"])
        body = json.loads(recorder.requests[0].read())
        assert body["input"] == ["仅一"]
        assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5]]
