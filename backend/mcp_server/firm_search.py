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

## 地址与凭据从哪来：**复用 Admin 里的 AI 平台配置，不再配第二份密钥**

同一台 LiteLLM 网关既提供模型（``/v1``）也提供这两个 MCP（``/WebSearch/mcp``、
``/webparser/mcp``），用的是**同一把 key**。所以这里不引入 ``FACHUAN_FIRM_SEARCH_KEY``：

1. **默认**：走 ``LLMProviderService.get_providers()`` 里优先级最高的启用平台
   （与模型调用同一份配置、同一个选择口径），把它的 ``base_url`` 换成同主机的
   MCP 路径（``FACHUAN_FIRM_SEARCH_PATH``，默认 ``/WebSearch/mcp``）；
   **key 用该平台的全部 key，经 ``shared_pool`` 轮询**——与模型调用**共用同一个
   Key 池实例**（``shared_pool(provider.name, provider.api_keys,
   provider.concurrency_per_key, provider.key_model_scopes)`` 与
   ``openai_compatible._key_pool`` 逐参数一致）。不共用就会把「每 Key 并发上限」
   放大成两倍，直接顶穿网关限额（`key_pool.py` 的 docstring 有同款警告）。
2. **Admin 改完立刻生效**：平台配置由服务层缓存（TTL 5 分钟）+ 保存时失效；
   Key 池按「配置内容」寻址，改了 key 列表下一个请求就换池，不会用到过期配置。
3. **逃生口**：``FACHUAN_FIRM_SEARCH_URL`` + ``FACHUAN_FIRM_SEARCH_KEY`` 仍可用
   （指向别的网关 / 本机联调 / 单测注入）；只要两者齐备就优先于平台配置。

选平台的口径与模型调用一致：``FACHUAN_FIRM_SEARCH_MODEL_HINT`` 可指定一个模型名，
留空则取优先级最高的启用平台。

## 协议细节（实测定案，别照抄官方客户端）

- 请求体是标准 JSON-RPC；**响应是 SSE**（``data: {...}`` 单行），不是
  ``application/json``——按 JSON 解析会直接炸。
- 工具名带服务前缀：``WebSearch-bailian_web_search``（LiteLLM 用
  ``<server>-<tool>`` 拼名）。写错不会报错，只会 404/空结果。
- 参数是 ``{"query": str, "count": int}``；``count`` 实测 10 稳定，超过也返回 10。
- 返回体：``{"status": 0, "pages": [{"title","url","hostname","snippet"}]}``。
  ``hostname`` 可能为 ``null``，``snippet`` 可能长到数万字——**必须截断**，
  否则单条结果就能把模型上下文刷爆。
- 鉴权头是 ``x-litellm-api-key: Bearer <key>``（不是 ``Authorization``）。
- 已知坑：``court.gov.cn`` 走的是另一个 MCP（``webparser``），会挂 120 秒后 500；
  检索本身从未失败过。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

#: 显式覆盖（逃生口 / 本机联调 / 单测）。两者齐备才生效，优先于平台配置。
ENV_URL = "FACHUAN_FIRM_SEARCH_URL"
ENV_KEY = "FACHUAN_FIRM_SEARCH_KEY"
#: 单次调用超时秒数（正常 2–3s，首次冷启动实测 18s）。
ENV_TIMEOUT = "FACHUAN_FIRM_SEARCH_TIMEOUT"
#: MCP 检索路径（挂在网关同主机上；换网关版本时只改这一个值）。
ENV_PATH = "FACHUAN_FIRM_SEARCH_PATH"
#: 选平台的模型提示（留空 = 优先级最高的启用平台，与模型调用同口径）。
ENV_MODEL_HINT = "FACHUAN_FIRM_SEARCH_MODEL_HINT"

#: 百炼检索工具在网关上的注册名（``<server>-<tool>``）。
TOOL_NAME = "WebSearch-bailian_web_search"

#: LiteLLM 上 MCP 服务的默认挂载路径。
DEFAULT_MCP_PATH = "/WebSearch/mcp"

DEFAULT_TIMEOUT = 45.0

#: 鉴权/限流类状态码：换一把 key 重试一次，比整条通道冷却两分钟划算。
_RETRYABLE_STATUS = frozenset({401, 403, 429})


