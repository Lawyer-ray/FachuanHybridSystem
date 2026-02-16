"""LLM SSE 流式响应服务.

将 LLM 流式响应封装为 SSE 事件流,包含错误处理.
try/except 在此处是必要的,因为 SSE 流已开始后无法使用全局异常处理器.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings

from apps.core.error_presentation import ExceptionPresenter

logger = logging.getLogger(__name__)


async def build_chat_stream(
    *,
    message: str,
    session_id: str | None,
    user_id: str,
    system_prompt: str | None,
    conversation_service_factory: Callable[..., Any],
    llm_service_factory: Callable[..., Any],
) -> AsyncIterator[bytes]:
    """构建 SSE 聊天流生成器.

    Args:
        message: 用户消息
        session_id: 会话 ID
        user_id: 用户 ID
        system_prompt: 系统提示词
        conversation_service_factory: 会话服务工厂
        llm_service_factory: LLM 服务工厂

    Yields:
        SSE 事件的 bytes 数据
    """
    presenter = ExceptionPresenter()

    conversation_service = await sync_to_async(conversation_service_factory, thread_sensitive=True)(
        session_id=session_id, user_id=user_id
    )

    meta_json = json.dumps(
        {"type": "meta", "session_id": conversation_service.session_id},
        ensure_ascii=False,
    )
    yield f"data: {meta_json}\n\n".encode()

    await sync_to_async(conversation_service.add_user_message, thread_sensitive=True)(message)

    base_messages: list[dict[str, str]] = []
    if system_prompt:
        base_messages.append({"role": "system", "content": system_prompt})
    history = await sync_to_async(conversation_service.get_messages_for_llm, thread_sensitive=True)()
    base_messages.extend(history)

    llm_service = await sync_to_async(llm_service_factory, thread_sensitive=True)()

    full: list[str] = []
    last_usage: Any | None = None
    last_model = ""
    last_backend = ""
    started_at = time.perf_counter()

    try:
        async for chunk in llm_service.astream(base_messages, temperature=0.7):
            piece: str = chunk.content or ""
            if piece:
                full.append(piece)
                yield f"data: {json.dumps({'type': 'delta', 'content': piece}, ensure_ascii=False)}\n\n".encode()
            if chunk.usage:
                last_usage = chunk.usage
            if getattr(chunk, "model", ""):
                last_model = chunk.model
            if getattr(chunk, "backend", ""):
                last_backend = chunk.backend

        content = "".join(full)
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        await sync_to_async(conversation_service.add_assistant_message, thread_sensitive=True)(
            content,
            metadata={
                "model": last_model,
                "backend": last_backend,
                "tokens": getattr(last_usage, "total_tokens", 0) if last_usage else 0,
                "duration_ms": round(duration_ms, 2),
            },
        )
        done_json = json.dumps(
            {"type": "done", "session_id": conversation_service.session_id},
            ensure_ascii=False,
        )
        yield f"data: {done_json}\n\n".encode()
    except Exception as e:
        logger.exception("SSE 流处理失败")
        envelope, _ = presenter.present(e, channel="sse", debug=getattr(settings, "DEBUG", False))
        error_payload = {
            "type": "error",
            **envelope.to_payload(include_legacy_error=False),
        }
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode()
