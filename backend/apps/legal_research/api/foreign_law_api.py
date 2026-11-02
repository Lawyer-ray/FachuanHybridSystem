"""东盟域外法查明的只读 HTTP 端点。

把 ``mcp_server.tools.foreign_law.asean_law`` 的四个 MCP 工具暴露给前端：
此前只能由 AI 工具面调用，页面上点不了「核验法条」。

## 三条设计约束

1. **原样透出**：出参就是 MCP 工具的 dict，不在这里做二次判定或字段改写。
   演示/前端与 AI 看到同一份 ``section_text``，避免两套口径。
2. **阻塞调用不占事件循环**：MCP 工具内部是同步 HTTP + 登录（实测 verify
   6–7 秒，首次还要 BARLC 登录）。用 ``run_sync_isolated`` 丢进一次性线程，
   与 ``/law-verification/check`` 同路数。
3. **失败不返 5xx**：超时/线程异常折叠成 ``ok=false`` + ``reason``，与工具
   自身的 ``ok=false`` 同形状。前端要能区分「这条引用查不到」
   （``section_not_found``）与「没配 BARLC 账号」（``credential_missing``），
   500 会把两者压成同一个红叉，演示时也只会看到白屏。

## 为什么超时只短不长

``asean_law_verify`` 一次要跑「检索 → 取详情 → 拉正文 PDF → 切条款」，
实测 6.8 秒（含登录）；首次调用是本机实测值，不是上限。给 30 秒：
足够覆盖冷启动登录 + 一次完整核验，又不至于让前端按钮转圈到用户以为卡死。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ninja import Router

from apps.core.infrastructure.sync_async_bridge import run_sync_isolated
from apps.core.security.auth import JWTOrSessionAuth
from apps.legal_research.schemas.foreign_law_schemas import (
    ForeignLawCountriesOut,
    ForeignLawSearchOut,
    ForeignLawVerifyIn,
    ForeignLawVerifyOut,
)

logger = logging.getLogger(__name__)

router = Router(tags=["域外法查明"], auth=JWTOrSessionAuth())

# MCP 工具调用超时（秒）。verify 实测 6.8 秒（含 BARLC 登录），留足冷启动余量。
_VERIFY_TIMEOUT_SECONDS = 30.0
_SEARCH_TIMEOUT_SECONDS = 20.0
_COUNTRIES_TIMEOUT_SECONDS = 15.0


def _call_foreign_law_tool(
    tool_name: str,
    kwargs: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    """在线程里调用一个 asean_law 工具，超时/异常都折叠成 ``ok=false``。

    工具自身已把上游失败转成结构化结果（见该模块 docstring），所以这里只
    兜两件工具兜不住的事：超时，以及调用链路本身炸了。
    """
    from mcp_server.tools.foreign_law import asean_law_countries, asean_law_search, asean_law_verify

    # 给 dict 标注值类型：run_sync_isolated 的参数是 Callable[..., T]，而从
    # 未标注 dict 取出的函数会被推断成裸 `function` 而报 arg-type（mypy 门禁拦下）。
    # 三个工具签名各异（countries 无参 / search、verify 各自带关键字参数），
    # 这里只能按关键字转发，故用 Callable[..., dict[str, Any]] 而非精确签名。
    tools: dict[str, Callable[..., dict[str, Any]]] = {
        "asean_law_verify": asean_law_verify,
        "asean_law_search": asean_law_search,
        "asean_law_countries": asean_law_countries,
    }
    tool = tools[tool_name]

    try:
        return run_sync_isolated(tool, timeout=timeout, thread_name_prefix="foreign-law", **kwargs)
    except TimeoutError:
        logger.warning("域外法查明超时 tool=%s timeout=%ss", tool_name, timeout)
        return {
            "ok": False,
            "reason": "timeout",
            "detail": f"BARLC 数据库响应超时（{timeout:.0f} 秒），请稍后重试",
        }
    except Exception as exc:  # 网络/插件缺失等工具外部故障，折叠为结构化失败
        logger.exception("域外法查明调用失败 tool=%s", tool_name)
        return {"ok": False, "reason": "call_failed", "detail": str(exc)}


@router.post("/verify", response=ForeignLawVerifyOut)
def verify_foreign_law(request: Any, payload: ForeignLawVerifyIn) -> dict[str, Any]:  # pragma: no cover
    """核验一条域外法引用（``asean_law_verify``）。

    请求: ``{"law_name": "民商法典", "section_number": "538",
    "claim": "...", "country_code": "LAWCOUNTRYTG"}``
    响应: 含 ``verdict`` / ``section_text`` / ``reason`` 的工具原样结构，
    另附 ``trace``（调用轨迹）与 ``total_ms``（总耗时）。

    ``trace`` 由结果反推（见 services/foreign_law_trace.build_verify_trace）：
    MCP 工具内部是同步 HTTP，没有逐帧埋点；重建依据是「结果能说明什么」，
    所以不会出现过程全绿而最终失败。前端据此把接入→登录→检索→取正文→
    切条款→取原文逐步展示，让人看得出系统真的连了 BARLC。
    """
    import time

    from apps.legal_research.services.foreign_law_trace import build_verify_trace

    t0 = time.perf_counter()
    result = _call_foreign_law_tool(
        "asean_law_verify",
        {
            "law_name": payload.law_name,
            "section_number": payload.section_number,
            "claim": payload.claim,
            "country_code": payload.country_code,
        },
        timeout=_VERIFY_TIMEOUT_SECONDS,
    )
    total_ms = int((time.perf_counter() - t0) * 1000)

    result["total_ms"] = total_ms
    result["trace"] = build_verify_trace(
        law_name=payload.law_name,
        section_number=payload.section_number,
        country_code=payload.country_code,
        ok=bool(result.get("ok")),
        verdict=str(result.get("verdict") or ""),
        law_title=str(result.get("law_title") or ""),
        section_text=str(result.get("section_text") or ""),
        reason=str(result.get("reason") or ""),
        total_ms=total_ms,
    )
    return result


@router.get("/search", response=ForeignLawSearchOut)
def search_foreign_law(
    request: Any,
    keyword: str,
    country_code: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:  # pragma: no cover
    """按关键词检索东盟法律（``asean_law_search``）。

    响应: ``{"ok": true, "total": N, "hits": [{"sys_id", "title_cn", ...}]}``。
    """
    return _call_foreign_law_tool(
        "asean_law_search",
        {
            "keyword": keyword,
            "country_code": country_code,
            "page": max(1, int(page)),
            "page_size": min(60, max(1, int(page_size))),
        },
        timeout=_SEARCH_TIMEOUT_SECONDS,
    )


@router.get("/countries", response=ForeignLawCountriesOut)
def list_foreign_law_countries(request: Any) -> dict[str, Any]:  # pragma: no cover
    """列出可查明的国家/地区及其 ``country_code``（``asean_law_countries``）。"""
    return _call_foreign_law_tool("asean_law_countries", {}, timeout=_COUNTRIES_TIMEOUT_SECONDS)
