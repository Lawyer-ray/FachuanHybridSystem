"""HTTP 客户端 - 封装 httpx，自动处理 JWT 认证和 token 刷新"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from . import config
from .identity import passthrough_authorization

logger = logging.getLogger(__name__)


class FachuanApiError(ToolError):
    """上游 REST 调用失败（非 2xx 或不可达）。

    继承 ``ToolError``：MCP 规范里「预期内的业务失败」应以
    ``is_error=True`` + **完整错误详情**回传给模型（HTTP 状态码、后端
    ``detail`` 字段级校验错误），模型据此自纠重试。此前抛裸
    ``RuntimeError``，SDK 会包成 ``UnexpectedToolError``——客户端只能看到
    ``"Error executing tool <name>"``，一行细节都不出网，模型无法自纠。
    ``agent_attachments._classify_http_error`` 按 ``"HTTP <status>:"`` 消息
    前缀分类，本类保持该消息格式不变。
    """


_MAX_OBTAIN_RETRIES = 3
_RETRY_BACKOFF = (1.0, 3.0, 5.0)


class FachuanClient:
    def __init__(self) -> None:
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        # trust_env=False: 绕过系统代理，直连后端（避免 macOS 代理工具对 localhost 返回 502）
        self._http = httpx.Client(base_url=config.BASE_URL, timeout=60, trust_env=False)

    def _obtain_token(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(_MAX_OBTAIN_RETRIES):
            try:
                resp = self._http.post(
                    "/token/pair",
                    json={"username": config.USERNAME, "password": config.PASSWORD},
                )
                resp.raise_for_status()
                data = resp.json()
                self._access_token = data["access"]
                self._refresh_token = data["refresh"]
                self._expires_at = time.time() + 270  # 提前 30s 刷新
                return
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status < 500:
                    raise  # 4xx 客户端错误直接抛
                logger.warning("token/pair 返回 %d，第 %d 次重试", status, attempt + 1)
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                logger.warning("token/pair 连接失败: %s，第 %d 次重试", exc, attempt + 1)
            if attempt < _MAX_OBTAIN_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
        raise last_exc  # type: ignore[misc]

    def _refresh(self) -> None:
        try:
            resp = self._http.post("/token/refresh", json={"refresh": self._refresh_token})
            resp.raise_for_status()
            self._access_token = resp.json()["access"]
            self._expires_at = time.time() + 270
        except Exception:
            self._obtain_token()

    def _ensure_token(self) -> None:
        with self._lock:
            if not self._access_token:
                self._obtain_token()
            elif time.time() >= self._expires_at:
                self._refresh()

    def _headers(self) -> dict[str, str]:
        # agent 场景（streamable-http）：优先透传请求头里「当前律师」的
        # Authorization，工具即以该律师身份调上游——归属过滤、权限、审计
        # 与本人登录一致；无透传（stdio/手工）才用服务账号。
        passthrough = passthrough_authorization()
        if passthrough:
            return {"Authorization": passthrough}
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def get(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.get(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def post(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.post(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def put(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.put(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def delete(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.delete(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def patch(self, path: str, **kwargs: Any) -> Any:
        resp = self._http.patch(path, headers=self._headers(), **kwargs)
        return self._handle(resp)

    def upload(
        self,
        path: str,
        files: dict[str, tuple[str, bytes, str]],
        data: dict[str, Any] | None = None,
    ) -> Any:
        """multipart/form-data 上传。files: {field: (filename, content, content_type)}"""
        resp = self._http.post(path, headers=self._headers(), files=files, data=data or {})
        return self._handle(resp)

    def download(self, path: str, *, method: str = "GET", **kwargs: Any) -> tuple[bytes, str, str]:
        """下载二进制内容，返回 (content_bytes, filename, content_type)。

        method: 默认 GET；生成类下载端点（诉讼文书 / 保全材料 / 授权材料等）
        是 POST，传 ``method="POST"``（可携带 ``json=`` 等请求体）。历史上
        这里写死 ``self._http.get(...)``，而 httpx 的 ``.get()`` 既不接受
        ``method`` 也不接受 ``json``——9 个传 ``method="POST"`` 的工具一调用
        就 TypeError，工具面静默全废（契约测试只校验意图，不校验这层）。
        """
        resp = self._http.request(method.upper(), path, headers=self._headers(), **kwargs)
        if not resp.is_success:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise FachuanApiError(f"HTTP {resp.status_code}: {detail}")
        content_type = resp.headers.get("content-type", "application/octet-stream")
        disposition = resp.headers.get("content-disposition", "")
        filename = "download"
        if disposition:
            # 尝试解析 filename*=UTF-8''... 或 filename="..."
            m = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
            if m:
                from urllib.parse import unquote

                filename = unquote(m.group(1))
            else:
                m2 = re.search(r'filename="?([^";]+)"?', disposition)
                if m2:
                    filename = m2.group(1).strip()
        return resp.content, filename, content_type

    @staticmethod
    def _handle(resp: httpx.Response) -> Any:
        if not resp.is_success:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise FachuanApiError(f"HTTP {resp.status_code}: {detail}")
        if resp.status_code == 204:
            return None
        return resp.json()


# 全局单例
client = FachuanClient()


def as_items(result: Any, *, default_page_size: int = 50) -> dict[str, Any]:
    """把 REST 返回归一化为 MCP 工具可声明的分页结构。

    .. deprecated::
        新工具请**直接声明后端真实返回类型**（``list[...]`` 或后端的分页
        schema），不要再经过本函数。MCP 框架会按返回注解做输出校验，
        声明与后端一致才是正确做法；在工具侧包一层假分页壳只会制造
        「声明与实现不符」的第二个源头。

    保留本函数仅为兼容尚未改造的工具。**任何“猜不出结构”的情况一律抛错**，
    不再返回空列表：

    - 旧实现把非 ``{items: [...]}`` 的 dict 静默变成
      ``{"items": [], "total": 0, "data": ...}``，于是后端结构一变（例如改成
      ``{"data": [...], "count": n}``），模型看到的就是「共 0 条」并如实
      回答「没有数据」——数据明明存在，用户却无从察觉。宁可抛错让调用方
      看到真实原因。

    Args:
        result: ``client.get`` 的原始返回（必须已是分页 dict 或裸数组）。
        default_page_size: 裸数组时填入的 ``page_size``。

    Returns:
        含 ``items`` 列表的 dict。

    Raises:
        TypeError: 返回结构既不是裸数组，也不含 ``items`` 列表。
    """
    if isinstance(result, list):
        return {"items": result, "total": len(result), "page": 1, "page_size": default_page_size}
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return result
    raise TypeError(
        "as_items 收到无法识别的返回结构（既不是数组，也不含 items 数组）: "
        f"{type(result).__name__} keys={sorted(result) if isinstance(result, dict) else 'n/a'}；"
        "工具应直接声明后端的真实返回类型，不要依赖 as_items 兜底"
    )
