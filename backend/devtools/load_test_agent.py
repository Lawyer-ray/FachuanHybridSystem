"""某个 agent 后端的高并发压测：N 路**全链路** `stream_chat` 并发。

验的是编排层的并发正确性，不是单轮功能（那个看 ``devtools/e2e_opencode.py``）：

1. **全部成功**：每路都要有正文、``done`` 恰好一条、没有 ``error`` 帧；
2. **帧归属**：同一路的所有帧 ``run_id`` 相同、``agent`` 与所选后端一致；
3. **无串话**：每路发一个独有暗号，回答里只准出现自己的暗号（别人出现 = 串话）；
4. **无历史污染**：每路一个独立会话，落库消息条数与轮次对得上；
5. **资源**：记录总耗时、峰值 RSS（按进程名采样）、失败率。

## 用法

```bash
cd backend
PYTHONPATH=apiSystem:. .venv/bin/python devtools/load_test_agent.py --kind opencode -n 8
PYTHONPATH=apiSystem:. .venv/bin/python devtools/load_test_agent.py --kind pi -n 8      # 基线对照
PYTHONPATH=apiSystem:. .venv/bin/python devtools/load_test_agent.py --kind opencode -n 16 --keep
```

输出一行 JSON（便于两次运行并列对比）+ 人读摘要。
"""

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import json
import logging
import os
import secrets
import subprocess
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

logger = logging.getLogger("load_test_agent")

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

from apps.agent.backends import builtin
from apps.agent.models import AgentMessage, AgentSession
from apps.agent.services.chat.stream import stream_chat
from apps.agent.services.session_service import create_session

#: 压测用的进程名片段（算 RSS 用）。opencode 是 ``opencode acp`` 子进程。
PROCESS_HINTS: dict[str, str] = {"opencode": "opencode acp", "pi": "pi"}

#: 单路等待上限（秒）。16 路并发时网关排队会明显变慢，给足。
LANE_TIMEOUT = 300.0


