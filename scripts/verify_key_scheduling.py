#!/usr/bin/env python
"""验收：三 agent 同答是否真的各拿一把不同的网关 key。

## 为什么需要这个脚本

网关对每把 key 限 ``max_parallel_requests = 3``（实测 429 + ``retry-after: 60``）。
「三 agent 用三把 key」是避免 429 的核心手段，但它**跨四层**：

    轮次分配(key_scheduler) → multi 分栏 → stream_chat(api_key) → RunContext
        → 后端取用 → 真正发到网关

任何一层漏了都**不报错**，只表现为「偶尔某栏卡 60 秒」——纯靠线上观察要很久
才发现，所以这里逐层验。

## 为什么不在 HTTP 层拦

pi 与 dsh 都是**子进程**，它们的请求不经过本进程的 httpx——在 HTTP 层拦只能看到
openai-agents（实测踩过：脚本报「只有 openai-agents 发了请求」，其实是另外两个
走子进程）。所以主判据取 ``stream_chat`` 入参（三个后端共用的必经点），
HTTP 层只作 openai-agents 的旁证。

用法::

    cd backend && DB_NAME=fachuan_dev PYTHONPATH=apiSystem:. \\
        .venv/bin/python ../scripts/verify_key_scheduling.py

退出码：0 通过 / 1 失败 / 2 环境缺失
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "apiSystem"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

EXIT_PASS, EXIT_FAIL, EXIT_ENV = 0, 1, 2


def _strip_proxy() -> None:
    """内网网关必须绕过系统代理（否则 Clash 会劫走请求 → 502 no body）。"""
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"


def _ok(label: str, detail: str = "") -> None:
    print(f"  ✅ {label}{(' — ' + detail) if detail else ''}")


def _bad(label: str, detail: str = "") -> None:
    print(f"  ❌ {label}{(' — ' + detail) if detail else ''}")


async def main() -> int:
    _strip_proxy()
    import django

    django.setup()

    from asgiref.sync import sync_to_async

    from apps.agent.backends.key_scheduler import fingerprint, get_key_scheduler
    from apps.agent.models import AgentSession
    from apps.agent.pi.model_config import _provider_keys_and_models
    from apps.core.models.llm_provider import LLMProvider

    def _load_keys() -> list[str]:
        prov = LLMProvider.objects.filter(enabled=True).first()
        if prov is None:
            return []
        keys, _scopes = _provider_keys_and_models(prov)
        return keys

    keys = await sync_to_async(_load_keys, thread_sensitive=True)()
    if not keys:
        print("环境缺失：没有启用中的 LLMProvider 或其 api_keys 为空")
        return EXIT_ENV

    print(f"网关 key 数={len(keys)} · 每 key 并发上限=3（网关侧）")
    print()

    # 在 multi 里拦截 stream_chat：三个后端共用的必经点。
    from apps.agent.services.chat import multi as multi_mod

    captured: list[tuple[str, str | None]] = []
    _orig_stream_chat = multi_mod.stream_chat

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append((str(kwargs.get("agent_kind") or ""), kwargs.get("api_key")))
        return _orig_stream_chat(*args, **kwargs)

    multi_mod.stream_chat = _spy  # type: ignore[assignment]

    from apps.agent.backends.builtin import ensure_registered
    from apps.agent.services.chat.multi import stream_multi

    ensure_registered()
    sched = get_key_scheduler()
    sched.reset()

    async def run_round(tag: str) -> list[str]:
        session = await AgentSession.objects.acreate(
            title=f"key-verify-{tag}", agent_kind="pi"
        )
        captured.clear()
        # **必须把整轮跑完**，不能取几个事件就 break。
        #
        # break 会让 pi / dsh 的异步生成器停在半途，事件循环收尾时对「仍在运行」
        # 的生成器 aclose 会抛 RuntimeError（实测见过
        # ``aclose(): asynchronous generator is already running``，并让本脚本
        # 误报一次失败）。整轮只有几秒，稳比快重要。
        async for _event in stream_multi(
            session=session,
            user_message="说三个字",
            user_id=1,
            specs=[
                {"kind": "pi", "model": "kimi-2.6"},
                {"kind": "dsh", "model": "glm53"},
                {"kind": "openai-agents", "model": "kimi-2.6(Anthropic)"},
            ],
        ):
            pass
        return [k for k, _ in captured]

    failures = 0
    try:
        print("[1/2] 一轮三 agent 同答 — 检查各栏拿到的 key …")
        await run_round("r1")
        per_column = {kind: key for kind, key in captured if kind}
        for kind, key in per_column.items():
            print(f"    {kind:16} {fingerprint(key or '')}")
        print()

        if len(per_column) < 3:
            _bad("有栏没经过 stream_chat", f"只看到 {sorted(per_column)}")
            failures += 1
        else:
            assigned = {k for k in per_column.values() if k}
            if len(assigned) != len(per_column):
                _bad(
                    "同一轮内有栏撞了同一把 key",
                    f"{len(per_column)} 栏只用了 {len(assigned)} 把",
                )
                failures += 1
            elif any(k is None for k in per_column.values()):
                _bad("有栏没拿到 key", "会退回后端的全局轮转（可能与他人撞车）")
                failures += 1
            else:
                _ok(
                    "三栏 key 互不相同",
                    f"{len(assigned)} 把：{sorted(fingerprint(k) for k in assigned)}",
                )

        # 分配器必须把占用还回去，否则下一轮会误判「全都满了」
        snap = sched.snapshot()
        if snap:
            _bad("租约没归还", f"残留在飞计数={snap}（下一轮会更容易 429）")
            failures += 1
        else:
            _ok("租约已全部归还", "在飞计数清零")

        print("\n[2/2] 再跑一轮 — 检查跨轮分散 …")
        round1 = {k for k in per_column.values() if k}
        await run_round("r2")
        round2 = {k for kind, k in captured if kind and k}
        if round2 and round2 != round1:
            _ok("跨轮 key 有分散", f"重叠 {len(round1 & round2)} 把")
        elif round2:
            _bad("两轮用了完全相同的 key 集合", "分配没有真正跨轮分散")
            failures += 1

        print()
        if failures == 0:
            print("✅ 全部通过：轮次级 key 分配已生效（三栏各用一把不同 key）")
            return EXIT_PASS
        print(f"❌ {failures} 项未通过")
        return EXIT_FAIL
    finally:
        multi_mod.stream_chat = _orig_stream_chat  # type: ignore[assignment]
        sched.reset()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
