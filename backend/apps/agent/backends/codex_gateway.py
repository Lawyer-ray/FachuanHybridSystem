"""给 codex 客户端用的 loopback 反向代理（绕开系统代理 + 注入 Bearer）。

## 为什么需要它（实测，不是推测）

codex 0.161 的 HTTP 客户端（reqwest）配置是
``system_proxy_fallback: true``（日志原文见 ``codex_backend`` 模块 docstring 的链接），
它会**读 macOS 系统代理**。律所网关是内网地址，系统代理（Clash）一劫持就是
``502 Bad Gateway``——而把同一份请求体经本模块的 loopback 代理转发就正常。

实测对照（2026-11-24，同一份 codex 请求体）：

| 路径 | 结果 |
|:-|:-|
| codex 直连 ``http://152.16.10.110:4000/v1/responses`` | ❌ 502（5 次重试后 turn.failed） |
| codex → 本代理 → 同一网关 | ✅ 正常出正文 |

注意：``NO_PROXY`` / 删 ``HTTPS_PROXY`` 环境变量**都不够**——codex 读的是系统级
代理配置，不是环境变量。所以只能从它的 ``base_url`` 上做文章，这就是本模块存在的
唯一理由（与 ``antigravity_gateway`` 是同一个套路）。

## 设计约束

- **只绑 127.0.0.1**，端口随机；每次运行一个随机 token 写在路径里
  （``/r/<token>/v1/responses``），token 不匹配一律 401。
- **key 不进 URL、不进日志**：token 只是路由凭据，真正的 ``Authorization``
  由本进程按 token 查表注入。
- **出网不带代理**：转发用 ``urllib`` 且显式 ``ProxyHandler({})``——这是整个模块
  存在的意义，绝不能继承宿主代理。
- **透传**：只补 ``Authorization``，请求体与响应（含 SSE 流）一律原样搬运，
  不改语义。codex 说 ``responses`` 协议，网关也支持 ``/v1/responses``（实测 200）。
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

#: 只允许转发到网关的这几条路径（防止被当成通用代理）。
ALLOWED_PREFIXES = ("/v1/responses", "/v1/chat/completions", "/v1/models")

#: 上游超时（秒）。responses 是流式，但 urllib 读的是整包，给足。
UPSTREAM_TIMEOUT = 300.0


@dataclass
class Lease:
    """一次运行的凭据：token → (网关 base_url, key)。"""

    token: str
    base_url: str
    api_key: str
    extra_headers: dict[str, str] = field(default_factory=dict)


class _Registry:
    """token → Lease（进程内表；进程退出即失效）。"""

    def __init__(self) -> None:
        self._leases: dict[str, Lease] = {}
        self._lock = threading.Lock()

    def add(self, lease: Lease) -> None:
        with self._lock:
            self._leases[lease.token] = lease

    def drop(self, token: str) -> None:
        with self._lock:
            self._leases.pop(token, None)

    def get(self, token: str) -> Lease | None:
        with self._lock:
            return self._leases.get(token)


_REGISTRY = _Registry()

#: 出网 opener：**显式清空代理**（ProxyHandler({})），否则等于没绕。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _split_path(path: str) -> tuple[str, str] | None:
    """``/r/<token>/v1/responses`` → ``(token, /v1/responses)``；形状不对返回 ``None``。"""
    if not path.startswith("/r/"):
        return None
    rest = path[len("/r/") :]
    token, _, tail = rest.partition("/")
    if not token or not tail:
        return None
    return token, "/" + tail


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # 默认实现往 stderr 打每条请求；这里降级到 debug，避免刷爆后端日志。
        logger.debug("codex proxy: %s", fmt % args if args else fmt)

    def _fail(self, code: int, message: str) -> None:
        body = json.dumps({"error": {"message": message}}).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        split = _split_path(self.path)
        if split is None:
            self._fail(404, "codex proxy: bad path")
            return
        token, tail = split
        lease = _REGISTRY.get(token)
        if lease is None:
            self._fail(401, "codex proxy: unknown token")
            return
        if not tail.startswith(ALLOWED_PREFIXES):
            self._fail(403, f"codex proxy: path not allowed {tail}")
            return
        length = int(self.headers.get("content-length") or 0)
        payload = self.rfile.read(length) if length else b""
        headers = {"content-type": "application/json", "authorization": f"Bearer {lease.api_key}"}
        headers.update(lease.extra_headers)
        base = lease.base_url.rstrip("/")
        # 网关的 base_url 通常已经带 ``/v1``，而 codex 发来的路径也以 ``/v1`` 开头——
        # 直接拼会得到 ``/v1/v1/responses``（实测 404）。只在这一处去重。
        if base.endswith("/v1") and tail.startswith("/v1"):
            base = base[: -len("/v1")]
        url = base + tail
        if not url.startswith(("http://", "https://")):
            self._fail(403, "codex proxy: scheme not allowed")
            return
        request = urllib.request.Request(url, data=payload, method="POST", headers=headers)  # noqa: S310 - scheme 已白名单
        try:
            with _OPENER.open(request, timeout=UPSTREAM_TIMEOUT) as upstream:
                body = upstream.read()
                self.send_response(upstream.status)
                for key, value in upstream.headers.items():
                    if key.lower() in {"transfer-encoding", "content-length", "connection", "content-encoding"}:
                        continue
                    self.send_header(key, value)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("content-type", exc.headers.get("content-type", "application/json"))
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("codex proxy 转发失败：%s", exc)
            self._fail(502, f"codex proxy upstream failed: {exc}")


class GatewayProxy:
    """一次性运行的代理实例（``with`` 进出，退出即关服务、清 token）。"""

    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lease: Lease | None = None

    def __enter__(self) -> GatewayProxy:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="codex-gateway", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._lease is not None:
            _REGISTRY.drop(self._lease.token)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("GatewayProxy 未启动")
        return int(self._server.server_address[1])

    def lease(self, *, base_url: str, api_key: str, extra_headers: dict[str, str] | None = None) -> str:
        """发一张凭据，返回 codex 应当使用的 base_url（``http://127.0.0.1:<port>/r/<token>/v1``）。"""
        token = secrets.token_urlsafe(16)
        lease = Lease(token=token, base_url=base_url, api_key=api_key, extra_headers=dict(extra_headers or {}))
        _REGISTRY.add(lease)
        self._lease = lease
        return f"http://127.0.0.1:{self.port}/r/{token}/v1"


__all__ = ["GatewayProxy", "Lease", "ALLOWED_PREFIXES"]