def peak_rss_mb(hint: str) -> float:
    """按命令行片段汇总 RSS（MB）。采样一次，用于「量级」而不是精确账。"""
    try:
        out = subprocess.run(["/bin/ps", "-axo", "rss=,command="], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return 0.0
    total = 0.0
    for line in out.splitlines():
        stripped = line.strip()
        if hint not in stripped:
            continue
        head = stripped.split(None, 1)[0]
        if head.isdigit():
            total += int(head) / 1024.0
    return round(total, 1)


async def run_lane(*, session: AgentSession, user_id: int, badge: str) -> dict[str, Any]:
    """跑一路：发独有暗号，收集帧归属与回答。"""
    result: dict[str, Any] = {
        "badge": badge,
        "ok": False,
        "done": 0,
        "errors": [],
        "answer": "",
        "run_ids": set(),
        "agents": set(),
        "frames": 0,
        "started": time.monotonic(),
    }
    prompt = f"暗号是 {badge}。请原样复述这个暗号，只回答暗号本身，不要调用任何工具。"
    try:
        async with asyncio.timeout(LANE_TIMEOUT):
            async for frame in stream_chat(session=session, user_message=prompt, user_id=user_id, agent_kind=session.agent_kind):
                if not frame:
                    continue
                result["frames"] += 1
                kind = frame.get("type")
                if kind == "done":
                    result["done"] += 1
                elif kind == "delta":
                    result["answer"] += frame.get("content") or ""
                elif kind == "error":
                    result["errors"].append(str(frame.get("code") or frame.get("message") or "")[:120])
                run_id = frame.get("run_id")
                if run_id:
                    result["run_ids"].add(str(run_id))
                agent = frame.get("agent")
                if agent:
                    result["agents"].add(str(agent))
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}"[:160])
    result["elapsed"] = round(time.monotonic() - result["started"], 2)
    _err(
        f"  lane {badge} 结束 elapsed={result['elapsed']}s frames={result['frames']} done={result['done']} "
        f"errors={result['errors'][:1]}",
    )
    result["ok"] = (
        not result["errors"]
        and result["done"] == 1
        and badge in result["answer"]
        and len(result["run_ids"]) == 1
        and result["agents"] == {session.agent_kind}
    )
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="agent 后端全链路并发压测")
    parser.add_argument("--kind", default="opencode", help="agent_kind，例如 opencode / pi")
    parser.add_argument("-n", "--lanes", type=int, default=8, help="并发路数")
    parser.add_argument("--keep", action="store_true", help="保留会话（默认删掉）")
    args = parser.parse_args()

    builtin.ensure_registered()
    user = await sync_to_async(lambda: get_user_model().objects.filter(is_active=True).order_by("id").first())()
    if user is None:
        _out("FAIL: 没有可用的律师账号")
        return 2

    # 卡住时（并发 / DB / 子进程）自动打栈，省得靠猜
    faulthandler.dump_traceback_later(150, repeat=True)
    badges = [f"BADGE{secrets.token_hex(3).upper()}" for _ in range(args.lanes)]
    sessions = [
        await create_session(title=f"load-{args.kind}-{i}", user_id=user.id, agent_kind=args.kind)
        for i in range(args.lanes)
    ]
    _out(f"kind={args.kind} lanes={args.lanes} 会话已建好，开始并发…")

    started = time.monotonic()
    # 采样任务**不能 await**：它是个 while True 的循环，只有被 cancel 才返回。
    # 直接把 `await rss_task` 写进 finally 会永久挂住（实测踩过：8 路全跑完、
    # 日志停在「开始并发」，看起来像后端卡死，实际是压测脚本自己等自己）。
    rss = {"peak": 0.0}
    rss_task = asyncio.create_task(_sample_rss(PROCESS_HINTS.get(args.kind, args.kind), rss))
    try:
        results = await asyncio.gather(
            *(run_lane(session=sessions[i], user_id=user.id, badge=badges[i]) for i in range(args.lanes))
        )
    finally:
        rss_task.cancel()
        try:
            await rss_task
        except asyncio.CancelledError:
            # 采样任务本来就是被 cancel 结束的：把它的 CancelledError 收干净，
            # 不要让它盖住压测本身的异常。
            pass
    peak = rss["peak"]
    total = round(time.monotonic() - started, 2)

    # ── 汇总 ────────────────────────────────────────────────────────────
    ok_count = sum(1 for r in results if r["ok"])
    cross_talk = [
        (r["badge"], other)
        for r in results
        for other in badges
        if other != r["badge"] and other in r["answer"]
    ]
    bad_run_ids = [r["badge"] for r in results if len(r["run_ids"]) != 1]
    dirty = [r["badge"] for r in results if r["agents"] != {args.kind}]

    messages = await sync_to_async(
        lambda: {
            s.session_id: AgentMessage.objects.filter(session=s).count()
            for s in sessions
        }
    )()

    summary = {
        "kind": args.kind,
        "lanes": args.lanes,
        "ok": ok_count,
        "failed": args.lanes - ok_count,
        "failure_rate": round((args.lanes - ok_count) / args.lanes, 3),
        "total_seconds": total,
        "per_lane_seconds": sorted(r["elapsed"] for r in results),
        "peak_process_rss_mb": peak,
        "cross_talk": cross_talk,
        "lanes_with_bad_run_id": bad_run_ids,
        "lanes_with_wrong_agent": dirty,
        "messages_per_session": sorted(messages.values()),
        "errors": [r["errors"] for r in results if r["errors"]],
    }
    _out("\n== 摘要 ==")
    for key, value in summary.items():
        _out(f"  {key}: {value}")
    _out("\n== JSON（两次运行并列对比用） ==")
    _out(json.dumps(summary, ensure_ascii=False))

    if not args.keep:
        for s in sessions:
            await sync_to_async(s.delete)()
        _out(f"已删除 {len(sessions)} 个压测会话")

    failed = bool(summary["failed"] or cross_talk or bad_run_ids or dirty)
    return 1 if failed else 0


async def _sample_rss(hint: str, holder: dict[str, float]) -> None:
    """并发期间反复采样，把峰值 RSS（MB）写进 ``holder``（由调用方 cancel）。"""
    while True:
        await asyncio.sleep(1.0)
        holder["peak"] = max(holder["peak"], await asyncio.to_thread(peak_rss_mb, hint))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
