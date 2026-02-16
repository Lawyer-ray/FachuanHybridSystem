import pytest

from apps.core.llm.backends import LLMResponse
from apps.core.llm.service import LLMService


def test_llm_service_uses_default_backend_when_backend_not_specified(monkeypatch):
    service = LLMService(default_backend="ollama")
    called = {}

    def fake_execute(*, operation, backend, fallback):
        called["backend"] = backend
        called["fallback"] = fallback
        return LLMResponse(
            content="ok",
            model="m",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            duration_ms=1.0,
            backend=backend,
        )

    monkeypatch.setattr(service, "_fallback_policy", type("X", (), {"execute": staticmethod(fake_execute)})())
    resp = service.complete("hi")
    assert resp.backend == "ollama"
    assert called["backend"] == "ollama"
    assert called["fallback"] is True


@pytest.mark.anyio
async def test_llm_service_uses_default_backend_for_async(monkeypatch):
    service = LLMService(default_backend="moonshot")
    called = {}

    async def fake_execute_async(*, operation, backend, fallback):
        called["backend"] = backend
        called["fallback"] = fallback
        return LLMResponse(
            content="ok",
            model="m",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            duration_ms=1.0,
            backend=backend,
        )

    monkeypatch.setattr(
        service, "_fallback_policy", type("X", (), {"execute_async": staticmethod(fake_execute_async)})()
    )
    resp = await service.achat(messages=[{"role": "user", "content": "hi"}])
    assert resp.backend == "moonshot"
    assert called["backend"] == "moonshot"
    assert called["fallback"] is True
