"""真机验收：MCP 服务端审批闸门（入口 B）完整往返。

跑在真实 :8011（共享 MCP）+ 真实 :8002（Django）+ 真实库上，验证四件事：

1. 高危工具先弹审批，批准后**真的执行**（拿到工具自己的业务错误，而不是闸门文案）；
2. 批准后的**第一次重试**由本轮台账覆盖（客户端 200s 超时后重试直接放行）；
3. 一次批准只放行一次：第三次同参数会重新进入审批（新单落库）；
4. 审批记录可审计（status / dedupe_key 落库）。

用法（先 `make mcp` 让共享 MCP 加载当前分支代码）：

    cd backend && PYTHONPATH=apiSystem:. DB_NAME=fachuan_dev \
        .venv/bin/python ../scripts/verify_approval_gate.py

前置：共享 MCP 在 :8011、Django 在 :8002、`agent` 迁移已应用（`manage.py migrate agent`）。
脚本自清理：跑完删除它创建的会话（审批记录随 CASCADE 清掉）。

注意：为了不改业务数据，工具用的是 `delete_case` + **不存在的** case_id——
批准后工具会返回 404「案件不存在」，正好证明「闸门放行 + 工具真执行」。
"""


from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack

sys.path.insert(0, "apiSystem")
sys.path.insert(0, ".")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
import django  # noqa: E402

django.setup()

import httpx  # noqa: E402
import httpx2  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

MCP_URL = os.environ.get("FACHUAN_MCP_ENDPOINT", "http://127.0.0.1:8011/mcp")
API = os.environ.get("FACHUAN_API_BASE", "http://127.0.0.1:8002/api/v1")
USER_ID = int(os.environ.get("ACCEPT_USER_ID", "1"))
TOOL = "delete_case"
ARGS = {"case_id": 987654321}
GATE_MARK = "需要律师人工批准"


def text_of(result) -> str:
    return "\n".join(getattr(b, "text", "") or "" for b in (getattr(result, "content", []) or []))


async def main() -> int:
    from apps.agent.models import AgentApproval, AgentSession
    from apps.agent.services.chat.env import mint_user_token

    token = await mint_user_token(USER_ID)
    session = await AgentSession.objects.acreate(title="真机验收-审批闸门", origin="chat", user_id=USER_ID)
    sid = str(session.session_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Fachuan-Session": sid,
        "X-Fachuan-Tool-Tier": "full",
    }
    results: list[tuple[str, bool, str]] = []
    holder: dict = {}

    async def auto_approve() -> None:
        """模拟律师点同意：等卡片落库 → 立刻批准。"""
        async with httpx.AsyncClient(timeout=5.0) as c:
            for _ in range(300):
                try:
                    r = await c.get(f"{API}/agent/approvals/pending", headers={"Authorization": f"Bearer {token}"})
                    if r.status_code == 200:
                        for row in r.json():
                            if str(row.get("session_id")) == sid:
                                holder["id"] = row["approval_id"]
                                d = await c.post(
                                    f"{API}/agent/approval/{holder['id']}/decide",
                                    headers={"Authorization": f"Bearer {token}"},
                                    json={"approved": True, "reason": "真机验收：批准一次"},
                                )
                                holder["decide"] = f"{d.status_code}"
                                return
                except Exception:
                    pass
                await asyncio.sleep(0.1)

    async with AsyncExitStack() as stack:
        hc = await stack.enter_async_context(httpx2.AsyncClient(headers=headers, timeout=200.0))
        read, write = await stack.enter_async_context(streamable_http_client(MCP_URL, http_client=hc))
        mcp = await stack.enter_async_context(ClientSession(read, write))
        await mcp.initialize()
        print(f"[1] 会话 {sid} · 工具 {TOOL}{ARGS}")

        approver = asyncio.ensure_future(auto_approve())
        first_text = text_of(await mcp.call_tool(TOOL, ARGS))
        await asyncio.wait_for(approver, timeout=30)
        print(f"[2] 第一次：审批单 {holder.get('id')} · decide={holder.get('decide')}")
        print("    " + first_text.replace("\n", " ")[:230])
        results.append(("① 高危调用先弹审批，批准后真的执行到工具（拿到业务 404，不是闸门文案）",
                        GATE_MARK not in first_text, first_text[:200]))

        second_text = text_of(await mcp.call_tool(TOOL, ARGS))
        print("[3] 第二次（同参数）：" + second_text.replace("\n", " ")[:200])
        results.append(("② 本轮重试台账覆盖一次（客户端超时后重试可直接执行）",
                        GATE_MARK not in second_text, second_text[:200]))

        # 第三次：台账已消费 → 必须重新发起审批。不等它 120s，只看「有没有新单」。
        before = await AgentApproval.objects.filter(session=session).acount()
        third = asyncio.ensure_future(mcp.call_tool(TOOL, ARGS))
        await asyncio.sleep(6)
        after_rows = [x async for x in AgentApproval.objects.filter(session=session).values("status")]
        third.cancel()
        print(f"[4] 第三次：审批记录 {before} → {len(after_rows)} 条，状态 {[r['status'] for r in after_rows]}")
        results.append(("③ 一次批准只放行一次：第三次同参数重新进入审批（新单落库）",
                        len(after_rows) > before, f"{after_rows}"))

        rows = [x async for x in AgentApproval.objects.filter(session=session).values("status", "run_id", "dedupe_key")]
        print(f"[5] 审批记录明细：{rows}")
        results.append(("④ 记录可审计（含 status / dedupe_key，run_id 由入口 A 提供、MCP 侧为空属预期）",
                        all(r["dedupe_key"] for r in rows), str(rows)[:200]))

    await AgentSession.objects.filter(pk=session.pk).adelete()
    print("[6] 清理：会话与其审批记录已删除")

    print("\n==== 验收结论 ====")
    bad = 0
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  ← {detail}"))
        bad += 0 if ok else 1
    print(f"==== {'全部通过' if bad == 0 else f'{bad} 项失败'} ====")
    return 0 if bad == 0 else 1


raise SystemExit(asyncio.run(main()))
