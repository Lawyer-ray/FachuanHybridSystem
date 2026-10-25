"""HTTP 客户端 - 封装 httpx，自动处理 JWT 认证和 token 刷新"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from . import config
from .identity import passthrough_authorization

logger = logging.getLogger(__name__)

#: 下载大小闸门（字节）。默认 15KB：宿主 pi 对工具输出按 20480 **字节**
#: 拦腰截断(2026-10-25 实测定案,见 fetch_url._BYTE_BUDGET)——base64 膨胀
#: 4/3 倍后,15KB 原始字节 ≈ 20KB 字符,已是完整送达模型的上限;再大就是
#: 「闸门放行 + pi 截断 = 模型收到损坏 base64」的静默腐败区间(旧默认 1MB
#: 只防挤爆上下文,没防截断腐败)。env 覆盖单位是 MB(可传小数)。
_MAX_MB = float(os.environ.get("FACHUAN_MCP_MAX_DOWNLOAD_MB", "0.0143") or "0.0143")
MAX_DOWNLOAD_BYTES = max(int(_MAX_MB * 1024 * 1024), 1024)

#: 巨型列表告警阈值：超过该条数的 list 响应记 warning（只告警不截断，
#: 见 ``_warn_bulk``）。300 是「模型一次能消化的列表规模」的经验上限。
_BULK_LIST_WARN_THRESHOLD = 300


def filename_of(resp: httpx.Response) -> str:
    """从 Content-Disposition 解析文件名（闸门报错用），解析不出返回空串。"""
    disposition = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
    if m:
        from urllib.parse import unquote

        return unquote(m.group(1))
    m2 = re.search(r'filename="?([^";]+)"?', disposition)
    return m2.group(1).strip() if m2 else ""


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


class FachuanTransportError(FachuanApiError):
    """暂时性传输故障（超时 / 断连 / 连接被拒）。

    与上游明确拒绝（4xx/5xx 响应）区分开：这类故障**没有证据表明请求
    未生效**，GET 重试是安全的；类型本身即「可重试」标记，调用方用
    isinstance 判定，不要解析错误文案。
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

    def _guard_transport(
        self, send: Callable[[], httpx.Response], method: str, path: str, *, timeout: float = 60.0
    ) -> httpx.Response:
        """执行请求，把 httpx 传输层异常翻译成模型可读的 FachuanApiError。

        超时/断连若直接冒泡，SDK 会包成 UnexpectedToolError——模型只看到
        "Error executing tool X"，不知道是暂时性故障、能不能重试。这里统一
        给出「可重试」的明确指引。
        """
        try:
            return send()
        except httpx.TimeoutException as exc:
            raise FachuanTransportError(
                f"上游超时（{timeout:.0f}s）: {method} {path}（{type(exc).__name__}）。"
                "暂时性故障可原样重试一次；若反复超时，请缩小请求范围或告知用户稍后再试。"
            ) from exc
        except httpx.TransportError as exc:
            raise FachuanTransportError(
                f"服务端不可达: {method} {path}（{type(exc).__name__}）。请稍后重试；若持续失败请告知用户联系管理员。"
            ) from exc

    def get(self, path: str, **kwargs: Any) -> Any:
        headers = self._headers()
        # GET 幂等：传输故障 / 502/503/504 自动重试一次（0.5s 退避）。只重试
        # 一次以免放大雪崩；非幂等方法（post/put/...）不自动重试。
        for attempt in (1, 2):
            try:
                resp = self._guard_transport(lambda: self._http.get(path, headers=headers, **kwargs), "GET", path)
            except FachuanTransportError:
                if attempt == 1:
                    time.sleep(0.5)
                    continue
                raise
            if resp.status_code in (502, 503, 504) and attempt == 1:
                time.sleep(0.5)
                continue
            break
        return self._warn_bulk(self._handle(resp), path)

    def post(self, path: str, **kwargs: Any) -> Any:
        resp = self._guard_transport(lambda: self._http.post(path, headers=self._headers(), **kwargs), "POST", path)
        return self._warn_bulk(self._handle(resp), path)

    def put(self, path: str, **kwargs: Any) -> Any:
        resp = self._guard_transport(lambda: self._http.put(path, headers=self._headers(), **kwargs), "PUT", path)
        return self._warn_bulk(self._handle(resp), path)

    def delete(self, path: str, **kwargs: Any) -> Any:
        resp = self._guard_transport(lambda: self._http.delete(path, headers=self._headers(), **kwargs), "DELETE", path)
        return self._handle(resp)

    def patch(self, path: str, **kwargs: Any) -> Any:
        resp = self._guard_transport(lambda: self._http.patch(path, headers=self._headers(), **kwargs), "PATCH", path)
        return self._warn_bulk(self._handle(resp), path)

    def upload(
        self,
        path: str,
        files: Mapping[str, tuple[str, bytes, str]] | list[tuple[str, tuple[str, bytes, str]]],
        data: dict[str, Any] | None = None,
    ) -> Any:
        """multipart/form-data 上传,返回 JSON(与 get/post 同走 _handle)。

        files 两种形态:``{field: (filename, content, content_type)}`` 单值
        dict,或同字段多文件的 ``[(field, (filename, content, type)), ...]``
        列表(httpx 原生都接受)。
        """
        resp = self._guard_transport(
            lambda: self._http.post(path, headers=self._headers(), files=files, data=data or {}),
            "POST",
            path,
        )
        return self._handle(resp)

    def download(self, path: str, *, method: str = "GET", **kwargs: Any) -> tuple[bytes, str, str]:
        """下载二进制内容，返回 (content_bytes, filename, content_type)。

        method: 默认 GET；生成类下载端点（诉讼文书 / 保全材料 / 授权材料等）
        是 POST，传 ``method="POST"``（可携带 ``json=`` 等请求体）。历史上
        这里写死 ``self._http.get(...)``，而 httpx 的 ``.get()`` 既不接受
        ``method`` 也不接受 ``json``——9 个传 ``method="POST"`` 的工具一调用
        就 TypeError，工具面静默全废（契约测试只校验意图，不校验这层）。

        大小闸门：超过 ``MAX_DOWNLOAD_BYTES``（默认 ~15KB，env
        ``FACHUAN_MCP_MAX_DOWNLOAD_MB`` 可调）直接报错。下载工具会把内容
        base64 塞进工具返回——宿主 pi 按约 20KB 字节截断工具输出,超限
        文件送达的是拦腰截断的损坏 base64;闸门在截断线**之前**拦下,
        给模型可执行的替代方案而不是腐败数据（列表投影防「条数多」，
        这里防「单件大」，是同一原则的两半）。
        """
        resp = self._guard_transport(
            lambda: self._http.request(method.upper(), path, headers=self._headers(), **kwargs),
            method.upper(),
            path,
        )
        if not resp.is_success:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise FachuanApiError(f"HTTP {resp.status_code}: {detail}")
        if len(resp.content) > MAX_DOWNLOAD_BYTES:
            raise FachuanApiError(
                f"文件过大: {filename_of(resp) or path} 约 {len(resp.content) / 1024:.0f}KB，"
                f"超过 {MAX_DOWNLOAD_BYTES / 1024:.0f}KB 上限（宿主对工具输出有约 20KB 截断线，"
                "再大送达的就是损坏的 base64）。"
                "替代方案：①请用户在前端页面直接下载该文件；②如需读取内容，"
                "改用文本提取类工具（extract-text）只取正文。"
            )
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
    def _warn_bulk(data: Any, path: str) -> Any:
        """巨型列表可见性护栏（2026-10-25 审计）。

        REST 端点的默认 limit 是**面向前端**设计的（clients 默认 1000、
        inbox 默认 500——前端表格做客户端分页没问题），但经 MCP 直达模型
        上下文就是几百 KB 的炸弹。这里**只告警不截断**（截断会让模型误以为
        看到了全量），把「哪个工具在灌无界列表」暴露到日志，提示维护者
        给工具加 limit 参数转发。
        """
        if isinstance(data, list) and len(data) > _BULK_LIST_WARN_THRESHOLD:
            logger.warning(
                "响应列表过大 path=%s items=%d——工具未做分页,模型上下文可能被挤爆;"
                "请给对应 MCP 工具加 limit 参数转发到 REST（客户端分页类端点尤其如此）",
                path,
                len(data),
            )
        return data

    @staticmethod
    def _handle(resp: httpx.Response) -> Any:
        if resp.status_code == 429:
            # REST 层限流专门回传 Retry-After 头(handlers.py 的
            # handle_rate_limit_exception),此前与普通错误混报会把它丢掉——
            # 模型不知道这是限流、等多久、立即重试只会继续 429。
            retry_after = resp.headers.get("retry-after", "")
            if retry_after.isdigit():
                wait_hint = f"建议等待 {retry_after} 秒后再试"
            else:
                wait_hint = "响应未说明等待时长,建议 30-60 秒后再试"
            try:
                where = f"{resp.request.method} {resp.request.url.path}"
            except RuntimeError:  # pragma: no cover - 未绑定请求的裸响应
                where = ""
            raise FachuanApiError(
                f"HTTP 429 触发限流: {where}。"
                f"{wait_hint}——这是速率限制不是故障,立即原样重试只会继续 429;"
                "高频列表/检索类操作请降低调用频率或改用更大分页。"
            )
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
