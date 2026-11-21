"""律所 LiteLLM 网关上的联网检索 MCP（百炼 WebSearch）——搜狗不可用时的兜底通道。

## 为什么接这个（2026-11-21 实测对比）

| | 搜狗免费 HTML | 律所百炼 WebSearch |
|---|---|---|
| 可用率 | 15%（生产库近 7 天：33 拦 / 6 成） | **15/15 = 100%** |
| 延迟 | 0.3s | 2–3s（首次冷启动 18s） |
| 来源权威性 | 高（gov.cn/法院/政务站为主） | **低**：148 条结果里 gov.cn 仅 9 条 |
| 发布日期 | 有（``cite-date``） | **无**（只有 title/url/hostname/snippet） |
| 摘要长度 | 200 字级 | **超长**：查「合同编通则解释全文」单条 47,964 字 |

所以它是**兜底**而不是替代：搜狗能给权威来源与日期，百炼能给可用性。
反过来排会把律师的证据来源换成百家号/头条/营销站，因此调用方（``web_search``）
必须做两件事——按来源权威性重排、并在无权威来源时显式声明（见
``web_search._authority_note``）。

## 配置（全部走环境变量，不写死在代码里）

``FACHUAN_FIRM_SEARCH_URL``
  流式 HTTP MCP 端点，形如 ``http://<litellm-host>:4000/WebSearch/mcp``。
``FACHUAN_FIRM_SEARCH_KEY``
  ``x-litellm-api-key`` 头的完整值（**含** ``Bearer `` 前缀）。
``FACHUAN_FIRM_SEARCH_TIMEOUT``
  单次调用超时秒数，默认 45（实测正常 2–3s，冷启动 18s；45 给冷启动留余量，
  又不至于把整轮对话拖死）。

任一缺失即视为未配置——该通道静默跳过（开发机没有网关时不该报错），
日志里也不打噪音。

## 协议细节（实测定案，别照抄官方客户端）

- 请求体是标准 JSON-RPC；**响应是 SSE**（``data: {...}`` 单行），不是
  ``application/json``——按 JSON 解析会直接炸。
- 工具名带服务前缀：``WebSearch-bailian_web_search``（LiteLLM 用
  ``<server>-<tool>`` 拼名）。写错不会报错，只会 404/空结果。
- 参数是 ``{"query": str, "count": int}``；``count`` 实测 10 稳定，超过也返回 10。
- 返回体：``{"status": 0, "pages": [{"title","url","hostname","snippet"}]}``。
  ``hostname`` 可能为 ``null``，``snippet`` 可能长到数万字——**必须截断**，
  否则单条结果就能把模型上下文刷爆。
- 已知坑：``court.gov.cn`` 的网页解析通道会挂 120 秒后 500（那是 ``webparser``
  的问题，与检索无关）。检索本身从未失败过。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ENV_URL = "FACHUAN_FIRM_SEARCH_URL"
ENV_KEY = "FACHUAN_FIRM_SEARCH_KEY"
ENV_TIMEOUT = "FACHUAN_FIRM_SEARCH_TIMEOUT"

#: 百炼检索工具在网关上的注册名（``<server>-<tool>``）。
TOOL_NAME = "WebSearch-bailian_web_search"

DEFAULT_TIMEOUT = 45.0


@dataclass(frozen=True)
class FirmSearchConfig:
    url: str
    key: str
    timeout: float


def load_config() -> FirmSearchConfig | None:
    """读取环境变量；URL 或 KEY 缺失时返回 ``None``（通道未启用）。

    每次调用都读环境变量而不是模块级常量：共享 MCP 是常驻进程，
    运维改 ``.env`` 后只需重启一次就能生效，不需要改代码里的默认值。
    """
    url = (os.getenv(ENV_URL) or "").strip()
    key = (os.getenv(ENV_KEY) or "").strip()
    if not url or not key:
        return None
    raw_timeout = (os.getenv(ENV_TIMEOUT) or "").strip()
    try:
        timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
    except ValueError:
        logger.warning("%s 不是数字（%r），回退默认 %ss", ENV_TIMEOUT, raw_timeout, DEFAULT_TIMEOUT)
        timeout = DEFAULT_TIMEOUT
    return FirmSearchConfig(url=url, key=key, timeout=max(5.0, min(timeout, 120.0)))


def _sse_payload(text: str) -> dict[str, Any] | None:
    """从 SSE 响应里取第一条 ``data:`` 的 JSON；不是 SSE 时按纯 JSON 解析。"""
    for line in text.splitlines():
        if line.startswith("data:"):
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _pages_from_result(result: dict[str, Any]) -> list[dict[str, Any]] | None:
    """``tools/call`` 结果 → ``pages`` 列表；结构不认识时返回 ``None``。"""
    if result.get("isError") is True:
        return None
    texts: list[str] = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(str(item.get("text") or ""))
    if not texts:
        return None
    for text in texts:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        pages = payload.get("pages")
        if isinstance(pages, list):
            return [p for p in pages if isinstance(p, dict)]
    return None


def search(query: str, count: int, config: FirmSearchConfig | None = None) -> dict[str, Any]:
    """调网关检索；返回 ``{"ok": bool, "reason": str, "pages": [...]}``。

    **不抛异常**：所有失败都折成 ``ok=False`` + 机器可读 reason，调用方
    （``web_search``）据此决定熔断时长与给模型的措辞。
    reason 取值：``timeout`` / ``network_error`` / ``http_error`` /
    ``rpc_error`` / ``bad_payload`` / ``empty`` / ``internal_error``。
    """
    cfg = config or load_config()
    if cfg is None:
        return {"ok": False, "reason": "not_configured", "pages": [], "detail": "兜底检索通道未配置"}

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": TOOL_NAME, "arguments": {"query": query, "count": count}},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "x-litellm-api-key": cfg.key,
    }

    try:
        # trust_env=False:与 fetch_url / 搜狗通道同口径——系统代理会把内网
        # 网关地址代理出去，表现为超时/502，极难排障（CLAUDE.md「内网地址
        # 必须绕过系统代理」同源）。
        with httpx.Client(timeout=cfg.timeout, follow_redirects=True, trust_env=False) as client:
            resp = client.post(cfg.url, headers=headers, json=payload)
    except httpx.TimeoutException:
        logger.warning("兜底检索超时（%ss）", cfg.timeout)
        return {"ok": False, "reason": "timeout", "pages": [], "detail": f"兜底检索超时（{cfg.timeout:.0f} 秒）"}
    except httpx.HTTPError as exc:
        logger.warning("兜底检索网络错误: %s", exc)
        return {
            "ok": False,
            "reason": "network_error",
            "pages": [],
            "detail": f"兜底检索连接失败（{type(exc).__name__}）",
        }

    if resp.status_code >= 400:
        logger.warning("兜底检索 HTTP %s", resp.status_code)
        return {
            "ok": False,
            "reason": "http_error",
            "pages": [],
            "detail": f"兜底检索服务返回 HTTP {resp.status_code}",
        }

    envelope = _sse_payload(resp.text)
    if envelope is None:
        return {"ok": False, "reason": "bad_payload", "pages": [], "detail": "兜底检索返回了无法解析的响应体"}

    if envelope.get("error"):
        detail = str(envelope["error"])[:160]
        return {"ok": False, "reason": "rpc_error", "pages": [], "detail": f"兜底检索 RPC 错误：{detail}"}

    result = envelope.get("result")
    if not isinstance(result, dict):
        return {"ok": False, "reason": "bad_payload", "pages": [], "detail": "兜底检索响应缺少 result 字段"}

    pages = _pages_from_result(result)
    if pages is None:
        return {"ok": False, "reason": "bad_payload", "pages": [], "detail": "兜底检索返回结构异常（无 pages）"}
    if not pages:
        return {"ok": False, "reason": "empty", "pages": [], "detail": "兜底检索未返回任何结果"}

    return {"ok": True, "reason": "", "pages": pages, "detail": ""}


__all__ = ["FirmSearchConfig", "TOOL_NAME", "load_config", "search"]
