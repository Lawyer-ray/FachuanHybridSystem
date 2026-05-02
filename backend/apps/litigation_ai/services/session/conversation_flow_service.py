"""Business logic services."""

import logging
from collections.abc import Callable
from typing import Any

from asgiref.sync import sync_to_async

from ..flow.flow_messenger import FlowMessenger
from ..flow.flow_state_machine import FlowStateMachine
from ..flow.session_repository import LitigationSessionRepository
from ..flow.types import ConversationStep, FlowContext

logger = logging.getLogger("apps.litigation_ai")


class ConversationFlowService:
    def __init__(self) -> None:
        self._conversation_service: Any | None = None
        self._session_repo: LitigationSessionRepository | None = None
        self._messenger: FlowMessenger | None = None
        self._state_machine: FlowStateMachine | None = None

    def _get_conversation_service(self) -> Any:
        if not self._conversation_service:
            from .conversation_service import ConversationService

            self._conversation_service = ConversationService()
        return self._conversation_service

    @property
    def session_repo(self) -> LitigationSessionRepository:
        if self._session_repo is None:
            self._session_repo = LitigationSessionRepository()
        return self._session_repo

    @property
    def messenger(self) -> FlowMessenger:
        if self._messenger is None:
            self._messenger = FlowMessenger(self._get_conversation_service())
        return self._messenger

    @property
    def state_machine(self) -> FlowStateMachine:
        if self._state_machine is None:
            self._state_machine = FlowStateMachine()
        return self._state_machine

    def get_current_step(self, session_id: str) -> ConversationStep:
        step_value = self.session_repo.get_step_value_sync(session_id)
        return self.state_machine.parse_step(step_value)

    def update_step(self, session_id: str, step: ConversationStep) -> None:
        self.session_repo.set_step_sync(session_id, step.value)

    async def _persist_message(
        self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        await self.messenger.persist_message(session_id=session_id, role=role, content=content, metadata=metadata)

    async def _send(
        self, send_callback: Callable[..., Any], payload: dict[str, Any], persist: bool, session_id: str, role: str
    ) -> None:
        await self.messenger.send(send_callback, payload, persist, session_id, role)

    async def handle_init(self, context: FlowContext, send_callback: Callable[..., Any]) -> None:
        service = self._get_conversation_service()
        recommended_types = await sync_to_async(service.get_recommended_document_types, thread_sensitive=True)(
            context.case_id
        )
        await self._persist_session_metadata(context.session_id, {"recommended_types": recommended_types})

        primary_document_type = self._choose_primary_document_type(recommended_types)
        need_doc_plan = (
            primary_document_type == "complaint"
            and "counterclaim_defense" in (recommended_types or [])
            and primary_document_type != "counterclaim_defense"
        )

        if need_doc_plan:
            await self._persist_session_metadata(
                context.session_id,
                {
                    "primary_document_type": primary_document_type,
                    "optional_document_types": ["counterclaim_defense"],
                },
            )
            message = await self._render_flow_text(
                "litigation_ai.flow.ask_counterclaim_defense",
                variables={
                    "primary_document_type": primary_document_type,
                    "optional_document_types": ["counterclaim_defense"],
                },
                fallback="检测到对方可能已提交反诉状.是否也需要生成反诉答辩状?可回复:要 / 不要 / 都要",
            )
            await self._send(
                send_callback,
                {
                    "type": "system_message",
                    "content": message,
                    "metadata": {
                        "recommended_types": recommended_types,
                        "primary_document_type": primary_document_type,
                    },
                },
                True,
                context.session_id,
                "system",
            )
            await sync_to_async(self.update_step, thread_sensitive=True)(context.session_id, ConversationStep.DOC_PLAN)
            return

        if len(recommended_types or []) == 1 and primary_document_type:
            await self._set_document_type(context.session_id, primary_document_type)
            message = await self._render_flow_text(
                "litigation_ai.flow.ask_goal",
                variables={"document_type": primary_document_type},
                fallback="请告诉我本次诉讼的目标是什么?",
            )
            await self._send(
                send_callback,
                {
                    "type": "system_message",
                    "content": message,
                    "metadata": {"recommended_types": recommended_types, "document_type": primary_document_type},
                },
                True,
                context.session_id,
                "system",
            )
            await sync_to_async(self.update_step, thread_sensitive=True)(
                context.session_id, ConversationStep.LITIGATION_GOAL
            )
            return

        message = await self._render_flow_text(
            "litigation_ai.flow.init",
            variables={"recommended_types": recommended_types},
            fallback=("您好!我是 AI 诉讼文书生成助手.\n\n请告诉我您要生成的文书类型(起诉状/答辩状/反诉状/反诉答辩状)."),
        )
        await self._send(
            send_callback,
            {"type": "system_message", "content": message, "metadata": {"recommended_types": recommended_types}},
            True,
            context.session_id,
            "system",
        )
        await sync_to_async(self.update_step, thread_sensitive=True)(context.session_id, ConversationStep.DOCUMENT_TYPE)

    async def handle_document_type_selection(
        self, context: FlowContext, document_type: str, send_callback: Callable[..., Any]
    ) -> None:
        valid_types = ["complaint", "defense", "counterclaim", "counterclaim_defense"]
        if document_type not in valid_types:
            await send_callback(
                {"type": "error", "message": f"无效的文书类型: {document_type}", "code": "INVALID_DOCUMENT_TYPE"}
            )
            return
        await self.session_repo.set_document_type(context.session_id, document_type)

        message = await self._render_flow_text(
            "litigation_ai.flow.ask_goal",
            variables={"document_type": document_type},
            fallback="请告诉我本次诉讼的目标是什么?",
        )
        await self._send(
            send_callback,
            {"type": "system_message", "content": message, "metadata": {"document_type": document_type}},
            True,
            context.session_id,
            "system",
        )
        await sync_to_async(self.update_step, thread_sensitive=True)(
            context.session_id, ConversationStep.LITIGATION_GOAL
        )

    async def handle_doc_plan_selection(
        self, context: FlowContext, user_input: str, send_callback: Callable[..., Any]
    ) -> None:
        session = await self.session_repo.get_session_or_raise(context.session_id)
        metadata = session.metadata or {}
        primary_document_type = metadata.get("primary_document_type") or "complaint"
        optional_document_types = metadata.get("optional_document_types") or ["counterclaim_defense"]

        from apps.litigation_ai.chains import UserChoiceParseChain

        parsed = await UserChoiceParseChain().arun(
            user_input=user_input,
            primary_document_type=primary_document_type,
            optional_document_types=list(optional_document_types),
        )

        valid_types = {"complaint", "defense", "counterclaim", "counterclaim_defense"}
        chosen_primary = parsed.primary_document_type or primary_document_type
        if chosen_primary not in valid_types:
            chosen_primary = primary_document_type
        pending = [x for x in (parsed.pending_document_types or []) if x in valid_types and x != chosen_primary]

        await self._set_document_type(context.session_id, chosen_primary)
        await self._persist_session_metadata(
            context.session_id, {"pending_document_types": pending, "doc_plan_notes": parsed.notes}
        )

        message = await self._render_flow_text(
            "litigation_ai.flow.ask_goal",
            variables={"document_type": chosen_primary},
            fallback="请告诉我本次诉讼的目标是什么?",
        )
        await self._send(
            send_callback,
            {"type": "system_message", "content": message, "metadata": {"document_type": chosen_primary}},
            True,
            context.session_id,
            "system",
        )
        await sync_to_async(self.update_step, thread_sensitive=True)(
            context.session_id, ConversationStep.LITIGATION_GOAL
        )

    async def handle_litigation_goal_collection(
        self, context: FlowContext, litigation_goal: str, send_callback: Callable[..., Any]
    ) -> None:
        session = await self.session_repo.get_session_or_raise(context.session_id)
        document_type = session.document_type or "complaint"
        case_info = await self._get_case_brief(context.case_id)

        from apps.litigation_ai.chains import LitigationGoalIntakeChain

        result = await LitigationGoalIntakeChain().arun(
            case_info=case_info,
            document_type=document_type,
            user_input=litigation_goal,
        )
        structured = result.model_dump() if hasattr(result, "model_dump") else result.dict()
        await self._persist_session_metadata(
            context.session_id,
            {"goal_raw": litigation_goal, "goal_structured": structured, "litigation_goal": result.goal_text},
        )

        if result.need_clarification:
            question = (
                result.clarifying_question or ""
            ).strip() or "为了准确起草,请补充一下关键诉讼请求要素(如金额/对象/期间等)."
            await self._send(
                send_callback,
                {"type": "system_message", "content": question, "metadata": {"need_clarification": True}},
                True,
                context.session_id,
                "system",
            )
            await sync_to_async(self.update_step, thread_sensitive=True)(
                context.session_id, ConversationStep.LITIGATION_GOAL
            )
            return

        message = await self._render_flow_text(
            "litigation_ai.flow.ask_evidence",
            variables={},
            fallback="请选择需要提交给我分析的证据材料.如果没有证据材料,可以直接回复「无」或「跳过」.",
        )
        await self._send(
            send_callback,
            {"type": "system_message", "content": message, "metadata": {}},
            True,
            context.session_id,
            "system",
        )
        await sync_to_async(self.update_step, thread_sensitive=True)(
            context.session_id, ConversationStep.EVIDENCE_SELECTION
        )

    async def handle_evidence_selection(
        self,
        context: FlowContext,
        evidence_list_ids: list[int],
        evidence_item_ids: list[int],
        our_evidence_item_ids: list[int],
        opponent_evidence_item_ids: list[int],
        send_callback: Callable[..., Any],
    ) -> None:
        await self._persist_session_metadata(
            context.session_id,
            {
                "evidence_list_ids": evidence_list_ids,
                "evidence_item_ids": evidence_item_ids,
                "our_evidence_item_ids": our_evidence_item_ids,
                "opponent_evidence_item_ids": opponent_evidence_item_ids,
            },
        )

        await self._send(
            send_callback,
            {"type": "system_message", "content": "好的,正在生成文书内容,请稍候...", "metadata": {}},
            True,
            context.session_id,
            "system",
        )
        await sync_to_async(self.update_step, thread_sensitive=True)(context.session_id, ConversationStep.GENERATING)
        await self.handle_generation(context, send_callback)

    async def handle_generation(self, context: FlowContext, send_callback: Callable[..., Any]) -> None:
        session = await self.session_repo.get_session_or_raise(context.session_id)
        metadata = session.metadata or {}
        litigation_goal = metadata.get("litigation_goal", "") or (metadata.get("goal_raw", "") or "")
        goal_structured = metadata.get("goal_structured")
        if goal_structured:
            import json

            litigation_goal = "\n".join(
                [
                    litigation_goal,
                    "",
                    "# 结构化诉讼目标",
                    json.dumps(goal_structured, ensure_ascii=False),
                ]
            ).strip()
        document_type = session.document_type or "complaint"
        evidence_list_ids = metadata.get("evidence_list_ids") or []
        evidence_item_ids = metadata.get("evidence_item_ids") or []
        our_evidence_item_ids = metadata.get("our_evidence_item_ids") or []
        opponent_evidence_item_ids = metadata.get("opponent_evidence_item_ids") or []

        from ..generation.draft_service import LitigationDraftService

        draft_service = LitigationDraftService()

        try:
            result = await draft_service.generate_draft_async(
                case_id=context.case_id,
                session_id=context.session_id,
                document_type=document_type,
                litigation_goal=litigation_goal,
                evidence_list_ids=evidence_list_ids,
                evidence_item_ids=evidence_item_ids,
                our_evidence_item_ids=our_evidence_item_ids,
                opponent_evidence_item_ids=opponent_evidence_item_ids,
                stream_callback=None,
            )
        except Exception as e:
            import openai

            from apps.core.llm.config import LLMConfig

            # 记录详细错误信息到控制台
            logger.error(f"[AI诉状生成] 生成失败: {type(e).__name__}: {e}")
            api_key = await LLMConfig.get_api_key_async()
            base_url = await LLMConfig.get_base_url_async()
            default_model = await LLMConfig.get_default_model_async()
            logger.error(f"[AI诉状生成] 当前配置 - API Key 已配置: {bool(api_key)}")
            logger.error(f"[AI诉状生成] 当前配置 - Base URL: {base_url}")
            logger.error(f"[AI诉状生成] 当前配置 - Model: {default_model}")

            if isinstance(e, openai.AuthenticationError):
                msg = "\n".join(
                    [
                        "⚠️ 大模型鉴权失败(401 Invalid token),已中断生成.",
                        "",
                        "请到 /admin/core/systemconfig/ 检查以下配置是否正确且启用:",
                        "- SILICONFLOW_API_KEY:不要保存成“Bearer xxx”,只填 token 本体;也不要填 **** 掩码",
                        f"- SILICONFLOW_BASE_URL:当前读取值为 {base_url}",
                        f"- SILICONFLOW_DEFAULT_MODEL:当前读取值为 {default_model}",
                        "",
                        "修复后可回复「重试」或再次回复「无」继续生成.",
                    ]
                )
                await self._send(
                    send_callback,
                    {"type": "system_message", "content": msg, "metadata": {"step": ConversationStep.GENERATING.value}},
                    True,
                    context.session_id,
                    "system",
                )
                await sync_to_async(self.update_step, thread_sensitive=True)(
                    context.session_id, ConversationStep.EVIDENCE_SELECTION
                )
                return
            raise

        await send_callback(
            {
                "type": "assistant_complete",
                "content": result["display_text"],
                "metadata": {
                    "step": ConversationStep.GENERATING.value,
                    "model": result.get("model"),
                    "token_usage": result.get("token_usage", {}),
                },
            }
        )
        await self._persist_message(
            context.session_id,
            "assistant",
            result["display_text"],
            metadata={"draft": result.get("draft", {}), "step": ConversationStep.GENERATING.value},
        )

        await self._send(
            send_callback,
            {
                "type": "system_message",
                "content": "✅ 生成完成!您可以:\n\n1) 回复「确认」生成正式文档\n2) 提出修改意见,我会帮您调整内容",
                "metadata": {},
            },
            True,
            context.session_id,
            "system",
        )
        await sync_to_async(self.update_step, thread_sensitive=True)(context.session_id, ConversationStep.REFINING)

    async def handle_refining(
        self, context: FlowContext, user_feedback: str, send_callback: Callable[..., Any]
    ) -> None:
        session = await self.session_repo.get_session_or_raise(context.session_id)
        metadata = session.metadata or {}
        pending = list(metadata.get("pending_document_types") or [])
        user_text = (user_feedback or "").strip()
        if pending and user_text in ["继续", "下一份", "下一个", "继续生成"]:
            next_doc = pending.pop(0)
            await self._set_document_type(context.session_id, next_doc)
            await self._persist_session_metadata(context.session_id, {"pending_document_types": pending})
            message = await self._render_flow_text(
                "litigation_ai.flow.ask_goal",
                variables={"document_type": next_doc},
                fallback="请告诉我本次诉讼的目标是什么?",
            )
            await self._send(
                send_callback,
                {"type": "system_message", "content": message, "metadata": {"document_type": next_doc}},
                True,
                context.session_id,
                "system",
            )
            await sync_to_async(self.update_step, thread_sensitive=True)(
                context.session_id, ConversationStep.LITIGATION_GOAL
            )
            return

        await self._send(
            send_callback,
            {
                "type": "system_message",
                "content": "修改完善暂未实现.若要继续生成下一份文书,请回复「继续」.",
                "metadata": {},
            },
            True,
            context.session_id,
            "system",
        )

    async def handle_confirm_generate(self, context: FlowContext, send_callback: Callable[..., Any]) -> None:
        await self._send(
            send_callback,
            {"type": "system_message", "content": "请在页面点击“生成文档”按钮生成并下载.", "metadata": {}},
            True,
            context.session_id,
            "system",
        )

    def _choose_primary_document_type(self, recommended_types: list[str]) -> str:
        if "complaint" in (recommended_types or []):
            return "complaint"
        if "defense" in (recommended_types or []):
            return "defense"
        return (recommended_types or ["complaint"])[0]

    async def _set_document_type(self, session_id: str, document_type: str) -> None:
        await self.session_repo.set_document_type(session_id, document_type)

    async def _persist_session_metadata(self, session_id: str, updates: dict[str, Any]) -> None:
        await self.session_repo.update_metadata_or_raise(session_id, updates or {})

    async def _get_case_brief(self, case_id: int) -> dict[str, Any]:
        from ..wiring import get_case_service

        @sync_to_async(thread_sensitive=True)
        def load() -> dict[str, Any]:
            case = get_case_service().get_case_internal(case_id)
            return {
                "case_name": case.name if case else "",
                "cause_of_action": (case.cause_of_action or "") if case else "",
                "target_amount": str(case.target_amount or "") if case else "",
            }

        return await load()

    async def _render_flow_text(self, name: str, variables: dict[str, Any], fallback: str) -> str:
        from asgiref.sync import sync_to_async

        from ..generation.prompt_template_service import PromptTemplateService

        service = PromptTemplateService()
        template = await sync_to_async(service.get_system_template, thread_sensitive=True)(name)
        if not template:
            return fallback
        return service.replace_variables(template, variables or {})
