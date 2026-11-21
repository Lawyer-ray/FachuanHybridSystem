"""给 Antigravity harness 补 ``Authorization`` 的 loopback 反向代理。

## 为什么需要这个模块（这不是「多一层架构」，是 SDK 的硬缺口）

Antigravity SDK 的本地 harness（Go 二进制 ``bin/localharness``）只有两条取模型的通道：

1. **Gemini / Vertex 原生**（``LocalAgentConfig`` + ``GeminiAPIEndpoint``）：能带
   ``api_key`` 与 ``http_headers``，但说的是 ``:generateContent`` 协议；
2. **OpenAI 兼容**（``LocalOpenAIAgentConfig`` + ``base_url``）：只有 ``base_url``
   一个字段，**没有任何 api_key / headers 入口**。

而律所网关（``LLMProvider.base_url``）只讲 OpenAI 兼容协议、且强制 Bearer
（实测：``/v1beta/models/...:generateContent`` 一律 404，``/chat/completions``
带 Bearer 才 200）。两条通道的交集是空集：

- 走 1 → 协议对不上（网关没有 Gemini 原生路由）；
- 走 2 → **wire 上根本没有 auth 头**（实测：``Authorization`` / ``api-key`` /
  ``OPENAI_API_KEY`` 环境变量三种都试过，harness 一律不发）。

所以本模块在**本进程内**起一个只绑 ``127.0.0.1`` 的小反向代理：harness 把请求发到
``http://127.0.0.1:<port>/r/<token><网关路径>``，代理补上 ``Authorization: Bearer
<key>`` 后转发到真正的网关。key 不写进 URL、不进日志，只存在于内存表里。

## 顺便补的第二件事：思考参数

harness 的 OpenAI 兼容通道**也不发**思考开关（实测请求体只有
``max_completion_tokens / messages / model / stream / stream_options /
tool_choice / tools``）。而网关（LiteLLM → vLLM）的思考需要两个字段：

```json
{"chat_template_kwargs": {"thinking": true}, "reasoning_effort": "max"}
```

不补的后果不是报错，而是**这一栏回答明显变浅**、且 `thoughts_token_count` 恒为 0
——与其它三个后端用同一个模型、同一个平台开关却「差一截」，没有任何提示。
所以注册路由时把本轮该注入的字段一并带上（由后端按
``LLMProvider.enable_thinking`` + 模型能力算好），转发时**只补缺不覆盖**。

## 红线一：按 run 分 key，不共享

:8011 与网关两头都是「每把 key 有并发上限」。编排层按轮次给每一栏分配了互不相同的
key（``key_scheduler``），后端必须照着用（见 ``base.py`` 的 ``RunContext.api_key``）。
所以代理的路由键是**一次运行一个随机 token**，token → 该轮的 key；一次运行结束即
注销。共享一个全局 key 会让四栏并答撞回同一把 key（表现为「某一栏卡 60 秒」）。

## 红线二：key 不进 URL、不进日志

URL 里只放随机 token（``uuid4().hex``），真 key 留在进程内存。日志只写 token 前缀与
上游 origin —— 代理是**每条请求都过**的热路径，一行 ``logger.debug`` 里带上 key
就等于把凭证写进 ``logs/api.log``。

## 红线三：内网网关必须绕开系统代理

本机 ``http_proxy`` 指向本地 Clash，转发内网网关会得到「502 no body」（同一教训见
``dsh_config.without_proxy_env`` 与 ``docs/harness/backend/agent-runtime.md``）。
出网客户端一律 ``trust_env=False``；harness 子进程侧再补 ``NO_PROXY``（见
``antigravity_backend`` 的 ``env``）。

## 生命周期

- 惰性启动：第一次要跑 antigravity 时才起（进程启动期不占端口、不影响其它后端）；
- 端口 0 由内核分配，绑定后从 ``uvicorn`` 的监听 socket 读回真实端口；
- 单例挂在模块级，按事件循环复用（gunicorn 每个 worker 一个进程、一个循环）；
- ``stop()`` 只给测试与进程收尾用，正常路径不需要关。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

#: 路由前缀：``/r/<token>/...``。带前缀而不是把 token 放在子域/端口，是为了让
#: 「一条 route 一个 key」在 URL 上可读、且不与上游自己的路径（``/v1/...``）混淆。
ROUTE_PREFIX = "/r/"

#: 泄漏兜底：一次运行的 token 正常会显式注销；崩溃/取消路径没走到时靠它过期。
#: 取 30 分钟（远大于单轮对话），只防无界增长，不参与正常回收。
ROUTE_TTL_SECONDS = 1800.0

#: 上游透传的响应头白名单。
#:
#: **``retry-after`` 必须在里面**：harness 会解析它并据此决定 429/5xx 的重试退避
#: （SDK CHANGELOG 0.1.24 的 "parses HTTP Retry-After headers"）；不透传等于把
#: 网关的退避建议丢掉，表现为「限流后立刻再撞一次」。
_PASS_RESPONSE_HEADERS = ("content-type", "retry-after", "x-request-id")


def normalize_request_body(body: bytes, extra_body: dict[str, Any] | None = None) -> bytes:
    """转发前做最小请求体归一（**只修协议不兼容，不改语义**）。

    实测（律所网关 = LiteLLM → vLLM 0.33）：harness 在本轮**没有任何工具**时
    仍然发 ``tool_choice: "auto"``，vLLM 直接 400：

        When using `tool_choice`, `tools` must be set. (parameter=tool_choice)

    这条组合完全合法于 OpenAI 官方端点（那里 ``tool_choice`` 没有工具时被忽略），
    所以不能指望 SDK 或网关某一侧修；在代理这一层把「有 tool_choice 但 tools
    为空」的字段摘掉即可。**只在真的为空时摘**——有工具时不碰，避免把网关的
    ``required`` / 指定函数之类的语义改掉。

    解析失败（非 JSON / 空体）一律原样返回：代理不是校验层，宁可让上游自己报错，
    也不要把一个能跑的请求体改坏。

    Args:
        body: harness 发来的原始请求体。
        extra_body: 本轮要补的字段（思考开关等）。**只补缺、不覆盖**：harness
            将来自己带上这些字段时，以它为准——那时本函数的注入就该自动失效，
            而不是把模型侧显式选择改掉。
    """
    if not body:
        return body
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return body
    if not isinstance(payload, dict):
        return body
    changed = False
    tools = payload.get("tools")
    if "tool_choice" in payload and (not isinstance(tools, list) or not tools):
        payload.pop("tool_choice", None)
        changed = True
    for key, value in (extra_body or {}).items():
        if key in payload:
            continue
        payload[key] = value
        changed = True
    if not changed:
        return body
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class GatewayLease:
    """一次运行的代理租约：harness 该用的地址 + 注销用的 token。"""

    #: 随机路由 token（**不是** key）。注销与日志标识都用它。
    token: str
    #: 交给 harness 的 base_url（形如 ``http://127.0.0.1:<port>/r/<token>/v1``）。
    base_url: str


@dataclass(frozen=True)
class _Route:
    """一条运行的路由：打哪个上游、用哪把 key。"""

    base_url: str
    #: 真实 key。**不得进日志**——需要标识时只用 :attr:`token` 前缀。
    api_key: str
    #: 本轮要补进请求体的字段（思考开关等）；空 = 不补。
    extra_body: dict[str, Any]
    created_at: float


class LoopbackGateway:
    """进程内反向代理：``/r/<token>/<path>`` → ``<网关 origin><path>`` + Bearer。"""

    def __init__(self) -> None:
        self._routes: dict[str, _Route] = {}
        self._server: Any = None
        self._task: asyncio.Task[Any] | None = None
        self._start_lock = asyncio.Lock()
        self._port: int = 0
        #: 服务所在的事件循环。uvicorn 的 server 绑在起它的那个循环上，换循环
        #: （pytest 每个用例一个新循环）必须重新起，否则新循环里 await 一个旧循环
        #: 的任务会直接挂死。
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── 对外 API ─────────────────────────────────────────────────────────

    async def register(self, *, base_url: str, api_key: str, extra_body: dict[str, Any] | None = None) -> GatewayLease:
        """登记一次运行，返回 harness 该用的 loopback 地址与注销 token。

        Args:
            base_url: 网关的 OpenAI 兼容地址（可含路径，如 ``http://host:4000/v1``）。
            api_key: 本轮该用的 key（编排层已按栏分配好；为空则本模块拒绝登记，
                让后端走「无可用平台」的错误路径，而不是发一批 401 出去）。
            extra_body: 本轮要补进请求体的字段（思考开关等，见模块 docstring）。
                ``None`` / 空 = 原样转发。

        Returns:
            租约：``base_url`` 的路径部分原样保留（harness 在它后面接
            ``/chat/completions``），``token`` 用于 :meth:`unregister`。
        """
        if not base_url or not api_key:
            raise ValueError("loopback 网关需要 base_url 与 api_key")
        await self.ensure_started()
        parts = urlsplit(base_url)
        path = parts.path.rstrip("/")
        token = uuid.uuid4().hex
        self._routes[token] = _Route(
            base_url=base_url, api_key=api_key, extra_body=dict(extra_body or {}), created_at=time.monotonic()
        )
        self._sweep()
        return GatewayLease(token=token, base_url=f"http://127.0.0.1:{self._port}{ROUTE_PREFIX}{token}{path}")

    def unregister(self, token: str) -> None:
        """注销一条路由（幂等）。token 从 :meth:`register` 返回的 URL 里取。"""
        self._routes.pop(token, None)

    async def ensure_started(self) -> None:
        """惰性启动（幂等）。同一个事件循环里只起一次。"""
        loop = asyncio.get_running_loop()
        if self._task is not None and not self._task.done() and self._loop is loop:
            return
        async with self._start_lock:
            if self._task is not None and not self._task.done() and self._loop is loop:
                return
            await self._start(loop)

    async def stop(self) -> None:
        """停掉服务（测试收尾 / 进程优雅退出用）。"""
        server = self._server
        task = self._task
        self._server = None
        self._task = None
        self._loop = None
        self._port = 0
        self._routes.clear()
        if server is not None:
            server.should_exit = True
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    @property
    def port(self) -> int:
        """当前监听端口（未启动为 0）。诊断与测试用。"""
        return self._port

    def route_count(self) -> int:
        """当前存活的路由条数（诊断用；泄漏会让它只增不减）。"""
        return len(self._routes)

    # ── 内部 ─────────────────────────────────────────────────────────────

    def _sweep(self) -> None:
        """清掉超过 TTL 的路由（崩溃/取消没走到 unregister 时的兜底）。"""
        now = time.monotonic()
        stale = [tok for tok, route in self._routes.items() if now - route.created_at > ROUTE_TTL_SECONDS]
        for tok in stale:
            self._routes.pop(tok, None)
        if stale:
            logger.warning("loopback 网关清掉 %d 条过期路由（超 %ss 未注销）", len(stale), int(ROUTE_TTL_SECONDS))

    async def _start(self, loop: asyncio.AbstractEventLoop) -> None:
        # 延迟 import：uvicorn / starlette 只在真的要跑 antigravity 时才付这份开销，
        # 也避免「没装可选后端」的部署因为本模块 import 失败而整进程起不来。
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route as StarletteRoute

        app = Starlette(routes=[StarletteRoute("/{path:path}", self._handle, methods=["POST", "GET"])])
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            access_log=False,
            lifespan="off",
            # 代理是纯转发，不读 body 上限也不做超时：SSE 长连接必须能一直流。
            timeout_keep_alive=30,
        )
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve(), name="antigravity-loopback-gateway")
        for _ in range(500):  # 最多等 5s；绑定 127.0.0.1 的 0 端口是毫秒级
            if server.started or task.done():
                break
            await asyncio.sleep(0.01)
        if not server.started:
            task.cancel()
            raise RuntimeError("antigravity loopback 网关启动失败（无法绑定 127.0.0.1）")

        self._server = server
        self._task = task
        self._loop = loop
        # 端口 0 由内核分配：从 uvicorn 的监听 socket 读回真实端口（uvicorn 没有
        # 提供「取端口」的公开接口，``servers[0].sockets[0]`` 是它的稳定形状）。
        self._port = int(server.servers[0].sockets[0].getsockname()[1])
        logger.info("antigravity loopback 网关已启动: 127.0.0.1:%s", self._port)

    async def _handle(self, request: Any) -> Any:
        """把 ``/r/<token>/<path>`` 转发到上游，补 auth 头，原样流回响应。"""
        import httpx
        from starlette.responses import Response, StreamingResponse

        path = request.url.path
        if not path.startswith(ROUTE_PREFIX):
            return Response("not found", status_code=404)
        token, _, upstream_path = path[len(ROUTE_PREFIX) :].partition("/")
        route = self._routes.get(token)
        if route is None:
            # 明确 401 而不是 404：404 会被 harness 当成「端点不存在」而放弃，
            # 401 才有可能让它把错误交给模型/用户（与上游的鉴权失败同语义）。
            return Response("unknown gateway route", status_code=401)
        if not upstream_path.startswith("/"):
            upstream_path = "/" + upstream_path

        # 路径拼接口径：harness 在「给的 base_url」后面追加 ``/chat/completions``，
        # 而 base_url 已经带着上游的路径（``/r/<token>/v1``）。所以转发时**只保留
        # 上游 origin**，路径用 harness 发来的那一段——再拼一次 ``provider.path``
        # 会得到 ``/v1/v1/chat/completions``（实测 404）。
        parts = urlsplit(route.base_url)
        upstream = f"{parts.scheme}://{parts.netloc}{upstream_path}"
        if request.url.query:
            upstream = f"{upstream}?{request.url.query}"

        body = normalize_request_body(await request.body(), route.extra_body)
        headers = {
            "authorization": f"Bearer {route.api_key}",
            "content-type": request.headers.get("content-type", "application/json"),
            "accept": request.headers.get("accept", "*/*"),
        }
        # SSE 长连接：httpx 的全局超时必须关掉，否则 5s 后就断流；代理自身
        # 不做超时，超时判定交给网关与 harness（harness 会解析 Retry-After 重试）。
        # S113（ruff）/ B113（bandit）：同一个决定要两套扫描器各标一次——
        # 只写 noqa 时 bandit 仍会把 SSE 长连接的超时当成「忘了设超时」拦下来。
        client = httpx.AsyncClient(trust_env=False, timeout=None)  # noqa: S113  # nosec B113
        upstream_request = client.build_request(request.method, upstream, headers=headers, content=body)
        try:
            upstream_response = await client.send(upstream_request, stream=True)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            # 只接「传输层 / URL 非法」这三类：上游不可达统一转 502，由后端的
            # ``_wrap_error`` 映射成 UNAVAILABLE。不接宽异常——代理不是兜底层，
            # 真正的程序 bug 应该带着堆栈冒到日志里，而不是被这里压成 502。
            await client.aclose()
            logger.warning("antigravity loopback 转发失败 route=%s… err=%s", token[:8], type(exc).__name__)
            return Response("upstream unreachable", status_code=502)

        passthrough = {
            name: upstream_response.headers[name]
            for name in _PASS_RESPONSE_HEADERS
            if name in upstream_response.headers
        }

        async def body_stream() -> Any:
            try:
                async for chunk in upstream_response.aiter_raw():
                    yield chunk
            finally:
                await upstream_response.aclose()
                await client.aclose()

        return StreamingResponse(
            body_stream(),
            status_code=upstream_response.status_code,
            headers=passthrough,
        )


_GATEWAY: LoopbackGateway | None = None


def get_loopback_gateway() -> LoopbackGateway:
    """进程内单例（测试可用 ``reset_loopback_gateway()`` 换新实例）。"""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = LoopbackGateway()
    return _GATEWAY


def reset_loopback_gateway() -> None:
    """丢弃当前单例（仅测试；不关服务，调用方负责先 ``await stop()``）。"""
    global _GATEWAY
    _GATEWAY = None
