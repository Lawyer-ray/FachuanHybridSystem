"""Unit tests for workbench.agents.http_client."""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from apps.workbench.agents.http_client import (
    LoopScopedTransport,
    reset_shared_http_client,
    shared_http_client,
    shared_transport,
)


class _RecordingTransport(httpx2.AsyncBaseTransport):
    """记录每次请求发生在哪个事件循环上，不发起真实网络调用。"""

    def __init__(self) -> None:
        self.loop_ids: list[int] = []
        self.closed = False

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self.loop_ids.append(id(asyncio.get_running_loop()))
        return httpx2.Response(200, json={"ok": True})

    async def aclose(self) -> None:
        self.closed = True


def _request(transport: LoopScopedTransport) -> None:
    """在**一个全新的**事件循环里向 transport 发一次请求。"""

    async def _call() -> None:
        request = httpx2.Request("GET", "http://gw.example/v1/models")
        response = await transport.handle_async_request(request)
        assert response.status_code == 200

    asyncio.run(_call())


@pytest.fixture
def recording() -> tuple[LoopScopedTransport, list[_RecordingTransport]]:
    created: list[_RecordingTransport] = []

    def factory() -> _RecordingTransport:
        inner = _RecordingTransport()
        created.append(inner)
        return inner

    return LoopScopedTransport(factory), created


class TestLoopScopedTransport:
    def test_reuses_one_pool_within_a_loop(self, recording: tuple[LoopScopedTransport, list[_RecordingTransport]]) -> None:
        transport, created = recording

        async def _twice() -> None:
            await transport.handle_async_request(httpx2.Request("GET", "http://gw.example/v1/models"))
            await transport.handle_async_request(httpx2.Request("GET", "http://gw.example/v1/models"))

        asyncio.run(_twice())

        assert len(created) == 1
        assert transport.pool_count == 1

    def test_isolates_pools_across_event_loops(
        self, recording: tuple[LoopScopedTransport, list[_RecordingTransport]]
    ) -> None:
        """跨循环必须换池：httpx 的连接池与首个使用它的事件循环绑定。"""
        transport, created = recording

        for _ in range(3):
            _request(transport)

        assert len(created) == 3
        assert transport.pool_count == 3
        assert len({id(inner) for inner in created}) == 3

    def test_each_loop_gets_its_own_transport_instance(
        self, recording: tuple[LoopScopedTransport, list[_RecordingTransport]]
    ) -> None:
        transport, created = recording

        _request(transport)
        _request(transport)

        assert created[0].loop_ids != created[1].loop_ids

    def test_aclose_closes_live_pools_and_skips_dead_loops(
        self, recording: tuple[LoopScopedTransport, list[_RecordingTransport]]
    ) -> None:
        transport, created = recording

        async def _use_and_close() -> None:
            await transport.handle_async_request(httpx2.Request("GET", "http://gw.example/v1/models"))
            await transport.aclose()

        asyncio.run(_use_and_close())

        assert created[0].closed is True
        assert transport.pool_count == 0

    def test_aclose_tolerates_pools_of_finished_loops(
        self, recording: tuple[LoopScopedTransport, list[_RecordingTransport]]
    ) -> None:
        transport, _created = recording

        _request(transport)  # 该循环随后结束

        async def _close_from_another_loop() -> None:
            await transport.aclose()

        asyncio.run(_close_from_another_loop())
        assert transport.pool_count == 0


class TestSharedHttpClient:
    def test_is_process_singleton(self) -> None:
        assert shared_http_client() is shared_http_client()

    def test_uses_loop_scoped_transport(self) -> None:
        assert isinstance(shared_transport(), LoopScopedTransport)

    def test_reset_drops_singleton(self) -> None:
        first = shared_http_client()
        reset_shared_http_client()
        try:
            assert shared_http_client() is not first
        finally:
            reset_shared_http_client()