@dataclass(frozen=True)
class FirmSearchConfig:
    """一次检索所需的全部静态信息（不含「这一跳用哪把 key」）。"""

    url: str
    keys: tuple[str, ...]
    timeout: float
    provider: str = ""
    concurrency_per_key: int = 0
    #: ``{key: [model, ...]}``——只为构造与模型调用**同一个** Key 池实例
    scopes: Mapping[str, list[str]] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - 只为日志不泄密
        return (
            f"FirmSearchConfig(url={self.url!r}, keys=<{len(self.keys)}>, "
            f"provider={self.provider!r}, timeout={self.timeout!r})"
        )


def mcp_url_from_base_url(base_url: str, path: str = DEFAULT_MCP_PATH) -> str:
    """把平台 ``base_url`` 换成同主机上的 MCP 端点。

    ``http://gw:4000/v1`` → ``http://gw:4000/WebSearch/mcp``。

    **只换路径、不动主机端口**：MCP 与 ``/v1`` 在同一个 LiteLLM 实例上，
    改 host 或补默认端口都是猜。``base_url`` 缺 scheme/host 时返回空串
    （宁可不接，也不要拼出一个错误的地址去撞）。
    """
    parsed = urlparse((base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    suffix = (path or DEFAULT_MCP_PATH).strip() or DEFAULT_MCP_PATH
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    return f"{parsed.scheme}://{parsed.netloc}{suffix}"


def _timeout_from_env() -> float:
    raw = (os.getenv(ENV_TIMEOUT) or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        return max(5.0, min(float(raw), 120.0))
    except ValueError:
        logger.warning("%s 不是数字（%r），回退默认 %ss", ENV_TIMEOUT, raw, DEFAULT_TIMEOUT)
        return DEFAULT_TIMEOUT


def _strip_bearer(key: str) -> str:
    return key[len("Bearer ") :].strip() if key.lower().startswith("bearer ") else key.strip()


def _config_from_env() -> FirmSearchConfig | None:
    url = (os.getenv(ENV_URL) or "").strip()
    raw_key = (os.getenv(ENV_KEY) or "").strip()
    if not url or not raw_key:
        return None
    key = _strip_bearer(raw_key)
    if not key:
        return None
    return FirmSearchConfig(url=url, keys=(key,), timeout=_timeout_from_env(), provider="env-override")


def _active_providers() -> list[Any]:
    """取启用平台列表（与模型调用同一个服务层，含缓存与保存失效）。

    单独抽成函数是为了**可测**：单测直接替换它就能验证「URL 怎么拼、
    key 池怎么建」，不需要起数据库。
    """
    from apps.core.services.llm_provider_service import LLMProviderService

    return list(LLMProviderService.get_providers())


def _config_from_provider() -> FirmSearchConfig | None:
    """复用 Admin「AI 平台」里的 base_url + 全部 key（不再配第二份密钥）。"""
    try:
        from apps.core.llm.backends.openai_compatible import _pick_provider

        providers = _active_providers()
    except Exception:  # pragma: no cover - Django 未就绪时降级为「通道未配置」
        logger.debug("无法读取 AI 平台配置，兜底检索通道不可用", exc_info=True)
        return None
    if not providers:
        return None

    provider = _pick_provider(providers, (os.getenv(ENV_MODEL_HINT) or "").strip())
    if provider is None:
        return None

    url = mcp_url_from_base_url(str(getattr(provider, "base_url", "") or ""))
    if not url:
        logger.warning("平台「%s」的 base_url 无法拼出 MCP 端点，兜底检索通道跳过", getattr(provider, "name", "?"))
        return None

    keys = tuple(str(k) for k in (getattr(provider, "api_keys", None) or []) if str(k).strip())
    if not keys:
        logger.info("平台「%s」没有配置 API Key，兜底检索通道跳过", getattr(provider, "name", "?"))
        return None

    scopes = getattr(provider, "key_model_scopes", None) or {}
    return FirmSearchConfig(
        url=url,
        keys=keys,
        timeout=_timeout_from_env(),
        provider=str(getattr(provider, "name", "") or ""),
        concurrency_per_key=int(getattr(provider, "concurrency_per_key", 0) or 0),
        scopes={str(k): list(v) for k, v in dict(scopes).items()},
    )


def load_config() -> FirmSearchConfig | None:
    """解析本次检索的目标；返回 ``None`` 表示该通道未配置（调用方静默跳过）。

    顺序：显式环境变量覆盖 → Admin 平台配置。**每次调用都重新解析**（服务层
    自带缓存），这样 Admin 里换 key / 换平台在几秒内就生效，不需要重启 MCP。
    """
    return _config_from_env() or _config_from_provider()


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
    for text in texts:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
            return [p for p in payload["pages"] if isinstance(p, dict)]
    return None


def _key_pool(cfg: FirmSearchConfig) -> Any:
    """取**与模型调用同一个** Key 池实例（参数必须逐一对齐）。

    对齐口径见 ``apps/core/llm/backends/openai_compatible._key_pool``：
    ``shared_pool(provider.name, provider.api_keys, provider.concurrency_per_key,
    provider.key_model_scopes)``。任何参数不一致都会落成**另一个池**，于是
    「每 Key 并发上限」被放大、失败冷却也不再共享——这是静默的，不会报错。
    """
    from apps.core.llm.key_pool import shared_pool

    return shared_pool(
        cfg.provider,
        list(cfg.keys),
        cfg.concurrency_per_key,
        dict(cfg.scopes) or None,
    )


def _post(url: str, key: str, query: str, count: int, timeout: float) -> httpx.Response:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": TOOL_NAME, "arguments": {"query": query, "count": count}},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "x-litellm-api-key": f"Bearer {key}",
    }
    # trust_env=False：与 fetch_url / 搜狗通道同口径——系统代理会把内网网关
    # 代理出去，表现为超时/502，极难排障（CLAUDE.md「内网地址必须绕过系统代理」）。
    with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        return client.post(url, headers=headers, json=payload)


def search(query: str, count: int, config: FirmSearchConfig | None = None) -> dict[str, Any]:
    """调网关检索；返回 ``{"ok": bool, "reason": str, "pages": [...]}``。

    **不抛异常**：所有失败都折成 ``ok=False`` + 机器可读 reason，调用方
    （``web_search``）据此决定熔断时长与给模型的措辞。
    reason 取值：``not_configured`` / ``no_key`` / ``timeout`` / ``network_error`` /
    ``http_error`` / ``rpc_error`` / ``bad_payload`` / ``empty``。
    """
    cfg = config or load_config()
    if cfg is None:
        return {"ok": False, "reason": "not_configured", "pages": [], "detail": "兜底检索通道未配置"}
    if not cfg.keys:
        return {"ok": False, "reason": "no_key", "pages": [], "detail": "兜底检索通道没有可用 Key"}

    pool = _key_pool(cfg)
    last_error: dict[str, Any] = {"ok": False, "reason": "no_key", "pages": [], "detail": "兜底检索没有可用 Key"}

    # 最多两次：429/401/403 这类「这把 key 不行」换一把再试，其余错误不重试。
    for attempt in range(2):
        idx = pool.acquire("")
        if idx is None:
            break
        key = pool.keys[idx]
        try:
            resp = _post(cfg.url, key, query, count, cfg.timeout)
        except httpx.TimeoutException:
            pool.release(idx, success=False, model="")
            logger.warning("兜底检索超时（%ss）", cfg.timeout)
            last_error = {
                "ok": False,
                "reason": "timeout",
                "pages": [],
                "detail": f"兜底检索超时（{cfg.timeout:.0f} 秒）",
            }
            continue
        except httpx.HTTPError as exc:
            pool.release(idx, success=False, model="")
            logger.warning("兜底检索网络错误: %s", exc)
            last_error = {
                "ok": False,
                "reason": "network_error",
                "pages": [],
                "detail": f"兜底检索连接失败（{type(exc).__name__}）",
            }
            continue

        retryable = resp.status_code in _RETRYABLE_STATUS
        pool.release(idx, success=not retryable, model="")
        if resp.status_code >= 400:
            logger.warning("兜底检索 HTTP %s（平台 %s）", resp.status_code, cfg.provider or "?")
            last_error = {
                "ok": False,
                "reason": "http_error",
                "pages": [],
                "detail": f"兜底检索服务返回 HTTP {resp.status_code}",
            }
            if retryable and attempt == 0:
                continue
            return last_error

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
        return {"ok": True, "reason": "", "pages": pages, "detail": "", "provider": cfg.provider}

    return last_error


__all__ = [
    "DEFAULT_MCP_PATH",
    "ENV_KEY",
    "ENV_MODEL_HINT",
    "ENV_PATH",
    "ENV_TIMEOUT",
    "ENV_URL",
    "FirmSearchConfig",
    "TOOL_NAME",
    "load_config",
    "mcp_url_from_base_url",
    "search",
]
