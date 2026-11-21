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
   每次记录都调它不会带来一次新查询。
3. **不猜**：解析不出来就是空串，不按「默认平台」硬塞——那会把别的平台的账算错。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_provider_name(model: str | None) -> str:
    """返回该模型所路由到的平台名；解析失败返回 ``""``（报表显示「未知」）。"""
    try:
        from apps.core.llm.backends.openai_compatible import _pick_provider
        from apps.core.services.llm_provider_service import LLMProviderService

        provider = _pick_provider(LLMProviderService.get_providers(), (model or "").strip())
        return str(getattr(provider, "name", "") or "")[:50] if provider is not None else ""
    except Exception:  # pragma: no cover - 统计旁路，永不抛
        logger.debug("解析模型所属平台失败（按未知处理）", exc_info=True)
        return ""


__all__ = ["resolve_provider_name"]
