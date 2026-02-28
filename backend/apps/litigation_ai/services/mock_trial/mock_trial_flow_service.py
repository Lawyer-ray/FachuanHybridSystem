"""模拟庭审主流程服务（状态机驱动）."""

import logging
from collections.abc import Callable
from typing import Any

from asgiref.sync import sync_to_async

from apps.litigation_ai.models.choices import MockTrialMode
from apps.litigation_ai.services.flow.flow_messenger import FlowMessenger
from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

from .types import MockTrialContext, MockTrialStep

logger = logging.getLogger("apps.litigation_ai")


class MockTrialFlowService:
    """模拟庭审主流程."""

    def __init__(self) -> None:
        self._conversation_service: Any | None = None
        self._session_repo: LitigationSessionRepository | None = None
        self._messenger: FlowMessenger | None = None

    def _get_conversation_service(self) -> Any:
        if not self._conversation_service:
            from apps.litigation_ai.services.conversation_service import ConversationService
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

    def parse_step(self, step_value: str | None) -> MockTrialStep:
        if not step_value:
            return MockTrialStep.INIT
        try:
            return MockTrialStep(step_value)
        except ValueError:
            return MockTrialStep.INIT

    def get_current_step(self, session_id: str) -> MockTrialStep:
        return self.parse_step(self.session_repo.get_step_value_sync(session_id))

    async def _send(
        self, send_cb: Callable[..., Any], payload: dict[str, Any], persist: bool, session_id: str, role: str
    ) -> None:
        await self.messenger.send(send_cb, payload, persist, session_id, role)

    # ---- INIT ----

    async def handle_init(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:
        case_info = await self._get_case_brief(ctx.case_id)
        case_name = case_info.get("case_name", "")
        cause = case_info.get("cause_of_action", "")

        msg = (
            f"⚖️ 模拟庭审 — {case_name}\n"
            f"案由：{cause or '未设置'}\n\n"
            "请选择模拟模式：\n"
            "1️⃣ 法官视角分析 — AI 扮演法官，分析争议焦点、证据强弱、胜诉概率\n"
            "2️⃣ 质证模拟 — AI 扮演对方律师，逐一质证您的证据\n"
            "3️⃣ 辩论模拟 — AI 扮演对方律师，围绕争议焦点进行多轮辩论\n\n"
            "请回复数字（1/2/3）或模式名称。"
        )
        await self._send(
            send_cb,
            {"type": "system_message", "content": msg, "metadata": {"case_info": case_info}},
            True, ctx.session_id, "system",
        )
        await self._set_step(ctx.session_id, MockTrialStep.MODE_SELECT)

    # ---- MODE_SELECT ----

    async def handle_mode_select(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:
        mode = self._parse_mode(user_input)
        if not mode:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "未识别模式，请回复 1（法官视角）、2（质证模拟）或 3（辩论模拟）。"},
                False, ctx.session_id, "system",
            )
            return

        await self.session_repo.update_metadata(ctx.session_id, {"mock_trial_mode": mode})

        if mode == MockTrialMode.JUDGE:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "🔍 正在以法官视角分析案件，请稍候...", "metadata": {"mode": mode}},
                True, ctx.session_id, "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SIMULATION)
            await self._run_judge_analysis(ctx, send_cb)
        elif mode == MockTrialMode.CROSS_EXAM:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "📋 质证模拟 — 正在加载证据清单...", "metadata": {"mode": mode}},
                True, ctx.session_id, "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SIMULATION)
            await self._start_cross_exam(ctx, send_cb)
        elif mode == MockTrialMode.DEBATE:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "💬 辩论模拟 — 正在归纳争议焦点...", "metadata": {"mode": mode}},
                True, ctx.session_id, "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.FOCUS_ANALYSIS)
            await self._start_debate_focus(ctx, send_cb)

    # ---- SIMULATION dispatchers ----

    async def handle_simulation(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:
        metadata = await self.session_repo.get_metadata(ctx.session_id)
        mode = metadata.get("mock_trial_mode", "")

        if mode == MockTrialMode.CROSS_EXAM:
            await self._handle_cross_exam_response(ctx, user_input, send_cb)
        elif mode == MockTrialMode.DEBATE:
            await self._handle_debate_turn(ctx, user_input, send_cb)
        else:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "分析已完成。如需重新选择模式，请新建会话。"},
                False, ctx.session_id, "system",
            )

    # ---- Judge perspective ----

    async def _run_judge_analysis(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:
        from .judge_perspective_service import JudgePerspectiveService

        try:
            result = await JudgePerspectiveService().generate_analysis(
                case_id=ctx.case_id, session_id=ctx.session_id
            )
            report = result["report"]
            display = self._format_judge_report(report)

            await send_cb({
                "type": "assistant_complete",
                "content": display,
                "metadata": {"report": report, "model": result.get("model"), "token_usage": result.get("token_usage")},
            })
            await self.messenger.persist_message(ctx.session_id, "assistant", display, {"report": report})

            await self._send(
                send_cb,
                {"type": "system_message", "content": "✅ 法官视角分析完成。您可以针对某个焦点追问，或新建会话尝试其他模式。"},
                True, ctx.session_id, "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)
        except Exception as e:
            logger.error(f"法官视角分析失败: {e}", exc_info=True)
            await self._send(
                send_cb,
                {"type": "error", "message": f"分析失败：{e}", "code": "JUDGE_ANALYSIS_FAILED"},
                False, ctx.session_id, "system",
            )

    def _format_judge_report(self, report: dict[str, Any]) -> str:
        lines: list[str] = ["# ⚖️ 法官视角分析报告\n"]

        focuses = report.get("dispute_focuses", [])
        if focuses:
            lines.append("## 争议焦点\n")
            for i, f in enumerate(focuses, 1):
                lines.append(f"**焦点{i}：{f.get('description', '')}**")
                lines.append(f"- 类型：{f.get('focus_type', '')}")
                lines.append(f"- 原告立场：{f.get('plaintiff_position', '')}")
                lines.append(f"- 被告可能立场：{f.get('defendant_position', '')}")
                lines.append(f"- 举证责任：{f.get('burden_of_proof', '')}")
                evidence = f.get("key_evidence", [])
                if evidence:
                    lines.append(f"- 关键证据：{'、'.join(evidence)}")
                lines.append("")

        comparisons = report.get("evidence_strength_comparison", [])
        if comparisons:
            lines.append("## 证据强弱对比\n")
            for c in comparisons:
                lines.append(f"**{c.get('focus', '')}**")
                lines.append(f"- 原告证据：{c.get('plaintiff_strength', '')} | 被告证据：{c.get('defendant_strength', '')}")
                lines.append(f"- 分析：{c.get('analysis', '')}")
                lines.append("")

        questions = report.get("judge_questions", [])
        if questions:
            lines.append("## 法官可能提问\n")
            for q in questions:
                lines.append(f"- {q}")
            lines.append("")

        lines.append(f"## 风险评估\n\n{report.get('risk_assessment', '')}\n")
        lines.append(f"## 胜诉概率\n\n{report.get('overall_win_probability', '')}\n")
        lines.append(f"## 建议策略\n\n{report.get('recommended_strategy', '')}")

        return "\n".join(lines)

    # ---- Cross exam stubs (Task 8 实现) ----

    async def _start_cross_exam(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:
        await self._send(
            send_cb,
            {"type": "system_message", "content": "⚠️ 质证模拟功能开发中，敬请期待。"},
            True, ctx.session_id, "system",
        )
        await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)

    async def _handle_cross_exam_response(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:
        pass

    # ---- Debate stubs (Task 9 实现) ----

    async def _start_debate_focus(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:
        await self._send(
            send_cb,
            {"type": "system_message", "content": "⚠️ 辩论模拟功能开发中，敬请期待。"},
            True, ctx.session_id, "system",
        )
        await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)

    async def _handle_debate_turn(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:
        pass

    # ---- Helpers ----

    def _parse_mode(self, user_input: str) -> str | None:
        text = (user_input or "").strip()
        mapping: dict[str, str] = {
            "1": MockTrialMode.JUDGE,
            "法官": MockTrialMode.JUDGE,
            "法官视角": MockTrialMode.JUDGE,
            "2": MockTrialMode.CROSS_EXAM,
            "质证": MockTrialMode.CROSS_EXAM,
            "质证模拟": MockTrialMode.CROSS_EXAM,
            "3": MockTrialMode.DEBATE,
            "辩论": MockTrialMode.DEBATE,
            "辩论模拟": MockTrialMode.DEBATE,
        }
        return mapping.get(text)

    async def _set_step(self, session_id: str, step: MockTrialStep) -> None:
        await self.session_repo.set_step(session_id, step.value)

    async def _get_case_brief(self, case_id: int) -> dict[str, Any]:
        from apps.litigation_ai.services.context_service import LitigationContextService

        return await sync_to_async(
            LitigationContextService().get_case_info_for_agent, thread_sensitive=True
        )(case_id)
