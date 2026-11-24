"""后端矩阵 e2e + 多栏并发断言：一次跑完「每个 kind 单栏」与「N 栏同题并答」。

验的是**接缝**，不是单轮功能（单轮细节看 ``e2e_opencode.py``）：

A. **单栏矩阵**：每个可用 kind 各跑一轮真实对话（要求它调 ``fachuan_asean_law_countries``），
   记录正文 / tool_call / tool_result / usage（input、output、cache_read）/ 耗时 / 错误。
B. **多栏并发**：用 ``stream_multi`` 跑 2 栏与 3 栏，断言
   ``meta.agents`` 等于所选 kinds、**每栏 done 恰好一条**、每栏都有正文、无 error 帧、
   ``AgentMessage`` 落库条数 = 1 + 栏数、每栏帧的 ``agent`` 归属正确（无串栏）。
C. 输出：人读表格 + 一行 JSON（便于两次运行对比）。

## 用法

```bash
cd backend
PYTHONPATH=apiSystem:. .venv/bin/python devtools/e2e_agent_matrix.py --kinds pi,opencode,codex
PYTHONPATH=apiSystem:. .venv/bin/python devtools/e2e_agent_matrix.py --kinds pi,opencode --keep
```

前置：共享 MCP 在 :8011、``LLMProvider`` 可用、对应后端的二进制/依赖已装。
任何 kind 不可用都会进结果表（**不静默跳过**——跳过等于假绿）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

from apps.agent.backends import builtin, registry
from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat.multi import stream_multi
from apps.agent.services.chat.stream import stream_chat
from apps.agent.services.session_service import create_session

logger = logging.getLogger("e2e_agent_matrix")
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)


def _out(*parts: object) -> None:
    """输出一行到 stdout（走 sys.stdout：仓库禁止 ``print``，且 Django 已配 root logger）。"""
    sys.stdout.write(" ".join(str(part) for part in parts) + chr(10))
    sys.stdout.flush()


#: 单栏 e2e 的提示词：要求真的调一次只读工具（不会改任何数据）。
PROBE_PROMPT = "请调用 fachuan_asean_law_countries，只回答国家数量。"

#: 多栏用的短提示词（多栏是要看编排，不是看工具）。
MULTI_PROMPT = "只回答两个字：收到"

#: 单栏 / 多栏各自的等待上限（秒）。codex 首轮要把工具面全塞进 prompt，给足。
LANE_TIMEOUT = 600.0


def _empty_lane() -> dict[str, Any]:
    return {"text": "", "done": 0, "tool_call": 0, "tool_result": 0, "usage": [], "errors": [], "agents": set()}


def _absorb(lane: dict[str, Any], frame: dict[str, Any]) -> None:
    """把一帧记进该栏的统计。"""
    kind = frame.get("type")
    if kind == "delta":
        lane["text"] += frame.get("content") or ""
    elif kind == "done":
        lane["done"] += 1
    elif kind == "tool_call":
        lane["tool_call"] += 1
    elif kind == "tool_result":
        lane["tool_result"] += 1
    elif kind == "usage":
        lane["usage"].append(
            {
                "input": frame.get("input_tokens"),
                "output": frame.get("output_tokens"),
                "cache_read": frame.get("cache_read_tokens"),
            }
        )
    elif kind == "error":
        lane["errors"].append(str(frame.get("code") or frame.get("message"))[:120])
    agent = frame.get("agent")
    if agent:
        lane["agents"].add(str(agent))


async def run_single(*, kind: str, user_id: int, keep: bool) -> dict[str, Any]:
    """单栏：一个 kind 跑一轮带工具调用的真实对话。"""
    session = await create_session(title=f"matrix-{kind}", user_id=user_id, agent_kind=kind)
    lane = _empty_lane()
    started = time.monotonic()
    try:
        async with asyncio.timeout(LANE_TIMEOUT):
            async for frame in stream_chat(
                session=session, user_message=PROBE_PROMPT, user_id=user_id, agent_kind=kind
            ):
                if frame:
                    _absorb(lane, frame)
    except (TimeoutError, RuntimeError, ValueError, OSError) as exc:
        lane["errors"].append(f"{type(exc).__name__}: {exc}"[:160])
    result = {
        "kind": kind,
        "elapsed": round(time.monotonic() - started, 1),
        "done": lane["done"],
        "tool_call": lane["tool_call"],
        "tool_result": lane["tool_result"],
        "text": lane["text"].strip()[:40],
        "usage": lane["usage"],
        "errors": lane["errors"],
        # 单栏探针要求**真的调过工具**：只有正文 + done 不算通——codex 在 lite 工具面下
        # 会不调工具、直接答「当前会话没有这个工具」，看着像成功（实测踩过）。
        "ok": lane["done"] == 1 and not lane["errors"] and lane["tool_call"] >= 1,
    }
    if not keep:
        await sync_to_async(session.delete)()
    return result


async def run_multi(*, kinds: list[str], user_id: int, keep: bool) -> dict[str, Any]:
    """多栏：kinds 同题并答，断言编排契约。"""
    session = await create_session(title=f"matrix-multi-{len(kinds)}", user_id=user_id, agent_kind=kinds[0])
    lanes = {k: _empty_lane() for k in kinds}
    meta_agents: list[str] | None = None
    started = time.monotonic()
    try:
        async with asyncio.timeout(LANE_TIMEOUT):
            async for frame in stream_multi(session=session, user_message=MULTI_PROMPT, user_id=user_id, kinds=kinds):
                if not frame:
                    continue
                if frame.get("type") == "meta" and frame.get("agents"):
                    meta_agents = list(frame["agents"])
                agent = frame.get("agent")
                if agent in lanes:
                    _absorb(lanes[agent], frame)
    except (TimeoutError, RuntimeError, ValueError, OSError) as exc:
        for lane in lanes.values():
            lane["errors"].append(f"{type(exc).__name__}: {exc}"[:160])
    messages = await sync_to_async(
        lambda: list(AgentMessage.objects.filter(session=session).values_list("role", flat=True))
    )()

    failures: list[str] = []
    if meta_agents is None or set(meta_agents) != set(kinds):
        failures.append(f"meta.agents={meta_agents}，期望 {kinds}")
    for kind, lane in lanes.items():
        if lane["done"] != 1:
            failures.append(f"{kind}: done={lane['done']}，期望 1")
        if not lane["text"].strip():
            failures.append(f"{kind}: 没有正文")
        if lane["errors"]:
            failures.append(f"{kind}: {lane['errors']}")
        if lane["agents"] not in ({kind}, set()):
            failures.append(f"{kind}: 帧归属串栏 {sorted(lane['agents'])}")
    expected_messages = 1 + len(kinds)
    if len(messages) != expected_messages:
        failures.append(f"落库 {len(messages)} 条，期望 {expected_messages}（1 user + {len(kinds)} assistant）")

    summary = {
        "lanes": kinds,
        "elapsed": round(time.monotonic() - started, 1),
        "meta_agents": meta_agents,
        "per_lane": {
            k: {"done": v["done"], "text": v["text"].strip()[:20], "errors": v["errors"]} for k, v in lanes.items()
        },
        "messages": messages,
        "failures": failures,
        "ok": not failures,
    }
    if not keep:
        await sync_to_async(session.delete)()
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser(description="agent 后端矩阵 e2e + 多栏并发")
    parser.add_argument("--kinds", default="pi,opencode,codex", help="逗号分隔的 agent_kind")
    parser.add_argument("--keep", action="store_true", help="保留会话（默认删掉）")
    args = parser.parse_args()

    builtin.ensure_registered()
    available = set(registry.available_kinds())
    wanted = [k.strip() for k in args.kinds.split(",") if k.strip()]
    user = await sync_to_async(lambda: get_user_model().objects.filter(is_active=True).order_by("id").first())()
    if user is None:
        _out("FAIL: 没有可用的律师账号")
        return 2

    _out(f"可用后端: {sorted(available)}")
    _out(f"本轮要测: {wanted}")
    results: list[dict[str, Any]] = []
    for kind in wanted:
        if kind not in available:
            results.append({"kind": kind, "ok": False, "errors": ["未注册（依赖/二进制缺失）"]})
            _out(f"  {kind:12} SKIP 未注册")
            continue
        one = await run_single(kind=kind, user_id=user.id, keep=args.keep)
        results.append(one)
        _out(
            f"  {one['kind']:12} ok={one['ok']!s:5} {one['elapsed']:>6}s "
            f"tool={one['tool_call']}/{one['tool_result']} usage={one['usage']} text={one['text']!r} err={one['errors']}"
        )

    multis: list[dict[str, Any]] = []
    runnable = [r["kind"] for r in results if r.get("ok")]
    for size in (2, 3):
        lanes = runnable[:size]
        if len(lanes) < size:
            _out(f"  多栏 {size}: 跳过（可跑通的只有 {runnable}）")
            continue
        multi = await run_multi(kinds=lanes, user_id=user.id, keep=args.keep)
        multis.append(multi)
        _out(
            f"  多栏 {size} {lanes}: ok={multi['ok']} {multi['elapsed']}s meta={multi['meta_agents']} failures={multi['failures']}"
        )

    summary = {"single": results, "multi": multis}
    _out("")
    _out("== JSON ==")
    _out(json.dumps(summary, ensure_ascii=False))

    failed = [r["kind"] for r in results if not r.get("ok")] + [f"multi-{m['lanes']}" for m in multis if not m["ok"]]
    if failed:
        _out(f"FAIL: {failed}")
        return 1
    _out("OK: 矩阵与多栏断言全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
