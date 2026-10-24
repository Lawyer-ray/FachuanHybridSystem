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

import threading

import httpx
import pytest

from mcp_server.client import FachuanClient
from mcp_server.identity import request_authorization

N_THREADS = 16
N_ROUNDS = 50


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
        client._http = httpx.Client(  # noqa: SLF001 - 测试注入 mock transport
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
        client._http = httpx.Client(  # noqa: SLF001 - 测试注入 mock transport
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
