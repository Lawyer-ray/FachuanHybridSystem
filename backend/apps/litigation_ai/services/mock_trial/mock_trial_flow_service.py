"""模拟庭审主流程服务（状态机驱动）."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from asgiref.sync import sync_to_async

from apps.litigation_ai.models.choices import MockTrialMode
from apps.litigation_ai.services.flow.flow_messenger import FlowMessenger
from apps.litigation_ai.services.flow.session_repository import LitigationSessionRepository

# S23-15（2026-11-23 二轮审计）：Markdown 排版与配置解析已按关注点拆到
# `presentation.py` / `adversarial_config.py`，本模块只留「状态机 + I/O 编排」。
from .adversarial_config import parse_adversarial_config
from .presentation import (
    build_evidence_menu_message,
    build_init_message,
    build_model_config_message,
    format_adversarial_report,
    format_cross_exam_opinion,
    format_debate_focuses,
    format_judge_report,
)
from .types import MockTrialContext, MockTrialStep

if TYPE_CHECKING:
    from .types import AdversarialConfig

logger = logging.getLogger("apps.litigation_ai")


# ── 模块级纯函数 ────────────────────────────────────────────


def parse_mode(user_input: str) -> str | None:
    """解析用户输入的模拟庭审模式。"""
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
        "4": MockTrialMode.ADVERSARIAL,
        "对抗": MockTrialMode.ADVERSARIAL,
        "多agent对抗": MockTrialMode.ADVERSARIAL,
        "多agent": MockTrialMode.ADVERSARIAL,
    }
    return mapping.get(text)


class MockTrialFlowService:
    """模拟庭审主流程."""

    def __init__(self) -> None:
        self._conversation_service: Any | None = None
        self._session_repo: LitigationSessionRepository | None = None
        self._messenger: FlowMessenger | None = None
        self._adversarial_services: dict[str, Any] = {}  # session_id → AdversarialTrialService

    def _get_conversation_service(self) -> Any:
        if not self._conversation_service:
            from apps.litigation_ai.services.session.conversation_service import ConversationService

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
    ) -> None:  # pragma: no cover
        await self.messenger.send(send_cb, payload, persist, session_id, role)

    # ---- INIT ----

    async def handle_init(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:  # pragma: no cover
        case_info = await self._get_case_brief(ctx.case_id)
        case_name = case_info.get("case_name", "")
        cause = case_info.get("cause_of_action", "")

        msg = build_init_message(case_name, cause)
        await self._send(
            send_cb,
            {"type": "system_message", "content": msg, "metadata": {"case_info": case_info}},
            True,
            ctx.session_id,
            "system",
        )
        await self._set_step(ctx.session_id, MockTrialStep.MODE_SELECT)

    # ---- MODE_SELECT ----

    async def handle_mode_select(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        mode = self._parse_mode(user_input)
        if not mode:
            await self._send(
                send_cb,
                {
                    "type": "system_message",
                    "content": "未识别模式，请回复 1（法官视角）、2（质证模拟）、3（辩论模拟）或 4（多Agent对抗）。",
                },
                False,
                ctx.session_id,
                "system",
            )
            return

        await self.session_repo.update_metadata(ctx.session_id, {"mock_trial_mode": mode})

        if mode == MockTrialMode.ADVERSARIAL:
            await self._send_model_config_prompt(ctx, send_cb)
            return

        if mode == MockTrialMode.JUDGE:
            await self._send(
                send_cb,
                {
                    "type": "system_message",
                    "content": "🔍 正在以法官视角分析案件，请稍候...",
                    "metadata": {"mode": mode},
                },
                True,
                ctx.session_id,
                "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SIMULATION)
            await self._run_judge_analysis(ctx, send_cb)
        elif mode == MockTrialMode.CROSS_EXAM:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "📋 质证模拟 — 正在加载证据清单...", "metadata": {"mode": mode}},
                True,
                ctx.session_id,
                "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SIMULATION)
            await self._start_cross_exam(ctx, send_cb)
        elif mode == MockTrialMode.DEBATE:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "💬 辩论模拟 — 正在归纳争议焦点...", "metadata": {"mode": mode}},
                True,
                ctx.session_id,
                "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.FOCUS_ANALYSIS)
            await self._start_debate_focus(ctx, send_cb)

    # ---- SIMULATION dispatchers ----

    async def handle_simulation(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        metadata = await self.session_repo.get_metadata(ctx.session_id)
        mode = metadata.get("mock_trial_mode", "")

        if mode == MockTrialMode.ADVERSARIAL:
            await self._handle_adversarial_input(ctx, user_input, send_cb)
        elif mode == MockTrialMode.CROSS_EXAM:
            await self._handle_cross_exam_response(ctx, user_input, send_cb)
        elif mode == MockTrialMode.DEBATE:
            await self._handle_debate_turn(ctx, user_input, send_cb)
        else:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "分析已完成。如需重新选择模式，请新建会话。"},
                False,
                ctx.session_id,
                "system",
            )

    # ---- Judge perspective ----

    async def _run_judge_analysis(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:  # pragma: no cover
        from .judge_perspective_service import JudgePerspectiveService

        try:
            result = await JudgePerspectiveService().generate_analysis(case_id=ctx.case_id, session_id=ctx.session_id)
            report = result["report"]
            display = self._format_judge_report(report)

            await send_cb(
                {
                    "type": "assistant_complete",
                    "content": display,
                    "metadata": {
                        "report": report,
                        "model": result.get("model"),
                        "token_usage": result.get("token_usage"),
                    },
                }
            )
            await self.messenger.persist_message(ctx.session_id, "assistant", display, {"report": report})

            await self._send(
                send_cb,
                {
                    "type": "system_message",
                    "content": "✅ 法官视角分析完成。您可以针对某个焦点追问，或新建会话尝试其他模式。",
                },
                True,
                ctx.session_id,
                "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)
        except Exception as e:
            logger.exception("法官视角分析失败: %s", e)
            await self._send(
                send_cb,
                {"type": "error", "message": f"分析失败：{e}", "code": "JUDGE_ANALYSIS_FAILED"},
                False,
                ctx.session_id,
                "system",
            )

    def _format_judge_report(self, report: dict[str, Any]) -> str:
        return format_judge_report(report)

    # ---- Cross exam ----

    async def _start_cross_exam(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:  # pragma: no cover
        from .cross_exam_service import CrossExamService

        svc = CrossExamService()
        evidence_list = await svc.load_evidence_list(ctx.case_id)
        if not evidence_list:
            await self._send(
                send_cb,
                {"type": "system_message", "content": "⚠️ 本案暂无证据，无法进行质证模拟。请先上传证据。"},
                True,
                ctx.session_id,
                "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)
            return

        await self.session_repo.update_metadata(
            ctx.session_id,
            {
                "cross_exam_evidence": evidence_list,
                "cross_exam_index": 0,
                "cross_exam_results": [],
            },
        )

        await self._send_evidence_menu(ctx, send_cb, evidence_list, 0)

    async def _send_evidence_menu(
        self,
        ctx: MockTrialContext,
        send_cb: Callable[..., Any],
        evidence_list: list[dict[str, Any]],
        current_index: int,
    ) -> None:  # pragma: no cover
        total = len(evidence_list)
        ev = evidence_list[current_index]
        await self._send(
            send_cb,
            {"type": "system_message", "content": build_evidence_menu_message(ev, current_index, total)},
            True,
            ctx.session_id,
            "system",
        )

        # 发送进度更新
        await send_cb(
            {
                "type": "progress",
                "current": current_index + 1,
                "total": total,
                "percentage": int((current_index + 1) * 100 / total),
                "message": f"正在分析证据 {current_index + 1}/{total}: {ev.get('name', '未命名')}",
            }
        )

        from .cross_exam_service import CrossExamService

        case_info = await self._get_case_brief(ctx.case_id)
        try:
            result = await CrossExamService().examine_single(case_info=case_info, evidence_info=ev)
            opinion = result.opinion
            display = self._format_cross_exam_opinion(ev, opinion)

            metadata = await self.session_repo.get_metadata(ctx.session_id)
            results = metadata.get("cross_exam_results", [])
            results.append({"evidence_name": ev.get("name", ""), "opinion": opinion})
            await self.session_repo.update_metadata(ctx.session_id, {"cross_exam_results": results})

            await send_cb({"type": "assistant_complete", "content": display, "metadata": {"opinion": opinion}})
            await self.messenger.persist_message(ctx.session_id, "assistant", display, {"opinion": opinion})

            if current_index + 1 < total:
                await self._send(
                    send_cb,
                    {
                        "type": "system_message",
                        "content": "回复 **下一份** 继续质证下一份证据，或回复 **跳过** 跳过剩余证据生成总结。",
                    },
                    False,
                    ctx.session_id,
                    "system",
                )
            else:
                await self._finish_cross_exam(ctx, send_cb)
        except Exception as e:
            logger.exception("质证分析失败: %s", e)
            await self._send(
                send_cb,
                {"type": "error", "message": f"质证分析失败：{e}", "code": "CROSS_EXAM_FAILED"},
                False,
                ctx.session_id,
                "system",
            )

    def _format_cross_exam_opinion(self, ev: dict[str, Any], opinion: dict[str, Any]) -> str:
        return format_cross_exam_opinion(ev, opinion)

    async def _handle_cross_exam_response(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        text = (user_input or "").strip()
        metadata = await self.session_repo.get_metadata(ctx.session_id)
        evidence_list = metadata.get("cross_exam_evidence", [])
        current_index = metadata.get("cross_exam_index", 0)

        if text in ("跳过", "skip", "结束"):
            await self._finish_cross_exam(ctx, send_cb)
            return

        next_index = current_index + 1
        if next_index >= len(evidence_list):
            await self._finish_cross_exam(ctx, send_cb)
            return

        await self.session_repo.update_metadata(ctx.session_id, {"cross_exam_index": next_index})
        await self._send_evidence_menu(ctx, send_cb, evidence_list, next_index)

    async def _finish_cross_exam(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:  # pragma: no cover
        metadata = await self.session_repo.get_metadata(ctx.session_id)
        results = metadata.get("cross_exam_results", [])
        total = len(results)
        high = sum(1 for r in results if r.get("opinion", {}).get("risk_level") == "high")
        medium = sum(1 for r in results if r.get("opinion", {}).get("risk_level") == "medium")

        summary = (
            f"✅ 质证模拟完成，共质证 {total} 份证据。\n"
            f"- 🔴 高风险：{high} 份\n"
            f"- 🟡 中风险：{medium} 份\n"
            f"- 🟢 低风险：{total - high - medium} 份\n\n"
            "建议重点关注高风险证据，准备充分的回应策略。"
        )
        await self._send(send_cb, {"type": "system_message", "content": summary}, True, ctx.session_id, "system")
        await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)

    # ---- Debate ----

    async def _start_debate_focus(self, ctx: MockTrialContext, send_cb: Callable[..., Any]) -> None:  # pragma: no cover
        from .debate_service import DebateService

        case_info = await self._get_case_brief(ctx.case_id)
        evidence_text = await self._get_evidence_text(ctx.case_id)

        try:
            result = await DebateService().analyze_focuses(case_info=case_info, evidence_text=evidence_text)
            focuses = result.focuses
            if not focuses:
                await self._send(
                    send_cb,
                    {"type": "system_message", "content": "⚠️ 未能归纳出争议焦点，请确认案件信息和证据是否完整。"},
                    True,
                    ctx.session_id,
                    "system",
                )
                await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)
                return

            await self.session_repo.update_metadata(
                ctx.session_id,
                {
                    "debate_focuses": focuses,
                    "debate_history": [],
                    "debate_selected_focus": None,
                },
            )

            await self._send(
                send_cb,
                {
                    "type": "system_message",
                    "content": format_debate_focuses(focuses),
                    "metadata": {"focuses": focuses},
                },
                True,
                ctx.session_id,
                "system",
            )
            await self._set_step(ctx.session_id, MockTrialStep.SIMULATION)
        except Exception as e:
            logger.exception("争议焦点归纳失败: %s", e)
            await self._send(
                send_cb,
                {"type": "error", "message": f"争议焦点归纳失败：{e}", "code": "FOCUS_ANALYSIS_FAILED"},
                False,
                ctx.session_id,
                "system",
            )

    async def _handle_debate_turn(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        from .debate_service import DebateService

        metadata = await self.session_repo.get_metadata(ctx.session_id)
        focuses = metadata.get("debate_focuses", [])
        selected = metadata.get("debate_selected_focus")
        history: list[dict[str, str]] = metadata.get("debate_history", [])
        text = (user_input or "").strip()

        if text in ("结束", "end", "结束辩论"):
            await self._finish_debate(ctx, send_cb, history)
            return

        # 尚未选择焦点 → 解析编号
        if selected is None:
            try:
                idx = int(text) - 1
                if 0 <= idx < len(focuses):
                    selected = focuses[idx]
                    await self.session_repo.update_metadata(ctx.session_id, {"debate_selected_focus": selected})
                    await self._send(
                        send_cb,
                        {
                            "type": "system_message",
                            "content": f"已选择焦点：**{selected.get('description', '')}**\n\n请发表您的第一轮论点。回复 **结束** 可结束辩论。",
                        },
                        True,
                        ctx.session_id,
                        "system",
                    )
                    return
                else:
                    await self._send(
                        send_cb,
                        {"type": "system_message", "content": f"请输入 1-{len(focuses)} 之间的编号。"},
                        False,
                        ctx.session_id,
                        "system",
                    )
                    return
            except ValueError:
                await self._send(
                    send_cb,
                    {"type": "system_message", "content": "请输入焦点编号（数字）。"},
                    False,
                    ctx.session_id,
                    "system",
                )
                return

        # 已选择焦点 → 进行辩论
        history.append({"role": "user", "content": text})
        case_info = await self._get_case_brief(ctx.case_id)

        # 获取设置的难度
        metadata = await self.session_repo.get_metadata(ctx.session_id)
        difficulty = metadata.get("debate_difficulty", "medium")

        try:
            result = await DebateService().debate_turn(
                case_info=case_info,
                focus=selected,
                user_argument=text,
                history=history,
                difficulty=difficulty,
            )
            rebuttal = result.rebuttal
            history.append({"role": "opponent", "content": rebuttal})
            await self.session_repo.update_metadata(ctx.session_id, {"debate_history": history})

            display = f"**对方律师反驳：**\n\n{rebuttal}"
            await send_cb({"type": "assistant_complete", "content": display})
            await self.messenger.persist_message(ctx.session_id, "assistant", display)

            round_num = len([h for h in history if h["role"] == "user"])
            await self._send(
                send_cb,
                {
                    "type": "system_message",
                    "content": f"第 {round_num} 轮辩论完成。请继续发表论点，或回复 **结束** 结束辩论。",
                },
                False,
                ctx.session_id,
                "system",
            )
        except Exception as e:
            logger.exception("辩论回合失败: %s", e)
            await self._send(
                send_cb,
                {"type": "error", "message": f"辩论回合失败：{e}", "code": "DEBATE_TURN_FAILED"},
                False,
                ctx.session_id,
                "system",
            )

    async def _finish_debate(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any], history: list[dict[str, str]]
    ) -> None:  # pragma: no cover
        rounds = len([h for h in history if h["role"] == "user"])
        summary = f"✅ 辩论模拟结束，共进行 {rounds} 轮辩论。\n\n建议回顾对方的反驳要点，完善己方论证。"
        await self._send(send_cb, {"type": "system_message", "content": summary}, True, ctx.session_id, "system")
        await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)

    async def _get_evidence_text(self, case_id: int) -> str:  # pragma: no cover
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService
        from apps.litigation_ai.services.session.context_service import LitigationContextService

        raw = await sync_to_async(LitigationContextService().get_evidence_list_for_agent, thread_sensitive=True)(
            case_id
        )
        if not raw:
            return ""
        # S23-13（2026-11-23 二轮审计）：原实现读 `e["list_id"]`（documents.EvidenceList 的键），
        # 而 `get_evidence_list_for_agent` 返回的每项只有 `evidence_item_id`，因此候选 id 恒为空、
        # `build_evidence_text` 的 RAG 分支永不命中，只剩「名称 + 证明目的」兜底。
        # 现在改读 `evidence_item_id` 并按证据项 id 构建摘要（页码/用途都来自证据项本身）。
        evidence_item_ids: list[int] = [int(e["evidence_item_id"]) for e in raw if e.get("evidence_item_id")]
        if not evidence_item_ids:
            return "\n".join([f"- {e.get('name', '未命名')}: {e.get('description', '')}" for e in raw])
        result = await sync_to_async(EvidenceDigestService().build_evidence_text, thread_sensitive=True)(
            evidence_list_ids=[], evidence_item_ids=evidence_item_ids
        )
        return result

    # ---- Helpers ----

    def _parse_mode(self, user_input: str) -> str | None:
        return parse_mode(user_input)

    async def _set_step(self, session_id: str, step: MockTrialStep) -> None:  # pragma: no cover
        await self.session_repo.set_step(session_id, step.value)

    async def _get_case_brief(self, case_id: int) -> dict[str, Any]:  # pragma: no cover
        from apps.litigation_ai.services.session.context_service import LitigationContextService

        result = await sync_to_async(LitigationContextService().get_case_info_for_agent, thread_sensitive=True)(case_id)
        return result

    # ── 多 Agent 对抗 ──

    async def _send_model_config_prompt(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        """发送模型配置提示."""
        from apps.core.llm.config import LLMConfig

        models = LLMConfig.DEFAULT_AVAILABLE_MODELS[:10]  # 取前 10 个
        msg = build_model_config_message(models)
        await self._send(
            send_cb,
            {"type": "system_message", "content": msg, "metadata": {"available_models": models}},
            True,
            ctx.session_id,
            "system",
        )
        await self._set_step(ctx.session_id, MockTrialStep.MODEL_CONFIG)

    async def handle_model_config(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        """解析用户的模型配置并启动对抗庭审."""
        from apps.core.llm.config import LLMConfig

        from .adversarial_service import AdversarialTrialService
        from .types import AdversarialConfig

        models = LLMConfig.DEFAULT_AVAILABLE_MODELS[:10]
        text = (user_input or "").strip()

        # 快捷默认
        if text in ("默认", "default", "开始"):
            config = AdversarialConfig()
        else:
            config = self._parse_adversarial_config(text, models)

        await self.session_repo.update_metadata(
            ctx.session_id,
            {
                "adversarial_config": {
                    "plaintiff_model": config.plaintiff_model,
                    "defendant_model": config.defendant_model,
                    "judge_model": config.judge_model,
                    "debate_rounds": config.debate_rounds,
                    "user_role": config.user_role,
                }
            },
        )

        level_label = {"first": "一审", "second": "二审"}.get(config.trial_level, "一审")
        role_label = {"plaintiff": "原告律师", "defendant": "被告律师", "judge": "审判长", "observer": "观看模式"}.get(
            config.user_role, "观看模式"
        )
        await self._send(
            send_cb,
            {
                "type": "system_message",
                "content": (
                    f"✅ 配置完成！\n"
                    f"- 审级：{level_label}\n"
                    f"- 原告模型：{config.plaintiff_model or '默认'}\n"
                    f"- 被告模型：{config.defendant_model or '默认'}\n"
                    f"- 法官模型：{config.judge_model or '默认'}\n"
                    f"- 辩论轮数：{config.debate_rounds}\n"
                    f"- 您的角色：{role_label}\n\n"
                    "🔔 庭审即将开始..."
                ),
            },
            True,
            ctx.session_id,
            "system",
        )

        # 加载案件信息和证据
        case_info = await self._get_case_brief(ctx.case_id)
        evidence_text = await self._get_evidence_text(ctx.case_id)

        # 创建服务实例并缓存
        service = AdversarialTrialService(config, case_info, evidence_text)
        self._adversarial_services[ctx.session_id] = service

        # 启动庭审
        await service.run_full_trial(ctx, send_cb, self._set_step)

    def _parse_adversarial_config(self, text: str, models: list[str]) -> AdversarialConfig:
        """解析用户输入的配置文本（解析规则见同目录 adversarial_config.py）。"""
        return parse_adversarial_config(text, models)

    async def _handle_adversarial_input(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        """处理对抗模式中的用户输入."""
        text = (user_input or "").strip()

        # 导出报告
        if text in ("导出报告", "导出", "报告"):
            await self._export_adversarial_report(ctx, send_cb)
            return

        # 结束辩论
        if text in ("结束辩论", "结束"):
            service = self._adversarial_services.get(ctx.session_id)
            if service:
                await self._set_step(ctx.session_id, MockTrialStep.COURT_SUMMARY)
                await service.run_summary(send_cb)
                await send_cb(
                    {
                        "type": "system_message",
                        "content": "✅ 庭审结束！回复 **导出报告** 下载庭审报告。",
                        "metadata": {"stage": "finished"},
                    }
                )
                await self._set_step(ctx.session_id, MockTrialStep.SUMMARY)
            return

        # 切换角色
        role_switch = {
            "我代替原告": "plaintiff",
            "我代替被告": "defendant",
            "我代替法官": "judge",
            "我观看": "observer",
        }
        for keyword, role in role_switch.items():
            if keyword in text:
                metadata = await self.session_repo.get_metadata(ctx.session_id)
                adv_config = metadata.get("adversarial_config", {})
                adv_config["user_role"] = role
                await self.session_repo.update_metadata(ctx.session_id, {"adversarial_config": adv_config})
                service = self._adversarial_services.get(ctx.session_id)
                if service:
                    service.config.user_role = role
                label = {"plaintiff": "原告律师", "defendant": "被告律师", "judge": "审判长", "observer": "观看模式"}
                await send_cb(
                    {
                        "type": "system_message",
                        "content": f"✅ 已切换为 **{label.get(role, role)}**",
                    }
                )
                return

        # 用户代替角色发言
        service = self._adversarial_services.get(ctx.session_id)
        if service:
            await service.handle_user_input(ctx, text, send_cb, self._set_step)

    async def _export_adversarial_report(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any]
    ) -> None:  # pragma: no cover
        """生成并推送对抗庭审报告."""
        service = self._adversarial_services.get(ctx.session_id)
        if not service or not service.transcript:
            await send_cb({"type": "system_message", "content": "⚠️ 暂无庭审记录可导出。"})
            return

        metadata = await self.session_repo.get_metadata(ctx.session_id)
        adv_config = metadata.get("adversarial_config", {})
        report_text = format_adversarial_report(service.transcript, service.case_info, adv_config)

        # 保存到 session metadata
        await self.session_repo.update_metadata(ctx.session_id, {"adversarial_report": report_text})

        await send_cb(
            {
                "type": "assistant_complete",
                "content": report_text,
                "metadata": {"report_type": "adversarial_trial", "exportable": True},
            }
        )
        await self.messenger.persist_message(
            ctx.session_id, "assistant", report_text, {"report_type": "adversarial_trial"}
        )
