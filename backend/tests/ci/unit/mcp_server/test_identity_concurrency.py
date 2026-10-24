"""并发身份隔离实证测试——共享 MCP 多会话交错调用不串号。

## 为什么需要这个测试

共享 MCP（streamable-http）是**单进程多用户**：所有律师的 agent 连同一个
server 进程，身份靠 ``identity.request_authorization`` ContextVar 按请求
透传。设计上（ASGI 每请求独立任务上下文 + anyio.to_thread 拷贝上下文进
工作线程）应当隔离，但这是安全关键路径——一旦串号就是跨用户数据泄漏
（A 律师的请求带着 B 律师的 Bearer 打到 REST）。

本测试用 16 线程 × 屏障强制交错，走**真实调用路径**
（``client.get`` → ``_headers`` → transport），实证无串号。
"""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest

from mcp_server.client import FachuanClient
from mcp_server.identity import RequestAuthMiddleware, passthrough_authorization, request_authorization

N_THREADS = 16
N_ROUNDS = 50


class TestRequestAuthMiddlewareIsolation:
    """第 48 轮线程测试直接设 ContextVar,绕过了 ASGI 中间件本体——
    这里补上:中间件在并发请求下必须把各自的 Authorization 写进
    各自请求任务上下文,互不污染;无 Authorization 头时保持默认(回退)。"""

    @pytest.fixture(autouse=True)
    def _reset_contextvar(self):
        token = request_authorization.set("")
        yield
        request_authorization.reset(token)

    @staticmethod
    def _scope(auth: str | None) -> dict[str, object]:
        headers = [] if auth is None else [(b"authorization", auth.encode("latin-1"))]
        return {"type": "http", "headers": headers}

    def test_concurrent_requests_isolated(self):
        """两个并发 ASGI 请求任务各持不同 Bearer,下游读到的一直是自己那一份。"""
        observed: list[tuple[str, str]] = []

        async def downstream(expected: str, tag: str) -> None:
            for _ in range(50):
                # 中间件 set 后本任务全程可见;与另一任务交错也不串
                observed.append((tag, passthrough_authorization()))
                await asyncio.sleep(0)

        async def run() -> None:
            async def noop_app(scope: object, receive: object, send: object) -> None:
                return

            mw = RequestAuthMiddleware(noop_app)

            async def call(expected: str, tag: str) -> None:
                # 每个请求用独立任务模拟 ASGI server 的任务模型
                await mw(self._scope(expected), None, None)  # type: ignore[arg-type]
                await downstream(expected, tag)

            await asyncio.gather(
                call("Bearer lawyer-a", "a"),
                call("Bearer lawyer-b", "b"),
            )

        asyncio.run(run())
        assert len(observed) == 100
        wrong = [(t, v) for t, v in observed if v != f"Bearer lawyer-{t}"]
        assert not wrong, f"中间件串号: {wrong[:5]}"

    def test_missing_or_invalid_header_keeps_default(self):
        """无 Authorization 头/非 Bearer 值 → ContextVar 保持默认空串(回退服务账号)。"""

        async def run() -> None:
            async def noop_app(scope: object, receive: object, send: object) -> None:
                return

            mw = RequestAuthMiddleware(noop_app)
            await mw(self._scope(None), None, None)
            assert request_authorization.get() == ""
            await mw(self._scope("Basic dXNlcjpwYXNz"), None, None)  # type: ignore[arg-type]
            assert passthrough_authorization() == "", "非 Bearer 方案必须拒绝透传"

        asyncio.run(run())


class TestConcurrentIdentityIsolation:
    @pytest.fixture(autouse=True)
    def _reset_contextvar(self):
        token = request_authorization.set("")  # 主线程兜底清空
        yield
        request_authorization.reset(token)

    def test_interleaved_calls_never_cross_users(self):
        """16 线程各自持不同 Bearer 并发交错调用，每次请求的
        Authorization 必须恰好是本线程的——不允许出现别的线程的
        token，也不允许静默回退服务账号。"""
        captured: list[tuple[int, str]] = []
        capture_lock = threading.Lock()

        def handler(request: httpx.Request) -> httpx.Response:
            auth = request.headers.get("authorization", "")
            if request.url.path.endswith("/token/pair"):
                return httpx.Response(200, json={"access": "svc-token", "refresh": "r"})
            thread_no = int(request.url.params["thread"])
            with capture_lock:
                captured.append((thread_no, auth))
            return httpx.Response(200, json={"ok": True})

        client = FachuanClient()
        client._http = httpx.Client(
            base_url="http://testserver", transport=httpx.MockTransport(handler), trust_env=False
        )

        barrier = threading.Barrier(N_THREADS)
        errors: list[str] = []

        def worker(i: int) -> None:
            # 模拟 anyio.to_thread 的工作线程：本线程上下文里设自己的 Bearer
            request_authorization.set(f"Bearer user-{i}")
            try:
                for _ in range(N_ROUNDS):
                    barrier.wait(timeout=10)  # 对齐后并发冲 _headers
                    data = client.get("/probe", params={"thread": i})
                    if data != {"ok": True}:
                        errors.append(f"thread{i}: 异常响应 {data!r}")
            except Exception as exc:  # pragma: no cover - 失败路径
                errors.append(f"thread{i}: {exc!r}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"并发调用报错: {errors[:5]}"
        # 每个线程的每次请求都带自己的 token,零串号、零回退
        assert len(captured) == N_THREADS * N_ROUNDS, "请求数与轮次不符"
        cross = [(i, auth) for i, auth in captured if auth != f"Bearer user-{i}"]
        assert not cross, f"身份串号/回退: {cross[:5]}（首 5 例）"

    def test_passthrough_threads_and_service_account_thread_coexist(self):
        """透传线程与服务账号回退线程并存时,回退线程不得捡到别人的透传值。"""
        captured: list[tuple[str, str]] = []
        capture_lock = threading.Lock()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/token/pair"):
                return httpx.Response(200, json={"access": "svc-token", "refresh": "r"})
            who = str(request.url.params["who"])
            with capture_lock:
                captured.append((who, request.headers.get("authorization", "")))
            return httpx.Response(200, json={})

        client = FachuanClient()
        client._http = httpx.Client(
            base_url="http://testserver", transport=httpx.MockTransport(handler), trust_env=False
        )

        barrier = threading.Barrier(2)
        errors: list[str] = []

        def passthrough_worker() -> None:
            request_authorization.set("Bearer lawyer-a")
            try:
                for _ in range(30):
                    barrier.wait(timeout=10)
                    client.get("/probe", params={"who": "a"})
            except Exception as exc:  # pragma: no cover
                errors.append(f"passthrough: {exc!r}")

        def fallback_worker() -> None:
            request_authorization.set("")  # stdio/无头场景:回退服务账号
            try:
                for _ in range(30):
                    barrier.wait(timeout=10)
                    client.get("/probe", params={"who": "fallback"})
            except Exception as exc:  # pragma: no cover
                errors.append(f"fallback: {exc!r}")

        t1 = threading.Thread(target=passthrough_worker)
        t2 = threading.Thread(target=fallback_worker)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, errors
        assert len(captured) == 60
        for who, auth in captured:
            if who == "a":
                assert auth == "Bearer lawyer-a", f"透传线程身份被篡改: {auth}"
            else:
                # 回退线程必须用服务账号 token,绝不能捡到 lawyer-a 的透传值
                assert auth == "Bearer svc-token", f"回退线程捡到他人身份: {auth}"
