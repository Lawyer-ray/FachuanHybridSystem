"""stream_chat —— 一轮对话的 SSE 编排（原 chat_service.py 主体）。

本层是**编排层**：准入（铸凭证）、落库（消息 / 标题 / ``AgentRun``）、事件总线、
会话收尾都归它；「跑一轮」本身交给 ``backends`` 注册表里按 kind 取到的后端。
后端只吐事件，本层把事件先入账再转发，保证「客户端断开时已送达的增量已经在落库
缓冲里」。

## 遗留的 pi 直接依赖

``PoolQueueTimeoutError`` / ``PiError`` / ``PiNotAvailableError`` 仍从 pi 包里 import：
它们是**pi 特有异常**，本层要按异常类型给出不同文案（排队超时是「忙」不是故障，
pi 不可用要引导找管理员）。等接入第二个后端时再收敛成统一的 ``BackendError``
层次——现在先统一会让「哪个后端坏了」的信息在翻译时丢掉。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone

from ...backends import RunContext
from ...backends import get as get_backend
from ...backends.builtin import ensure_registered
from ...models import AgentMessage, AgentSession
from ...pi.pool import PoolQueueTimeoutError
from ...pi.rpc_client import PiError, PiNotAvailableError
from ..event_bus import get_bus
from ..history import render_transcript
from ..memory_tasks import enqueue_extraction
from ..session_cleanup import has_pi_session
from . import env, persist

logger = logging.getLogger(__name__)

#: 会话标题缺省取首条用户消息的前若干字（侧边栏会话列表用）
AUTO_TITLE_LIMIT = 30


def auto_title(user_message: str) -> str:
    """会话标题候选：用户消息剥掉锚点块后的前若干字。

    侧边栏会话列表默认靠标题区分；首条消息前 30 字是最低成本的近似。
    先剥掉前端注入的锚点行（[当前业务：…]/[当前页面：…]/[已引用…：…]
    块）——否则标题变成「[当前业务：本委托] xx公司诉…」，锚点对标题
    没有信息量还挤掉正文。

    独立成函数是因为双答路径（``dual.py``）也要用它，而那条路径不经过
    ``stream_chat``——两处各抄一份必然漂移，标题口径一旦分叉就很难发现。
    """
    title_src = user_message.strip()
    for lead in ("[当前业务：", "[当前页面：", "[已引用文件：", "[已引用目录："):
        if title_src.startswith(lead):
            title_src = title_src.split("\n", 1)[1].strip() if "\n" in title_src else ""
            break
    return title_src[:AUTO_TITLE_LIMIT]


async def record_user_message(session: AgentSession, user_message: str) -> None:
    """落库本轮用户消息（并在首轮补会话标题）。

    归编排层而不是后端（见 ``backends/base.py`` 的分工边界）：双答模式下两个
    后端跑的是**同一条**用户消息，必须只落一条——各写一次会让历史回放里出现
    两个一模一样的提问。
    """
    await AgentMessage.objects.acreate(
        session=session,
        role=AgentMessage.Role.USER,
        content=user_message,
    )
    updates: dict[str, Any] = {"updated_at": timezone.now()}
    if not session.title:
        updates["title"] = auto_title(user_message)
    await AgentSession.objects.filter(pk=session.pk).aupdate(**updates)


async def stream_chat(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
    user_message_recorded: bool = False,
    persist_assistant: bool = True,
    memo: Any | None = None,
    agent_kind: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """跑一轮对话，产出 SSE 事件。

    ## 多轮上下文归谁管

    正常路径交给 **pi 原生 session**（``--session-dir`` + ``--session-id``）：
    pi 自己裁剪上下文并做自动 compaction，prompt cache 也能命中，长会话不再
    受 30 条 / 24000 字符的硬截断。

    **回退路径**只在一个场景触发：这个会话已有历史消息，但没有对应的 pi
    session 文件（旧数据 / 目录被清理 / 换了部署节点）。此时把历史渲染成
    transcript 附在 prompt 前，保证用户不会突然失忆；一旦这轮跑完，pi 就有了
    自己的 session 文件，下一轮自动回到正常路径。

    两种情况下本轮的助手文本与工具结果都会回写 ``AgentMessage``，那是审计与
    会话回放的权威来源。

    Args:
        user_message_recorded: 用户消息**已经**由调用方落库（双答路径
            ``dual.py`` 一次落库、两个后端共用）。``True`` 时本函数不再写用户
            消息与标题，只跑后端那一半。
        persist_assistant: 是否由本函数把助手正文写进 ``AgentMessage``。
            默认 ``True``。双答路径的**次答**传 ``False``：它的正文要带回调用方
            才能带上 ``agent_kind`` 落库，否则两条 assistant 消息里有一条永远
            缺来源标注，历史回放分不出哪条是谁。其余落库（工具结果、压缩留痕、
            ``AgentRun``）仍照旧由本函数做——那些不区分栏，必须有且只有一份。
        memo: 与 ``persist_assistant=False`` 配套的可变容器（``dual.StreamMemo``）。
            本函数把本轮 ``run_id``、已流出的正文与 metadata 写进去，供调用方
            自行落库。类型用 ``Any`` 是为了不让编排层 import 调用方模块。
        agent_kind: 本轮**用哪个后端**跑。默认空串 = 用会话自己的
            ``session.agent_kind``（单后端路径的唯一口径）。双答路径必须显式
            传：同一个会话要同时跑主/次两个后端，靠会话字段选后端会让两次调用
            都取到主后端——表现是「两栏内容一模一样」，且不会报任何错。
    """
    # 先确保内置后端已注册（幂等）：注册表是进程内全局状态，可能被清空过；
    # 取后端之前补一次，比依赖「app 启动时那一次」稳得多（见 builtin 模块说明）。
    ensure_registered()

    # 后端按会话的 ``agent_kind`` 选（模型字段已在 AgentSession 上，历史数据回填为
    # ``pi``）。未设置 / 未识别时回落到 ``pi``：引入多后端前只有一个后端在跑，
    # 空串必须等价于引入前的行为。
    backend = get_backend(agent_kind or getattr(session, "agent_kind", "") or "pi")

    # 先铸身份凭证再接受消息：铸不出（用户被删/停用）就整轮拒绝，
    # 不能让工具退回超管服务账号执行。
    try:
        user_token = await env.mint_user_token(user_id)
    except Exception:
        logger.exception("为用户 %s 铸造 agent 凭证失败，拒绝本轮对话", user_id)
        yield {"type": "error", "message": "无法为当前用户签发工具访问凭证，请联系管理员"}
        return

    session_id = str(session.session_id)
    resumed = await sync_to_async(has_pi_session, thread_sensitive=True)(session_id)
    prompt_text = user_message
    if not resumed:
        history = await persist._recent_history(session)
        if history:
            # 无 pi session 但有历史 → 一次性补齐上下文，之后交给 pi 自己管
            prompt_text = render_transcript(history, user_message)
            logger.info("pi session 缺失，本轮以 transcript 回退 session=%s 历史=%s 条", session_id, len(history))

    if not user_message_recorded:
        await record_user_message(session, user_message)

    bus = get_bus()
    external_queue = await bus.register(str(session.session_id))

    # 本轮运行 id：``{session_id}:{agent_kind}:{轮次}``，审批回调与运行记录都靠它归因。
    # 轮次序号**暂固定为 1**：现在每会话同一时刻只有一轮在跑，多 agent 并行上线时
    # 再按会话内的并发轮次递增（届时审批弹窗才需要区分「同会话第几轮」）。
    run_id = f"{session_id}:{backend.kind}:1"
    if memo is not None:
        # 事件里的 run_id 与这里同源：调用方靠它把事件归到正确的栏（见 dual.py
        # 的 StreamMemo 说明），不要在两处各推导一遍。
        memo.run_id = run_id

    follow_ok = True
    cancelled = False
    model: str | None = None
    assistant_parts: list[str] = []
    output_tokens_total = 0
    input_tokens_total = 0
    # 缓存 token 单独累加，**不能**并进 input（cacheRead 是每轮重读的累计
    # 前缀，累加会严重虚高）。详情见 AgentRun.cache_read_tokens 注释。
    cache_read_total = 0
    cache_write_total = 0
    tool_calls_total = 0
    # 上下文水位（轮结束、pi 关闭前取一次；拿不到保持 None，不编造 0）
    context_used: int | None = None
    context_total: int | None = None
    error_kind = ""
    started = time.monotonic()
    try:
        yield {"type": "meta", "session_id": str(session.session_id), "agent": backend.kind}
        # 开流即告知「正在思考」：后台进程启动、排队、建连都要时间，这段时间前端
        # 只有一个静态界面。这是编排层的状态播报（与具体后端无关），所以不走后端事件。
        yield {"type": "activity", "status": "thinking", "agent": backend.kind, "run_id": run_id}
        # 直接用注册表里那个后端实例：收尾事实按 ``run_id`` 归集在它身上
        # （``result_for(run_id)``），并发会话各取各的，不会互相覆盖。
        ctx = RunContext(
            run_id=run_id,
            session=session,
            user_id=user_id,
            prompt=prompt_text,
            user_token=user_token,
            model=None,
            tool_selection=tool_selection,
        )
        stream = backend.stream(ctx)
        # 收到 done 就别再 aclose：后端在 done 之前已经写好 ``result``（见
        # ``pi_backend`` 的 done 分支），aclose 只会白跑一遍关闭流程。
        stream_exhausted = False
        try:
            async for event in stream:
                # ``None`` 是后端「本 tick 无事件」的让出信号：借这个 tick 把外部总线
                # 里的审批事件推进来（审批不走后端事件流，见 pi_backend 模块说明）。
                while True:
                    try:
                        yield external_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                if event is None:
                    continue

                # delta 先入账再 yield：生成器停在 yield 点被打断（客户端断开）
                # 时，已送达的最后一段增量必须已经在落库缓冲里
                if event.get("type") == "delta":
                    assistant_parts.append(str(event.get("content") or ""))
                elif event.get("type") == "usage":
                    # pi 的精确计数：一轮里工具循环会产出多段 assistant，逐段累加
                    output_tokens_total += int(event.get("output_tokens") or 0)
                    input_tokens_total += int(event.get("input_tokens") or 0)
                    cache_read_total += int(event.get("cache_read_tokens") or 0)
                    cache_write_total += int(event.get("cache_write_tokens") or 0)
                elif event.get("type") == "tool_call":
                    tool_calls_total += 1
                elif event.get("type") == "compaction" and event.get("phase") == "end":
                    # 自动压缩完成：Django 消息表是回放权威，必须留痕；
                    # 否则律师重开会话只看到 AI「失忆」，没有任何解释。
                    await persist._persist_compaction_message(session, "自动压缩上下文")
                yield event
                if event.get("type") == "tool_result":
                    # 工具结果也带 agent_kind：双答时两栏的证据必须能对回各自的栏
                    await persist._persist_tool_message(session, event, backend.kind)
                if event.get("type") == "done":
                    # 记下「已见过 done」，但**不 break**：后端生成器在 done 之后还有
                    # 代码（finally 里注销 live session、收掉挂起的 __anext__；再退
                    # 出 async with 归还进程），break 会让它永远停在 yield 点、这
                    # 些收尾一次也不会跑（表现为注册表泄漏、进程不归还）。
                    # 后端保证 done 是最后一个事件（见 ``base.py`` 契约），所以下一
                    # 轮 async for 就结束。
                    stream_exhausted = True
        finally:
            # 客户端断开 / 取消时本生成器停在 ``yield`` 点收到 GeneratorExit。后端那侧
            # 必须被关掉：它的 finally 要注销 live session、收掉挂起的 ``__anext__``，
            # ``pool.acquire`` 的退出路径才走得到取消分支
            # （close(abort_running=True) → 先 clear_queue + abort 再关进程）。
            #
            # **不能在这里 await ``stream.aclose()``**：真实 pi 进程的关闭要屏蔽外层
            # 取消、跑完整套 abort 流程（可能耗时数百毫秒），而 GeneratorExit 路径上
            # 的 await 会把「用户按停止」变成「等半天没反应」——原实现在这里也不
            # await，取消语义由 ``pool.acquire.__aexit__`` 自己担。改成派一个后台
            # 任务去关：既不会卡住前端，也不会因 GC 时机不确定而泄漏子进程。
            if not stream_exhausted:
                task = asyncio.ensure_future(stream.aclose())
                task.add_done_callback(persist._log_task_failure)

        # 收尾事实（实际模型、上下文水位）按 run_id 向后端取——异步生成器的 return
        # 值取不到，而后端在 done 之前就已把它写好。后端没实现 ``result_for`` 时
        # 保持上面的缺省值（模型 ``None``、水位 ``None``），不编造数据。
        result_for = getattr(backend, "result_for", None)
        result = result_for(run_id) if result_for is not None else None
        if result is not None:
            # 实际用的模型与水位都要回写：SessionOut 如实回报（客户端不再传模型），
            # done 事件与 AgentRun 也要用同一个值（两处不一致会让成本对不上账）。
            model = result.model
            context_used, context_total = result.context_used, result.context_total
            if model and model != session.llm_model:
                await AgentSession.objects.filter(pk=session.pk).aupdate(llm_model=model)

    except (GeneratorExit, asyncio.CancelledError):
        # 客户端断开/中止：已流出的部分回答也要落库（见 finally），再按生成器语义上抛。
        # 真正把「停」传递给 pi 的动作在 ``pool.acquire`` 的取消分支（
        # close(abort_running=True) → 先 clear_queue + abort 再关进程），
        # 那里能屏蔽外层取消、保证 abort 真写得进 stdin。
        cancelled = True
        logger.info("用户中止本轮对话 session=%s，已流出的 %s 段将落库", session.pk, len(assistant_parts))
        raise
    except PiNotAvailableError as exc:
        follow_ok = False
        error_kind = "pi_unavailable"
        logger.error("pi 不可用: %s", exc)
        yield {"type": "error", "message": "pi 运行时不可用，请联系管理员（详见服务端日志）"}
    except PoolQueueTimeoutError as exc:
        # 排队超时是「忙」，不是故障：给出可读提示，不要把堆栈吐给律师
        follow_ok = False
        error_kind = "queue_timeout"
        logger.warning("agent 进程池排队超时: %s", exc)
        yield {"type": "error", "message": "当前使用人数较多，请稍后重试"}
    except PiError as exc:
        follow_ok = False
        error_kind = "pi_error"
        logger.error("pi 运行失败: %s", exc)
        yield {"type": "error", "message": "pi 运行失败，请稍后重试（详见服务端日志）"}
    except Exception:
        follow_ok = False
        error_kind = "unexpected"
        logger.exception("Agent runtime 未预期错误")
        yield {"type": "error", "message": "Agent 运行失败，请稍后重试"}
    finally:
        # 注意：生成器的 finally 里**不能 yield**。客户端断开时本协程会收到
        # GeneratorExit，此时再 yield 会抛 RuntimeError（"async generator ignored
        # GeneratorExit"），表现为 SSE 被截断、curl 返回 CURLE_PARTIAL_FILE(18)。
        await bus.unregister(str(session.session_id), external_queue)

        # 运行记录落库（成功 / 取消 / 出错三态都记）。
        # 只记成功等于把最贵的失败藏起来：用户按停止时模型可能已跑了大半
        # token，网关超时重试三次也是真金白银。
        await persist._record_run(
            session=session,
            user_id=user_id,
            model=model,
            cancelled=cancelled,
            error_kind=error_kind,
            input_tokens=input_tokens_total,
            output_tokens=output_tokens_total,
            cache_read_tokens=cache_read_total,
            cache_write_tokens=cache_write_total,
            tool_calls=tool_calls_total,
            duration_ms=int((time.monotonic() - started) * 1000),
            context_used_tokens=context_used,
            context_total_tokens=context_total,
        )

        # 助手文本落库放在 finally：取消/出错路径已流出的部分回答同样要保住
        # （用户看着三段回答按停止，重开会话不能全没）。取消路径里允许 await
        # （禁止的只是 yield）；若外层任务仍在取消中，await 会立刻抛
        # CancelledError——用 shield 保住写入，外层继续上抛、内层后台完成。
        assistant_text = "".join(assistant_parts).strip()
        # metadata 两条路径都要（落库 / 交回调用方），放在 if 外面算
        assistant_metadata: dict[str, Any] = {}
        if assistant_text:
            assistant_metadata = {"model": model or ""}
            if output_tokens_total > 0:
                assistant_metadata["output_tokens"] = output_tokens_total
            if cancelled or not follow_ok:
                assistant_metadata["truncated"] = True
        if memo is not None:
            # 交回调用方落库（persist_assistant=False）：正文与 metadata 都要给，
            # 否则调用方只能自己重算一遍 token 与截断标记，两处必然漂移。
            memo.parts = list(assistant_parts)
            memo.metadata = assistant_metadata
        if assistant_text and not persist_assistant:
            logger.debug("助手正文交由调用方落库 session=%s run=%s", session_id, run_id)
        elif assistant_text:
            metadata = assistant_metadata
            persist_coro = AgentMessage.objects.acreate(
                session=session,
                role=AgentMessage.Role.ASSISTANT,
                content=assistant_text,
                metadata=metadata,
                # 单后端轮次也标注来源：历史回放要靠它区分双答轮次的两栏与
                # 普通轮次的一条（空串 = 引入本字段前的旧数据）。
                agent_kind=backend.kind,
            )
            if cancelled:
                task = asyncio.ensure_future(persist_coro)
                task.add_done_callback(persist._log_task_failure)
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(task)
            else:
                try:
                    await persist_coro
                except Exception:
                    logger.warning("助手消息落库失败", exc_info=True)

        # 会话收尾后异步抽取个人记忆（→ pending，等律师确认）。
        #
        # 为什么在这里而不是 pi 扩展里：本系统每请求起一个 pi 进程、用完即关，
        # 取消路径走 ``abort_running=True``，``session_shutdown`` 不保证干净触发；
        # 且 pi core 等 shutdown handler 无超时，同步调 LLM 会把关闭拖死。
        # 取消的运行同样入队：用户按停止不代表前面说的偏好不值得记。
        try:
            await asyncio.shield(sync_to_async(enqueue_extraction, thread_sensitive=False)(str(session.session_id)))
        except Exception:
            logger.warning("记忆抽取入队失败（不影响对话）", exc_info=True)

    if follow_ok:
        yield {
            "type": "done",
            "session_id": str(session.session_id),
            "context_used_tokens": context_used,
            "context_total_tokens": context_total,
        }
