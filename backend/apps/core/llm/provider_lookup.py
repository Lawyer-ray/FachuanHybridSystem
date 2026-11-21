"""模型 → 平台名（``LLMProvider.name``）的解析。

## 为什么需要它

成本归属必须能回答「钱花在哪个平台上」（`TECH-DEBT.md` ①）。而我们记流水的地方
（`LLMCallRecord` / `AgentRun`）只拿到**模型名**，拿不到自己连的是哪个平台——
同一个模型可能被多个平台提供，同一个平台也会被多个 backend 使用。

解析口径与真实发请求时**完全一致**：复用 ``openai_compatible._pick_provider``
（按模型白名单选、未命中回落优先级最高的启用平台），否则报表里的归属会和实际
路由分叉——那种分叉比没有数据更糟。

## 三条纪律

1. **绝不抛异常**：这是给统计用的旁路，不能因为查配置失败让调用记录写不进去；
   失败返回空串，报表显示「未知」。
2. **走服务层缓存**：``LLMProviderService.get_providers()`` 有 60s TTL + 代次校验，
   每次记录都调它不会带来一次新查询。**async 调用者用
   :func:`aresolve_provider_name`**（内部 ``await aget_providers()``）：同步访问器
   在事件循环里会抛 ``SynchronousOnlyOperation``，然后被吞成「无平台」。
3. **不猜**：解析不出来就是空串，不按「默认平台」硬塞——那会把别的平台的账算错。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _provider_name(provider: object | None) -> str:
    """平台配置 → 落库用的平台名（截断 50 字符）；无平台返回空串。"""
    return str(getattr(provider, "name", "") or "")[:50] if provider is not None else ""


def resolve_provider_name(model: str | None) -> str:
    """返回该模型所路由到的平台名；解析失败返回 ``""``（报表显示「未知」）。

    **仅限同步调用者**。async 上下文请用 :func:`aresolve_provider_name`——
    本函数读平台配置走同步 ORM，在事件循环里会抛 ``SynchronousOnlyOperation``。
    """
    try:
        from apps.core.llm.backends.openai_compatible import _pick_provider
        from apps.core.services.llm_provider_service import LLMProviderService

        provider = _pick_provider(LLMProviderService.get_providers(), (model or "").strip())
        return _provider_name(provider)
    except (AttributeError, ImportError, IndexError, KeyError, RuntimeError, TypeError, ValueError):
        # 统计旁路，永不抛：平台解析失败只影响「这条记录归到哪个平台」。
        # 用具体类型而不是宽捕获（宽异常捕获棘轮只许下调）：这里可能失败的原因
        # 就是「没配平台 / 模型名为空 / 配置对象形状变了 / 循环导入」这几类。
        logger.debug("解析模型所属平台失败（按未知处理）", exc_info=True)
        return ""


async def aresolve_provider_name(model: str | None) -> str:
    """异步版 :func:`resolve_provider_name`：走 ``await aget_providers()``。

    async 上下文（``_record_run`` / ``arecord_llm_call``）必须用这个：同步
    ``get_providers()`` 在事件循环里读库会抛 ``SynchronousOnlyOperation``，
    被 ``_load_from_db`` 吞成空列表后，成本归属静默变成「未知」。
    """
    try:
        from apps.core.llm.backends.openai_compatible import _pick_provider
        from apps.core.services.llm_provider_service import LLMProviderService

        provider = _pick_provider(await LLMProviderService.aget_providers(), (model or "").strip())
        return _provider_name(provider)
    except (AttributeError, ImportError, IndexError, KeyError, RuntimeError, TypeError, ValueError):
        # 与同步版同一纪律：统计旁路永不抛。
        logger.debug("异步解析模型所属平台失败（按未知处理）", exc_info=True)
        return ""


__all__ = ["aresolve_provider_name", "resolve_provider_name"]
