"""apps/core/services/llm_stream_service.py 单元测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.services.llm_stream_service import build_chat_stream


def _make_chunk(content: str = "", usage: object | None = None, model: str = "", backend: str = "") -> MagicMock:
    """创建模拟 LLM chunk。"""
    chunk = MagicMock()
    chunk.content = content
    chunk.usage = usage
    chunk.model = model
    chunk.backend = backend
    return chunk


def _make_conversation_service(session_id: str = "sess_123") -> MagicMock:
    """创建模拟会话服务。"""
    svc = MagicMock()
    svc.session_id = session_id
    svc.add_user_message = MagicMock()
    svc.get_messages_for_llm = MagicMock(return_value=[{"role": "user", "content": "hi"}])
    svc.add_assistant_message = MagicMock()
    return svc


async def _collect_stream(gen):  # type: ignore[no-untyped-def]
    """收集异步生成器的所有输出。"""
    results = []
    async for chunk in gen:
        results.append(chunk)
    return results


class TestBuildChatStream:
    """测试 build_chat_stream SSE 生成器。"""

    @pytest.mark.asyncio
    async def test_emits_meta_event_first(self) -> None:
        """第一个 SSE 事件应为 meta 类型。"""
        conv_svc = _make_conversation_service(session_id="sess_abc")

        llm_svc = MagicMock()

        async def fake_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            return
            yield  # pragma: no cover

        llm_svc.astream = fake_astream

        factory_conv = MagicMock(return_value=conv_svc)
        factory_llm = MagicMock(return_value=llm_svc)

        with patch("asgiref.sync.sync_to_async", side_effect=lambda fn, **kw: AsyncMock(return_value=fn())):
            results = await _collect_stream(
                build_chat_stream(
                    message="hello",
                    session_id="sess_abc",
                    user_id="user_1",
                    system_prompt=None,
                    conversation_service_factory=factory_conv,
                    llm_service_factory=factory_llm,
                )
            )

        assert len(results) >= 1
        meta = json.loads(results[0].decode().removeprefix("data: ").removesuffix("\n\n"))
        assert meta["type"] == "meta"
        assert meta["session_id"] == "sess_abc"

    @pytest.mark.asyncio
    async def test_emits_delta_events(self) -> None:
        """应为每个非空 chunk 发出 delta 事件。"""
        conv_svc = _make_conversation_service()

        chunk1 = _make_chunk(content="Hello")
        chunk2 = _make_chunk(content=" world")

        async def fake_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            yield chunk1
            yield chunk2

        llm_svc = MagicMock()
        llm_svc.astream = fake_astream

        factory_conv = MagicMock(return_value=conv_svc)
        factory_llm = MagicMock(return_value=llm_svc)

        with patch("asgiref.sync.sync_to_async", side_effect=lambda fn, **kw: AsyncMock(return_value=fn())):
            results = await _collect_stream(
                build_chat_stream(
                    message="hi",
                    session_id=None,
                    user_id="user_1",
                    system_prompt=None,
                    conversation_service_factory=factory_conv,
                    llm_service_factory=factory_llm,
                )
            )

        deltas = []
        for raw in results:
            payload = json.loads(raw.decode().removeprefix("data: ").removesuffix("\n\n"))
            if payload.get("type") == "delta":
                deltas.append(payload["content"])

        assert deltas == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_emits_done_event(self) -> None:
        """流结束时应发出 done 事件。"""
        conv_svc = _make_conversation_service(session_id="sess_done")

        async def fake_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            return
            yield  # pragma: no cover

        llm_svc = MagicMock()
        llm_svc.astream = fake_astream

        factory_conv = MagicMock(return_value=conv_svc)
        factory_llm = MagicMock(return_value=llm_svc)

        with patch("asgiref.sync.sync_to_async", side_effect=lambda fn, **kw: AsyncMock(return_value=fn())):
            results = await _collect_stream(
                build_chat_stream(
                    message="hi",
                    session_id=None,
                    user_id="user_1",
                    system_prompt=None,
                    conversation_service_factory=factory_conv,
                    llm_service_factory=factory_llm,
                )
            )

        last = json.loads(results[-1].decode().removeprefix("data: ").removesuffix("\n\n"))
        assert last["type"] == "done"
        assert last["session_id"] == "sess_done"

    @pytest.mark.asyncio
    async def test_includes_system_prompt(self) -> None:
        """有 system_prompt 时应在 messages 中包含 system 消息。"""
        conv_svc = _make_conversation_service()

        async def fake_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            messages = args[0] if args else kwargs.get("messages", [])
            # system prompt 应在 messages 的第一个
            assert any(m.get("role") == "system" for m in messages)
            return
            yield  # pragma: no cover

        llm_svc = MagicMock()
        llm_svc.astream = fake_astream

        factory_conv = MagicMock(return_value=conv_svc)
        factory_llm = MagicMock(return_value=llm_svc)

        with patch("asgiref.sync.sync_to_async", side_effect=lambda fn, **kw: AsyncMock(return_value=fn())):
            await _collect_stream(
                build_chat_stream(
                    message="hi",
                    session_id=None,
                    user_id="user_1",
                    system_prompt="You are a helpful assistant.",
                    conversation_service_factory=factory_conv,
                    llm_service_factory=factory_llm,
                )
            )

    @pytest.mark.asyncio
    async def test_error_emits_error_event(self) -> None:
        """LLM 抛出异常时应发出 error 事件而非崩溃。"""
        conv_svc = _make_conversation_service()

        async def failing_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("LLM crashed")
            yield  # pragma: no cover

        llm_svc = MagicMock()
        llm_svc.astream = failing_astream

        factory_conv = MagicMock(return_value=conv_svc)
        factory_llm = MagicMock(return_value=llm_svc)

        mock_scs = MagicMock()
        mock_scs.return_value.get_value.return_value = "false"

        with (
            patch("asgiref.sync.sync_to_async", side_effect=lambda fn, **kw: AsyncMock(return_value=fn())),
            patch(
                "apps.core.services.llm_stream_service.ExceptionPresenter"
            ) as mock_presenter_cls,
            patch(
                "apps.core.services.system_config_service.SystemConfigService",
                mock_scs,
            ),
        ):
            mock_presenter = MagicMock()
            mock_envelope = MagicMock()
            mock_envelope.to_payload.return_value = {"code": "INTERNAL_ERROR", "message": "LLM crashed"}
            mock_presenter.present.return_value = (mock_envelope, None)
            mock_presenter_cls.return_value = mock_presenter

            results = await _collect_stream(
                build_chat_stream(
                    message="hi",
                    session_id=None,
                    user_id="user_1",
                    system_prompt=None,
                    conversation_service_factory=factory_conv,
                    llm_service_factory=factory_llm,
                )
            )

        # 应有 error 事件
        payloads = [
            json.loads(raw.decode().removeprefix("data: ").removesuffix("\n\n"))
            for raw in results
        ]
        error_events = [p for p in payloads if p.get("type") == "error"]
        assert len(error_events) == 1
