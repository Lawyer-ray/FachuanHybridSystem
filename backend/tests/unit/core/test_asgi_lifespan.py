import pytest

from apps.core.asgi_lifespan import LifespanApp


@pytest.mark.anyio
async def test_lifespan_calls_shutdown_hook():
    calls = {"shutdown": 0}

    async def on_shutdown():
        calls["shutdown"] += 1

    messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    app = LifespanApp(on_shutdown=on_shutdown)
    await app({"type": "lifespan"}, receive, send)

    assert calls["shutdown"] == 1
    assert [m["type"] for m in sent] == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
