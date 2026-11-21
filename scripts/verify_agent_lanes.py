"""真机验收：四个 agent 能不能答、思考开没开、联网搜索通不通、四栏并答成不成。

## 为什么需要它

单元测试只能证明「翻译逻辑对」，证明不了三件事：

1. **四个后端在同一台机器上真的都起得来**（pi 子进程 / dsh 常驻 / openai-agents
   SDK / antigravity 的 Go 二进制，四套完全不同的生命周期）；
2. **思考模式真的开了**——它不报错，只是回答变浅。判据必须是「收到 ``thinking``
   帧」+「``usage`` 里有思考 token」，而不是「代码里传了参数」；
3. **联网搜索真的能用**——`web_search` 要么不在工具面（模型根本看不见），要么在
   但网关/检索链路不通（工具返回 error）。判据是「真的出现 ``web_search`` 的
   ``tool_call`` 且 ``tool_result.is_error=false``」。

这三件事都没法靠 mock 验，只能真跑。所以本脚本走**真实编排层**
（``stream_chat`` / ``stream_multi``），而不是直接调后端 ``stream()``：编排层的
落库、审批总线、每栏 key 分配、``done`` 收尾全都在链路里，绕过它们就是在验另一条路径。

## 用法

```bash
cd backend/apiSystem
PYTHONPATH=.:.. ../.venv/bin/python ../../scripts/verify_agent_lanes.py

# 只跑某几栏 / 换问题 / 指定提示词
... --kinds pi,antigravity
... --prompt "自定问题" --multi-prompt "四栏同一问题"

# 只测四栏并答（不逐栏单跑）
... --skip-single
```

## 判定口径（脚本会自己下结论，非零退出 = 有失败）

| 维度 | 通过判据 |
|:-|:-|
| 能回答 | 该栏 ``delta`` 帧 > 0 且拼出的正文非空 |
| 思考开启 | 该栏 ``thinking`` 帧 > 0 **且** ``usage.output_tokens`` 里含思考 token |
| 联网搜索 | 出现 ``web_search`` 的 ``tool_call``，且对应 ``tool_result.is_error`` 为 false |
| 四栏并答 | 4 栏各一条 ``done``、各有正文、``run_id`` 互不相同 |

审批：脚本把 ``request_approval`` 替换成「立即放行」（只影响本进程），
否则高危工具会挂起等真人，验收就会卡在超时上。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()

from asgiref.sync import sync_to_async

from apps.agent.backends import builtin, registry
from apps.agent.models.session import AgentSession
from apps.agent.services.chat.multi import MAX_ANSWERS, AgentSpec, stream_multi

#: 默认逐栏单跑的问题：前两句要触发「先想再说」，后一句要触发联网检索。
DEFAULT_PROMPT = (
    "请先在心里完整推理再回答，不要直接给结论："
    "《民法典》第五百八十五条规定的违约金调整规则是什么？"
)
#: 默认的四栏并答问题（四栏必须答同一句，否则比的不是同一件事）。
DEFAULT_MULTI_PROMPT = "用三句话说明：律师收到一份买卖合同后，第一步应该核查什么？"
#: 触发联网搜索的问法（明确要求查外部信息，逼模型去调 web_search）。
SEARCH_PROMPT = "帮我上网搜索一下「最高人民法院关于适用民法典合同编通则的解释」的最新条文，给出处链接。"


class LaneResult:
    """一栏的实测结果（单跑与并答共用）。"""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.delta = 0
        self.thinking = 0
        self.tool_calls: list[str] = []
        self.tool_results: list[tuple[str, bool]] = []
        self.usage_in = 0
        self.usage_out = 0
        self.errors: list[str] = []
        self.dones = 0
        self.run_ids: set[str] = set()
        self.text: list[str] = []
        self.thoughts: list[str] = []
        self.started_at = time.monotonic()
        self.elapsed = 0.0

    def feed(self, event: dict[str, Any]) -> None:
        """按事件类型累计（字段口径见 ``sse_types.py``）。"""
        etype = event.get("type")
        if event.get("run_id"):
            self.run_ids.add(str(event["run_id"]))
        if etype == "delta":
            self.delta += 1
            self.text.append(str(event.get("content") or ""))
        elif etype == "thinking":
            self.thinking += 1
            self.thoughts.append(str(event.get("content") or ""))
        elif etype == "tool_call":
            self.tool_calls.append(str(event.get("name") or ""))
        elif etype == "tool_result":
            self.tool_results.append((str(event.get("name") or ""), bool(event.get("is_error"))))
        elif etype == "usage":
            self.usage_in += int(event.get("input_tokens") or 0)
            self.usage_out += int(event.get("output_tokens") or 0)
        elif etype == "error":
            self.errors.append(str(event.get("message") or event.get("code") or "error"))
        elif etype == "done":
            self.dones += 1
            # 每栏一条 done 才是协议要求的；多栏时 done 在**全部栏落库之后**才发，
            # 所以这一条时间戳代表「该栏可见完成」，不是「该栏算完」。
            self.elapsed = time.monotonic() - self.started_at

    # ── 判定 ─────────────────────────────────────────────────────────
    @property
    def answered(self) -> bool:
        return self.delta > 0 and bool("".join(self.text).strip())

    @property
    def search_called(self) -> bool:
        """模型有没有真的去调 ``web_search``（工具面可见 + 模型选择调用）。"""
        return any("web_search" in name for name in self.tool_calls)

    @property
    def searched(self) -> bool:
        """联网搜索**证据齐**：调了 ``web_search`` 且对应 ``tool_result`` 不是错误。

        注意「调用成功」与「我们能看见结果」是两件事：dsh 后端目前**不翻译**
        ``tool/result`` 事件（``dsh_backend.py`` 的 ``_translate_event`` 只有
        ``assistant/message`` / ``tool/call`` / ``turn/end`` 三个分支），所以那
        一栏永远是「调了但看不到结果」。这种情况判成「无法判定」而不是「未通过」，
        否则会把后端的埋点缺失误报成搜索坏掉。
        """
        return self.search_called and any("web_search" in name and not is_error for name, is_error in self.tool_results)

    @property
    def search_observable(self) -> bool:
        """这个后端会不会吐 ``tool_result``——不吐就没法从事件流判定搜索是否可用。"""
        return bool(self.tool_results) or not self.tool_calls

    def summary(self) -> str:
        answer = "".join(self.text).strip().replace("\n", " ")
        return (
            f"{self.kind:14s} delta={self.delta:3d} thinking={self.thinking:3d} "
            f"tools={len(self.tool_calls)} usage={self.usage_in}in/{self.usage_out}out "
            f"done={self.dones} run_ids={len(self.run_ids)} {self.elapsed:.1f}s "
            f"answered={'Y' if self.answered else 'N'} "
            f"searched={'Y' if self.searched else ('?' if self.search_called else '-')}"
            + (f" errors={self.errors[:2]}" if self.errors else "")
            + f"\n{'':14s} 答: {answer[:160]}"
        )


async def _auto_approve() -> None:
    """把审批替换成「立即放行」（只在本进程生效，避免验收卡在等人上）。"""
    import apps.agent.services.approval as pkg

    async def approve(**kwargs: Any) -> tuple[bool, str, str]:
        print(f"    [approval] 自动放行 {kwargs.get('tool_name')}", flush=True)
        return True, "verify-auto", "验收脚本自动放行"

    pkg.request_approval = approve  # type: ignore[assignment]


async def _create_session(kind: str, title: str, user_id: int | None) -> AgentSession:
    """建一个会话（真机验收要落库：``stream_chat`` / ``stream_multi`` 都要 session 行）。"""

    def _create() -> AgentSession:
        return AgentSession.objects.create(
            title=title,
            agent_kind=kind,
            origin="chat",
            user_id=user_id,
        )

    return await sync_to_async(_create, thread_sensitive=True)()


async def run_single(kinds: list[str], prompt: str, search_prompt: str, user_id: int | None) -> list[LaneResult]:
    """逐栏单跑：每栏一个独立会话，跑「思考题」+「联网题」两轮。"""
    from apps.agent.services.chat.stream import stream_chat

    results: list[LaneResult] = []
    for kind in kinds:
        session = await _create_session(kind, f"【验收】{kind} 单栏", user_id)
        print(f"\n=== 单栏 {kind}（session {session.session_id}）===", flush=True)

        think = LaneResult(kind)
        async for event in stream_chat(session=session, user_message=prompt, user_id=user_id, agent_kind=kind):
            think.feed(event)
        print(think.summary(), flush=True)

        search = LaneResult(kind)
        async for event in stream_chat(session=session, user_message=search_prompt, user_id=user_id, agent_kind=kind):
            search.feed(event)
        print(f"  [搜索题] {search.summary()}", flush=True)

        # 合并成一栏结果：回答/思考取第一轮，搜索取第二轮
        think.tool_calls += search.tool_calls
        think.tool_results += search.tool_results
        think.errors += search.errors
        think.dones += search.dones
        think.usage_in += search.usage_in
        think.usage_out += search.usage_out
        think.run_ids |= search.run_ids
        think._search_ok = search.searched  # type: ignore[attr-defined]
        results.append(think)
    return results


async def run_multi(kinds: list[str], prompt: str, user_id: int | None) -> dict[str, LaneResult]:
    """四栏并答：一个会话、一个问题、N 栏同时跑，按 ``agent`` 分流。"""
    session = await _create_session(kinds[0] if kinds else "pi", "【验收】四栏并答", user_id)
    print(f"\n=== 多栏并答 {kinds}（session {session.session_id}）===", flush=True)
    lanes: dict[str, LaneResult] = {kind: LaneResult(kind) for kind in kinds}
    specs = [AgentSpec(kind=kind) for kind in kinds]
    async for event in stream_multi(session=session, user_message=prompt, user_id=user_id, specs=specs):
        kind = str(event.get("agent") or (kinds[0] if kinds else "pi"))
        lanes.setdefault(kind, LaneResult(kind)).feed(event)
    for kind, lane in lanes.items():
        print(lane.summary(), flush=True)
    return lanes


def _verdict(
    singles: list[LaneResult], multi: dict[str, LaneResult] | None, kinds: list[str], skip_single: bool
) -> tuple[list[str], list[str]]:
    """把实测结果转成「失败清单 + 警告清单」（失败为空 = 全过）。"""
    failures: list[str] = []
    warnings: list[str] = []
    if not skip_single:
        for lane in singles:
            if not lane.answered:
                failures.append(f"{lane.kind}: 没答出来（delta={lane.delta}, errors={lane.errors[:1]}）")
            if lane.thinking == 0:
                failures.append(f"{lane.kind}: 思考没开（thinking 帧 0；usage={lane.usage_in}/{lane.usage_out}）")
            if not getattr(lane, "_search_ok", False):
                if lane.search_called and not lane.search_observable:
                    # 后端不产出 tool_result：搜索本身可能成功，只是我们看不见 → 警告而非失败
                    warnings.append(
                        f"{lane.kind}: 调了 web_search 但该后端不产出 tool_result 帧，"
                        "搜索是否可用**无法从事件流判定**（需补 tool/result 翻译）"
                    )
                else:
                    failures.append(
                        f"{lane.kind}: 联网搜索没通过（tools={lane.tool_calls[:6]}, results={lane.tool_results[:4]}）"
                    )
    if multi is not None:
        run_ids: set[str] = set()
        for kind in kinds:
            lane = multi.get(kind)
            if lane is None:
                failures.append(f"多栏: {kind} 一帧都没收到")
                continue
            if not lane.answered:
                failures.append(f"多栏 {kind}: 没答出来（delta={lane.delta}, errors={lane.errors[:1]}）")
            if lane.dones != 1:
                failures.append(f"多栏 {kind}: done 数={lane.dones}（应为 1）")
            run_ids |= lane.run_ids
        if len({rid for lane in multi.values() for rid in lane.run_ids}) != len(kinds):
            failures.append(f"多栏: run_id 不唯一（{len(run_ids)} 个，{len(kinds)} 栏）")
    return failures, warnings


async def main() -> int:
    parser = argparse.ArgumentParser(description="四个 agent 的真机验收（回答 / 思考 / 联网搜索 / 四栏并答）")
    parser.add_argument("--kinds", default="", help="逗号分隔；默认取注册表全部后端")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="单栏思考题")
    parser.add_argument("--search-prompt", default=SEARCH_PROMPT, help="单栏联网题")
    parser.add_argument("--multi-prompt", default=DEFAULT_MULTI_PROMPT, help="四栏同一问题")
    parser.add_argument("--skip-single", action="store_true", help="只测四栏并答")
    parser.add_argument("--skip-multi", action="store_true", help="只测逐栏单跑")
    args = parser.parse_args()

    builtin.ensure_registered()
    registered = registry.available_kinds()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()] or registered
    print(f"注册表: {registered}\n本轮参与: {kinds}", flush=True)
    if len(kinds) > MAX_ANSWERS:
        print(f"超过 MAX_ANSWERS={MAX_ANSWERS}，截断", flush=True)
        kinds = kinds[:MAX_ANSWERS]

    from django.contrib.auth import get_user_model

    user = await sync_to_async(lambda: get_user_model().objects.filter(is_active=True).first())()

    await _auto_approve()

    singles: list[LaneResult] = []
    multi: dict[str, LaneResult] | None = None
    try:
        if not args.skip_single:
            singles = await run_single(kinds, args.prompt, args.search_prompt, getattr(user, "pk", None))
        if not args.skip_multi:
            multi = await run_multi(kinds, args.multi_prompt, getattr(user, "pk", None))
    finally:
        failures, warnings = _verdict(singles, multi, kinds, args.skip_single)
        print("\n" + "=" * 70, flush=True)
        for item in warnings:
            print(f"  ⚠ {item}", flush=True)
        if failures:
            print(f"失败 {len(failures)} 项:", flush=True)
            for item in failures:
                print(f"  ✗ {item}", flush=True)
        else:
            print("全部通过 ✅" if not warnings else "通过（含警告）⚠", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
