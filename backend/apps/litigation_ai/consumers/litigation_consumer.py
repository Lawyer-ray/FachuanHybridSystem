"""Module for litigation consumer."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


def _use_agent_mode() -> bool:
    """检查是否使用 Agent 模式"""
    return getattr(settings, "LITIGATION_USE_AGENT_MODE", False)


class LitigationConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.session_id: str | None = None
        self.user: Any | None = None
        self.session: Any | None = None
        self._agent_service: Any | None = None

    @property
    def agent_service(self) -> Any:
        """延迟加载 Agent 服务"""
        if self._agent_service is None:
            from apps.litigation_ai.services.litigation_agent_service import LitigationAgentService

            self._agent_service = LitigationAgentService()
        return self._agent_service

    async def connect(self) -> None:
        try:
            self.user = self.scope.get("user")
            if not self.user or isinstance(self.user, AnonymousUser):
                await self.close(code=4001)
                return

            self.session_id = self.scope["url_route"]["kwargs"].get("session_id")
            if not self.session_id:
                await self.close(code=4002)
                return

            self.session = await self._get_session(self.session_id)
            if not self.session:
                await self.close(code=4004)
                return

            await self.accept()
            await self.channel_layer.group_add(f"litigation_{self.session_id}", self.channel_name)

            # 移除 WebSocket 连接时的自动推送历史消息
            # await self.send_history_messages()

            from apps.litigation_ai.services import ConversationFlowService, ConversationStep, FlowContext

            flow_service = ConversationFlowService()
            context = FlowContext(
                session_id=self.session_id,
                case_id=self.session.case_id,
                user_id=self.user.id,
                current_step=ConversationStep.INIT,
            )
            await flow_service.handle_init(context, self._send_flow_message)
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}", exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code: int) -> None:
        if self.session_id:
            try:
                await self.channel_layer.group_discard(f"litigation_{self.session_id}", self.channel_name)
            except Exception as e:
                logger.error(f"WebSocket 断开连接处理失败: {e}", exc_info=True)

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        try:
            if not text_data:
                await self.send_error("消息内容为空")
                return

            try:
                message = json.loads(text_data)
            except json.JSONDecodeError as e:
                await self.send_error(f"消息格式错误: {e}")
                return

            if not isinstance(message, dict):
                await self.send_error("消息必须是 JSON 对象")
                return

            message_type = message.get("type")
            if not message_type:
                await self.send_error("缺少消息类型")
                return

            handler = self._get_message_handler(message_type)
            if not handler:
                await self.send_error(f"不支持的消息类型: {message_type}")
                return

            await handler(message)
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            await self.send_error(e)

    def _get_message_handler(self, message_type: str) -> Any:
        handlers = {
            "user_message": self.handle_user_message,
            "select_document_type": self.handle_select_document_type,
            "select_evidence": self.handle_select_evidence,
            "confirm_generate": self.handle_confirm_generate,
            "stop_generation": self.handle_stop_generation,
        }
        return handlers.get(message_type)

    async def handle_user_message(self, message: dict[str, Any]) -> None:
        content = message.get("content", "").strip()
        if not content:
            await self.send_error("消息内容为空")
            return

        metadata = message.get("metadata", {})

        if _use_agent_mode():
            await self._handle_user_message_agent(content, metadata)
            return

        await self._add_message("user", content, metadata)

        from apps.litigation_ai.services import ConversationFlowService, FlowContext

        flow_service = ConversationFlowService()
        current_step = await self._get_current_step(flow_service)

        session_id = self.session_id if self.session_id is not None else ""
        context = FlowContext(
            session_id=session_id,
            case_id=self.session.case_id,  # type: ignore[union-attr]
            user_id=self.user.id,  # type: ignore[union-attr]
            current_step=current_step,
        )

        await self._dispatch_by_step(flow_service, context, current_step, content)

    async def _dispatch_by_step(self, flow_service: Any, context: Any, current_step: Any, content: str) -> None:
        from collections.abc import Awaitable

        from apps.litigation_ai.services import ConversationStep

        step_handlers: dict[Any, Callable[[], Awaitable[None]]] = {
            ConversationStep.INIT: lambda: flow_service.handle_init(context, self._send_flow_message),
            ConversationStep.DOCUMENT_TYPE: lambda: self._handle_document_type_step(flow_service, context, content),
            ConversationStep.LITIGATION_GOAL: lambda: flow_service.handle_litigation_goal_collection(
                context, content, self._send_flow_message
            ),
            ConversationStep.EVIDENCE_SELECTION: lambda: flow_service.handle_evidence_selection(
                context, [], [], [], [], self._send_flow_message
            ),
            ConversationStep.DOC_PLAN: lambda: flow_service.handle_doc_plan_selection(
                context, content, self._send_flow_message
            ),
        }

        handler = step_handlers.get(current_step)
        if handler:
            await handler()
        elif current_step in (ConversationStep.GENERATING, ConversationStep.REFINING):
            await flow_service.handle_refining(context, content, self._send_flow_message)

    async def _handle_document_type_step(self, flow_service: Any, context: Any, content: str) -> None:
        from channels.db import database_sync_to_async

        from apps.litigation_ai.chains import DocumentTypeParseChain
        from apps.litigation_ai.models import LitigationSession

        session = await database_sync_to_async(LitigationSession.objects.get)(session_id=self.session_id)
        recommended_types = (session.metadata or {}).get("recommended_types") or []
        allowed_types = recommended_types or ["complaint", "defense", "counterclaim", "counterclaim_defense"]

        try:
            parsed = await DocumentTypeParseChain().arun(user_input=content, allowed_types=list(allowed_types))
            parsed_type = parsed.document_type
        except Exception:
            logger.exception("操作失败")

            parsed_type = ""

        if parsed_type:
            await flow_service.handle_document_type_selection(context, parsed_type, self._send_flow_message)
        else:
            await self._send_flow_message(
                {
                    "type": "system_message",
                    "content": (
                        "我没有理解您要生成的文书类型.请回复:起诉状/答辩状/反诉状/反诉答辩状,或回复序号(如 1)."
                    ),
                }
            )

    async def handle_select_document_type(self, message: dict[str, Any]) -> None:
        document_type = message.get("document_type", "")
        if not document_type:
            await self.send_error("缺少 document_type")
            return

        from apps.litigation_ai.services import ConversationFlowService, ConversationStep, FlowContext

        flow_service = ConversationFlowService()
        session_id = self.session_id if self.session_id is not None else ""
        context = FlowContext(
            session_id=session_id,
            case_id=self.session.case_id,  # type: ignore[union-attr]
            user_id=self.user.id,  # type: ignore[union-attr]
            current_step=ConversationStep.DOCUMENT_TYPE,
        )
        await flow_service.handle_document_type_selection(context, document_type, self._send_flow_message)

    async def handle_select_evidence(self, message: dict[str, Any]) -> None:
        evidence_list_ids = message.get("evidence_list_ids", []) or []
        evidence_item_ids = message.get("evidence_item_ids", []) or []
        our_evidence_item_ids = message.get("our_evidence_item_ids", []) or []
        opponent_evidence_item_ids = message.get("opponent_evidence_item_ids", []) or []

        from apps.litigation_ai.services import ConversationFlowService, ConversationStep, FlowContext

        flow_service = ConversationFlowService()
        session_id = self.session_id if self.session_id is not None else ""
        context = FlowContext(
            session_id=session_id,
            case_id=self.session.case_id,  # type: ignore[union-attr]
            user_id=self.user.id,  # type: ignore[union-attr]
            current_step=ConversationStep.EVIDENCE_SELECTION,
        )
        await flow_service.handle_evidence_selection(
            context,
            evidence_list_ids,
            evidence_item_ids,
            our_evidence_item_ids,
            opponent_evidence_item_ids,
            self._send_flow_message,
        )

    async def handle_confirm_generate(self, message: dict[str, Any]) -> None:
        from apps.litigation_ai.services import ConversationFlowService, ConversationStep, FlowContext

        flow_service = ConversationFlowService()
        session_id = self.session_id if self.session_id is not None else ""
        context = FlowContext(
            session_id=session_id,
            case_id=self.session.case_id,  # type: ignore[union-attr]
            user_id=self.user.id,  # type: ignore[union-attr]
            current_step=ConversationStep.COMPLETED,
        )
        await flow_service.handle_confirm_generate(context, self._send_flow_message)

    async def handle_stop_generation(self, message: dict[str, Any]) -> None:
        await self._send_flow_message({"type": "system_message", "content": "停止生成暂未实现"})

    async def send_error(self, error: Exception | str, code: str = "INVALID_REQUEST") -> None:
        if isinstance(error, Exception):
            from apps.core.exceptions.error_presentation import ExceptionPresenter

            presenter = ExceptionPresenter()
            envelope, _ = presenter.present(error, channel="ws", debug=getattr(settings, "DEBUG", False))
            payload = {
                "type": "error",
                "code": envelope.code,
                "message": envelope.message,
                "errors": envelope.errors,
                "retryable": envelope.retryable,
            }
            await self.send(text_data=json.dumps(payload, ensure_ascii=False))
            return

        await self.send(text_data=json.dumps({"type": "error", "message": error, "code": code}, ensure_ascii=False))

    async def _send_flow_message(self, payload: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))

    async def send_history_messages(self) -> None:
        from apps.litigation_ai.services import LitigationConversationService

        service = LitigationConversationService()
        messages = await database_sync_to_async(service.get_messages)(self.session_id, limit=50, offset=0)

        await self._send_flow_message(
            {
                "type": "history",
                "messages": [
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "metadata": msg.metadata,
                        "created_at": msg.created_at.isoformat(),
                    }
                    for msg in messages
                ],
            }
        )

    @database_sync_to_async
    def _get_session(self, session_id: str) -> Any:
        from apps.litigation_ai.models import LitigationSession

        return LitigationSession.objects.filter(session_id=session_id).first()

    @database_sync_to_async
    def _add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> Any:
        from apps.litigation_ai.services import LitigationConversationService

        service = LitigationConversationService()
        session_id = self.session_id if self.session_id is not None else ""
        return service.add_message(session_id=session_id, role=role, content=content, metadata=metadata or {})

    @database_sync_to_async
    def _get_current_step(self, flow_service: Any) -> Any:
        return flow_service.get_current_step(self.session_id)

    # ============================================================
    # Agent 模式处理方法
    # ============================================================

    async def _handle_user_message_agent(self, content: str, metadata: dict[str, Any]) -> None:
        """
        使用 Agent 模式处理用户消息

        Args:
            content: 消息内容
            metadata: 消息元数据
        """
        try:
            # 流式回调
            async def stream_callback(chunk: str) -> None:
                await self._send_flow_message(
                    {
                        "type": "stream_chunk",
                        "content": chunk,
                    }
                )

            result = await self.agent_service.handle_message(
                session_id=self.session_id,
                case_id=self.session.case_id,  # type: ignore[union-attr]
                user_message=content,
                metadata=metadata,
                stream_callback=stream_callback,
            )

            # 发送完整响应
            await self._send_flow_message(result)

        except Exception as e:
            logger.error(f"Agent 处理消息失败: {e}", exc_info=True)
            await self._handle_agent_error(e)

    async def _handle_select_evidence_agent(
        self,
        evidence_item_ids: list[Any],
        our_evidence_item_ids: list[Any],
        opponent_evidence_item_ids: list[Any],
    ) -> None:
        """
        使用 Agent 模式处理证据选择

        Args:
            evidence_item_ids: 所有证据项 ID
            our_evidence_item_ids: 我方证据项 ID
            opponent_evidence_item_ids: 对方证据项 ID
        """
        try:
            result = await self.agent_service.handle_evidence_selection(
                session_id=self.session_id,
                case_id=self.session.case_id,  # type: ignore[union-attr]
                evidence_item_ids=evidence_item_ids,
                our_evidence_item_ids=our_evidence_item_ids,
                opponent_evidence_item_ids=opponent_evidence_item_ids,
            )

            await self._send_flow_message(result)

        except Exception as e:
            logger.error(f"Agent 处理证据选择失败: {e}", exc_info=True)
            await self._handle_agent_error(e)

    async def _handle_agent_error(self, error: Exception) -> None:
        """
        处理 Agent 错误

        Args:
            error: 异常对象
        """
        await self.send_error(error)
