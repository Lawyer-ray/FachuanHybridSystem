"""opencode 端到端冒烟：**真实** opencode + **真实**共享 MCP + **真实**律师网关。

跑一轮完整链路并打印逐帧时间线：

    流式正文 → 一次工具调用 → 一次高危审批（批准）→ 一次高危审批（拒绝）→ 正常收尾

## 为什么这条脚本存在

单元测试（``tests/ci/unit/agent/test_opencode_backend.py``）把翻译、审批决策、
配置生成都钉住了，但它们都在打桩世界里跑。真正会出问题的是**接缝**：

- ACP 子进程到底能不能起来、能不能 `session/new` 挂上 430 个工具；
- 审批卡到底会不会从事件总线推到调用方（推不出去就是死锁）；
- ``done`` 会不会重复发（前端会显示两条收尾）；
- 拒绝之后工具到底有没有被执行。

这些只有真跑才知道。改动 ``opencode_backend`` / 审批链路 / MCP 工具面之后跑一遍。

## 用法

```bash
cd backend
PYTHONPATH=apiSystem:. .venv/bin/python devtools/e2e_opencode.py            # 跑完删会话
PYTHONPATH=apiSystem:. .venv/bin/python devtools/e2e_opencode.py --keep     # 保留会话供排查
```

前置：`opencode` 可执行文件在 PATH、共享 MCP 在 :8011、``LLMProvider`` 可用。
任何一项缺失脚本会**直接报错退出**（不静默跳过——跳过等于假绿）。

## 分级是脚本强制的，不是工具本身高危

真去调 ``delete_case`` 会把律师的数据删掉。所以本脚本把**只读**的
``fachuan_asean_law_countries`` 临时判成 ``HIGH``，好让真实的审批链路跑起来
（真实建 ``AgentApproval`` 记录、真实通过事件总线推帧、真实等
``decide_approval``）。除了分级函数，其余全是生产代码路径。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()



def _out(*parts: object) -> None:
    sys.stdout.write(" ".join(str(part) for part in parts) + chr(10))
    sys.stdout.flush()


def _err(*parts: object) -> None:
    sys.stderr.write(" ".join(str(part) for part in parts) + chr(10))
    sys.stderr.flush()

logger = logging.getLogger("e2e_opencode")

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

from apps.agent.backends import builtin
from apps.agent.models import AgentMessage, AgentRun, AgentSession
from apps.agent.pi.user_token import mint_user_access_token
from apps.agent.services import approval as approval_mod
from apps.agent.services.approval import decide_approval
from apps.agent.services.chat.stream import stream_chat
from apps.agent.services.session_service import create_session

#: 被脚本强制判成高危的只读工具（真调它不会改任何数据）。
PROBE_TOOL = "asean_law_countries"

#: 每轮的等待上限（秒）。网关慢的时候 90s 也可能不够，给足。
ROUND_TIMEOUT = 240.0


class Timeline:
    """逐帧时间线（相对毫秒 + 关键字段），失败时整段打出来最好用。"""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.rows: list[str] = []

    def add(self, frame: dict[str, Any]) -> None:
        elapsed = (time.monotonic() - self.started) * 1000
        kind = frame.get("type")
        detail = ""
        if kind == "delta":
            detail = (frame.get("content") or "")[:40].replace("\n", " ")
        elif kind == "tool_call":
            detail = f"{frame.get('name')} args={(frame.get('arguments') or '')[:40]}"
        elif kind == "tool_result":
            detail = f"{frame.get('name')} is_error={frame.get('is_error')} {(frame.get('result') or '')[:40]}"
        elif kind == "approval_request":
            level = frame.get("risk_level") or frame.get("level") or "-"
            detail = f"approval_id={frame.get('approval_id')} tool={frame.get('tool_name')} level={level}"
        elif kind == "usage":
            detail = f"in={frame.get('input_tokens')} out={frame.get('output_tokens')} cache={frame.get('cache_read_tokens')}"
        elif kind == "error":
            detail = f"{frame.get('code')} {frame.get('message')}"
        self.rows.append(f"{elapsed:8.0f}ms  {kind!s:16} {detail}")

    def dump(self, title: str) -> None:
        _err(f"\n──── {title} ────")
        for row in self.rows:
            _out(row)


def _force_high(name: str, args: dict[str, Any] | None = None) -> Any:
    """把探针工具临时判成 HIGH，其余仍走真实分级。"""
    if name.endswith(PROBE_TOOL):
        return approval_mod.RiskLevel.HIGH
    return _REAL_CLASSIFY(name, args)


_REAL_CLASSIFY = approval_mod.classify_risk


async def run_round(*, session: AgentSession, user_id: int, prompt: str, approve: bool) -> dict[str, Any]:
    """跑一轮，收到审批卡就按 ``approve`` 处方，返回可断言的统计。"""
    timeline = Timeline()
    answer = ""
    approvals: list[str] = []

    async def consume() -> dict[str, Any]:
        nonlocal answer
        stats = {"done": 0, "tool_call": 0, "tool_result": [], "error": None, "approval": 0}
        async for frame in stream_chat(session=session, user_message=prompt, user_id=user_id, agent_kind="opencode"):
            if not frame:
                continue
            timeline.add(frame)
            kind = frame.get("type")
            if kind == "done":
                stats["done"] += 1
            elif kind == "delta":
                answer += frame.get("content") or ""
            elif kind == "tool_call":
                stats["tool_call"] += 1
            elif kind == "tool_result":
                stats["tool_result"].append({"name": frame.get("name"), "is_error": frame.get("is_error")})
            elif kind == "error":
                stats["error"] = frame
            elif kind == "approval_request":
                stats["approval"] += 1
                approval_id = str(frame.get("approval_id") or "")
                approvals.append(approval_id)
                # 模拟前端点「批准 / 拒绝」——这一步走的是真实 API 背后的同一个服务函数
                ok = await decide_approval(approval_id, approve, user_id=user_id, reason="" if approve else "e2e 拒绝")
                _out(f"  ↳ 审批 {approval_id[:8]} → {'批准' if approve else '拒绝'}（decide={ok}）")
        return stats

    stats = await asyncio.wait_for(consume(), timeout=ROUND_TIMEOUT)
    stats["answer"] = answer
    stats["approvals"] = approvals
    timeline.dump(f"第 {'批准' if approve else '拒绝'} 轮")
    return stats


async def main(keep: bool) -> int:
    builtin.ensure_registered()
    user = await sync_to_async(lambda: get_user_model().objects.filter(is_active=True).order_by("id").first())()
    if user is None:
        _out("FAIL: 没有可用的律师账号")
        return 2
    token_ok = bool(await sync_to_async(mint_user_access_token)(user.id))
    if not token_ok:
        _err("FAIL: 铸不出律师 token（共享 MCP 会拒 401）")
        return 2

    session = await create_session(title="opencode e2e", user_id=user.id, agent_kind="opencode")
    _out(f"会话 {session.session_id}（agent_kind=opencode, user={user.id}）")

    approval_mod.classify_risk = _force_high
    failures: list[str] = []
    try:
        approve_stats = await run_round(
            session=session,
            user_id=user.id,
            prompt=f"请调用 fachuan_{PROBE_TOOL}，只回答国家数量。",
            approve=True,
        )
        reject_stats = await run_round(
            session=session,
            user_id=user.id,
            prompt=f"请再次调用 fachuan_{PROBE_TOOL}，只回答国家数量。",
            approve=False,
        )
    finally:
        approval_mod.classify_risk = _REAL_CLASSIFY

    # ── 断言 ────────────────────────────────────────────────────────────
    for label, stats, expect_ok in (("批准轮", approve_stats, True), ("拒绝轮", reject_stats, False)):
        if stats["done"] != 1:
            failures.append(f"{label}: done 应恰好 1 条，实际 {stats['done']}")
        if stats["error"]:
            failures.append(f"{label}: 出现 error 帧 {stats['error']}")
        if stats["approval"] != 1:
            failures.append(f"{label}: 审批卡应恰好 1 张，实际 {stats['approval']}")
        if stats["tool_call"] != 1:
            failures.append(f"{label}: tool_call 应恰好 1 条，实际 {stats['tool_call']}")
        if len(stats["tool_result"]) != 1:
            failures.append(f"{label}: tool_result 应恰好 1 条，实际 {len(stats['tool_result'])}")
        elif bool(stats["tool_result"][0]["is_error"]) is expect_ok:
            # 批准 → is_error 必须为 False；拒绝 → 必须为 True
            failures.append(
                f"{label}: tool_result.is_error={stats['tool_result'][0]['is_error']}，期望 {not expect_ok}"
            )
        if expect_ok and not stats["answer"].strip():
            failures.append(f"{label}: 批准后应有正文，实际为空")

    messages = await sync_to_async(lambda: list(AgentMessage.objects.filter(session=session).values("role")))()
    runs = await sync_to_async(
        lambda: list(AgentRun.objects.filter(session=session).values("agent_kind", "model", "status", "tool_calls"))
    )()
    if not any(m["role"] == "assistant" for m in messages):
        failures.append("落库: 没有 assistant 消息")
    if len(runs) != 2:
        failures.append(f"落库: AgentRun 应 2 条（每轮一条），实际 {len(runs)}")
    for run in runs:
        if run["agent_kind"] != "opencode":
            failures.append(f"落库: AgentRun.agent_kind={run['agent_kind']}")
        if not run["model"]:
            failures.append("落库: AgentRun.model 为空（成本归属会落空）")

    _out("\n== 落库 ==")
    _out("  messages:", [m["role"] for m in messages])
    _out("  runs:", runs)

    if not keep:
        deleted, _ = await sync_to_async(lambda: session.delete())()
        _out(f"已删除会话（{deleted} 行）")

    if failures:
        _out("\nFAIL:")
        for item in failures:
            _out("  -", item)
        return 1
    _out("\nOK: 端到端链路全部断言通过")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="opencode 端到端冒烟")
    parser.add_argument("--keep", action="store_true", help="保留会话与消息（默认跑完删除）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.keep)))
