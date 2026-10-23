"""把 MCP 工具的 HTTP 调用桥到 Django test client（仅供集成测试）。

## 为什么需要

MCP 工具（``mcp_server/tools/**``）通过 ``mcp_server.client`` 走真实 HTTP 打到后端。
集成测试若把它整体 mock 掉，就测不出**端点与工具的契约**——本项目真实踩过两次：

1. T1→T4 契约漂移：``agent_api.py`` import 了不存在的 ``render_attachment_pages``
   → ``/pages`` 恒 503，而全 mock 的单测全绿；
2. 文字层页不回传 ``page.text``：端点只给 ``has_text_layer=True``，
   工具见「无 b64」就跳页 → 一份 1223 字的裁定书被判 ``parse_empty``。
   单测里 mocked 响应永远带非空 b64，因此永远测不到这条分支。

两者都是「端点按预期返回了，但返回里缺字段」。唯一能抓住它们的方式是
**让工具真的调用端点**，并且用 Django 的 test client 处理请求——它绕开
网络与鉴权，但仍走完整的中间件/路由/Ninja 序列化链路。

## 用法

    with patch_client(client):
        blocks = tool.read_agent_attachment(attachment_id=aid)

``client`` 必须是已 ``force_login`` 的 ``django.test.Client``；工具侧的
``_headers()``（含 JWT）在本桥接里被忽略，鉴权完全由 Django session 承担。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any
from unittest import mock

#: MCP 的 base_url 形如 ``http://127.0.0.1:8002/api/v1``，Django test client
#: 需要的是去掉该前缀后的站内路径。
_API_PREFIX = "/api/v1"


def _to_internal_path(path: str) -> str:
    """把工具侧使用的绝对/相对路径规范成站内路径（保留 query string）。"""
    raw = str(path or "")
    # 多种写法都见过：相对路径 "/agent/..."、带前缀 "/api/v1/agent/...",
    # 以及第三方调用方传入的完整 URL。统一压成站内路径。
    for marker in ("/api/v1",):
        idx = raw.find(marker)
        if idx >= 0:
            raw = raw[idx + len(marker) :]
            break
    if not raw.startswith("/"):
        raw = "/" + raw
    return _API_PREFIX + raw


class _TestClientBridge:
    """把 ``FachuanClient`` 的 get/post/upload/… 转发给 Django test client。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, path: str, **kwargs: Any) -> Any:
        params = kwargs.get("params") or {}
        return self._handle(self._client.get(_to_internal_path(path), data=params))

    def post(self, path: str, **kwargs: Any) -> Any:
        return self._handle(self._client.post(_to_internal_path(path), data=kwargs.get("json") or {}))

    def put(self, path: str, **kwargs: Any) -> Any:
        return self._handle(self._client.put(_to_internal_path(path), data=kwargs.get("json") or {}))

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self._handle(self._client.patch(_to_internal_path(path), data=kwargs.get("json") or {}))

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._handle(self._client.delete(_to_internal_path(path)))

    def upload(self, path: str, files: dict[str, tuple[str, bytes, str]], data: dict[str, Any] | None = None) -> Any:
        from django.core.files.uploadedfile import SimpleUploadedFile

        payload: dict[str, Any] = dict(data or {})
        for field, (filename, content, content_type) in files.items():
            payload[field] = SimpleUploadedFile(filename, content, content_type=content_type)
        return self._handle(self._client.post(_to_internal_path(path), payload))

    def download(self, path: str, **kwargs: Any) -> tuple[bytes, str, str]:
        resp = self._client.get(_to_internal_path(path))
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.content[:300]!r}")
        return (
            bytes(resp.content),
            resp.headers.get("content-disposition", "download"),
            resp.headers.get("content-type", "application/octet-stream"),
        )

    @staticmethod
    def _handle(resp: Any) -> Any:
        """与 ``FachuanClient._handle`` 对齐：2xx 返回 JSON，4xx/5xx 抛 RuntimeError。

        工具层靠异常里的 "HTTP 404"/"HTTP 403" 文本来映射 not_found/forbidden，
        因此这里必须保留该前缀格式。
        """
        if 200 <= resp.status_code < 300:
            if getattr(resp, "content", b"") and resp["Content-Type"].startswith("application/json"):
                return resp.json()
            return {}
        detail: Any
        try:
            detail = resp.json()
        except Exception:
            detail = resp.content[:300]
        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")


@contextlib.contextmanager
def patch_client(django_client: Any) -> Iterator[None]:
    """临时把 ``mcp_server.tools.core.agent_attachments.client`` 换成桥接对象。"""
    from mcp_server.tools.core import agent_attachments

    with mock.patch.object(agent_attachments, "client", _TestClientBridge(django_client)):
        yield
