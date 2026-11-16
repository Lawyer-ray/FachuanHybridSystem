"""stream_chat —— 一轮对话的 SSE 编排（原 chat_service.py 主体）。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone

from ...models import AgentMessage, AgentSession
from ...pi.bridge import stream_events
from ...pi.pool import PoolQueueTimeoutError
from ...pi.rpc_client import PiError, PiNotAvailableError, parse_context_usage
from ..event_bus import get_bus
from ..history import render_transcript
from ..live_sessions import get_live_registry
from ..memory_tasks import enqueue_extraction
from ..session_cleanup import has_pi_session
from ..skill_service import enabled_skill_paths
from . import env, persist, pool

logger = logging.getLogger(__name__)

#: 会话标题缺省取首条用户消息的前若干字（侧边栏会话列表用）
AUTO_TITLE_LIMIT = 30


async def stream_chat(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
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
    """
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

    await AgentMessage.objects.acreate(
        session=session,
        role=AgentMessage.Role.USER,
        content=user_message,
    )
    updates: dict[str, Any] = {"updated_at": timezone.now()}
    if not session.title:
        # 侧边栏会话列表默认靠标题区分；首条消息前 30 字是最低成本的近似。
        # 先剥掉前端注入的锚点行（[当前业务：…]/[当前页面：…]/[已引用…：…]
        # 块）——否则标题变成「[当前业务：本委托] xx公司诉…」，锚点对标题
        # 没有信息量还挤掉正文
        title_src = user_message.strip()
        for lead in ("[当前业务：", "[当前页面：", "[已引用文件：", "[已引用目录："):
            if title_src.startswith(lead):
                title_src = title_src.split("\n", 1)[1].strip() if "\n" in title_src else ""
                break
        updates["title"] = title_src[:AUTO_TITLE_LIMIT]
    await AgentSession.objects.filter(pk=session.pk).aupdate(**updates)

    bus = get_bus()
    external_queue = await bus.register(str(session.session_id))

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
        yield {"type": "meta", "session_id": str(session.session_id), "agent": "pi"}
        yield {"type": "activity", "status": "thinking", "agent": "pi"}

        pi_pool = await pool.get_pool()
        # 按请求解析模型：Admin 改了 LLMProvider 默认模型立即生效，
        # 且 --model 与 models.json 同源不会失配（池配置里的只是兜底）。
        model = await pool._resolve_model()
        if model and model != session.llm_model:
            # 回写实际使用的模型，SessionOut 如实回报（客户端不再传模型）
            await AgentSession.objects.filter(pk=session.pk).aupdate(llm_model=model)
        # 会话级 env：extension 靠 FACHUAN_SESSION_ID 把审批回调路由回本会话。
        # 必须在启动 pi 之前注入，否则回调里 session_id 为空，前端收不到
        # approval_request，只能等超时走 fail-closed。
        session_env = env.session_env(session, user_id, user_token=user_token)
        # 本律师启用的技能目录（`--skill` 注入；偏好查询走同步 ORM，放线程里）。
        # 无用户身份（测试场景）时给空清单——不注入任何技能也能正常对话。
        if user_id is not None:
            skill_paths = await sync_to_async(enabled_skill_paths, thread_sensitive=True)(user_id)
        else:
            skill_paths = []
        # 池满时先告知前端在排队（否则用户只能盯着转圈不知道发生了什么）。
        # 必须在 acquire 之前看：acquire 里会同步等执行位，事件发不出去。
        # 用 getattr 容错：测试与自定义池实现不一定带这两个属性。
        waiting = int(getattr(pi_pool, "waiting", 0) or 0)
        saturated = bool(getattr(pi_pool, "saturated", False))
        if waiting > 0 or saturated:
            yield {
                "type": "activity",
                "status": "queued",
                "agent": "pi",
                "position": waiting + 1,
            }
        async with pi_pool.acquire(
            session_env=session_env,
            model=model,
            session_id=session_id,
            tool_selection=tool_selection,
            skill_paths=skill_paths,
        ) as pi_session:
            # 同时消费两个来源：pi 事件流 + 外部总线（审批请求）。
            # 不用「两个 get() task + asyncio.wait」—那个写法在 yield 让出控制权后
            # 容易丢掉已取出的事件（实测表现为只有 activity、无 delta）。
            # 改为：pi 事件流为主循环，审批事件用非阻塞轮询插队。
            stream = stream_events(pi_session)
            pending_next: asyncio.Task[dict[str, Any]] | None = None
            # 登记运行中会话：用户可在本轮跑到一半时 steer / follow_up。
            # 必须包在事件循环外面——登记后才有 prompt，否则插话会打空。
            registry = get_live_registry()
            await registry.register(str(session.session_id), pi_session)
            # P2-3：跨 worker 路由注册（Redis 路由表）
            from ..live_sessions import register_live_route

            register_live_route(str(session.session_id), env._worker_id())
            try:
                await pi_session.prompt(prompt_text)
                while True:
                    while True:
                        try:
                            yield external_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                    if pending_next is None:
                        pending_next = asyncio.ensure_future(stream.__anext__())
                    await asyncio.wait({pending_next}, timeout=0.2)
                    if not pending_next.done():
                        continue
                    task, pending_next = pending_next, None
                    try:
                        event = task.result()
                    except StopAsyncIteration:
                        break
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
                        await persist._persist_tool_message(session, event)
                    if event.get("type") == "done":
                        break
            finally:
                await registry.unregister(str(session.session_id), pi_session)
                from ..live_sessions import unregister_live_route

                unregister_live_route(str(session.session_id))
                if pending_next is not None:
                    # 提前退出（done / 取消）时可能还挂着一次 __anext__，必须收掉，
                    # 否则任务泄漏并在事件循环关闭时刷 "Task was destroyed" 警告。
                    pending_next.cancel()

            # 轮正常结束、pi 进程还活着（仍在 async with 内）：取一次会话水位，
            # 供 done 事件与 AgentRun。异常路径不会走到这里；stats 失败只降级
            # （水位 None），不影响对话本身。
            try:
                context_used, context_total = parse_context_usage(await pi_session.get_session_stats())
            except Exception:
                logger.warning("会话上下文水位获取失败（不影响对话）", exc_info=True)

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
        if assistant_text:
            metadata: dict[str, Any] = {"model": model or ""}
            if output_tokens_total > 0:
                metadata["output_tokens"] = output_tokens_total
            if cancelled or not follow_ok:
                metadata["truncated"] = True
            persist_coro = AgentMessage.objects.acreate(
                session=session,
                role=AgentMessage.Role.ASSISTANT,
                content=assistant_text,
                metadata=metadata,
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
