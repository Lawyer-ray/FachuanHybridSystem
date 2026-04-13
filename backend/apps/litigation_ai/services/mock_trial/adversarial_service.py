"""多 Agent 对抗模拟庭审服务 — 严格按照民事诉讼法庭审程序."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .agents import (
    CLERK,
    CLERK_ANNOUNCE,
    DEFENDANT,
    DEFENDANT_SYSTEM,
    JUDGE,
    JUDGE_CLOSING,
    JUDGE_CROSS_EXAM,
    JUDGE_DEBATE_START,
    JUDGE_EVIDENCE_START,
    JUDGE_FINAL_STATEMENT,
    JUDGE_IDENTITY_CHECK,
    JUDGE_INVESTIGATION_START_FIRST,
    JUDGE_INVESTIGATION_START_SECOND,
    JUDGE_MEDIATION,
    JUDGE_OPEN_FIRST,
    JUDGE_OPEN_SECOND,
    JUDGE_RIGHTS_NOTICE,
    JUDGE_SUMMARY_SYSTEM,
    JUDGE_SYSTEM,
    PLAINTIFF,
    PLAINTIFF_SYSTEM,
    ROLE_LABELS,
    Agent,
)
from .types import AdversarialConfig, MockTrialContext, MockTrialStep, TrialLevel

logger = logging.getLogger("apps.litigation_ai")


class AdversarialTrialService:
    """多 Agent 对抗模拟庭审引擎 — 严格按照民事诉讼法庭审程序."""

    def __init__(self, config: AdversarialConfig, case_info: dict[str, Any], evidence_text: str) -> None:
        self.config = config
        self.case_info = case_info
        self.evidence_text = evidence_text
        self.transcript: list[dict[str, Any]] = []
        self.is_second = config.trial_level == TrialLevel.SECOND

        self.plaintiff = Agent(PLAINTIFF, config.plaintiff_model, PLAINTIFF_SYSTEM)
        self.defendant = Agent(DEFENDANT, config.defendant_model, DEFENDANT_SYSTEM)
        self.judge = Agent(JUDGE, config.judge_model, JUDGE_SYSTEM)

    # ── 工具方法 ──

    def _case_brief(self) -> str:
        ci = self.case_info
        parties = "\n".join(
            f"- {p.get('name', '')}（{p.get('legal_status', '')}，{'我方' if p.get('is_our_side') else '对方'}）"
            for p in ci.get("parties", [])
        )
        return (
            f"案件名称：{ci.get('case_name', '')}\n"
            f"案由：{ci.get('cause_of_action', '')}\n"
            f"标的额：{ci.get('target_amount') or '未知'}\n"
            f"当事人：\n{parties or '无'}\n"
            f"证据概要：\n{self.evidence_text or '无'}"
        )

    def _party_names(self) -> tuple[str, str]:
        parties = self.case_info.get("parties", [])
        p_name = next(
            (p["name"] for p in parties if "原告" in p.get("legal_status", "") or p.get("is_our_side")), "原告"
        )
        d_name = next(
            (p["name"] for p in parties if "被告" in p.get("legal_status", "") or not p.get("is_our_side")), "被告"
        )
        return p_name, d_name

    async def _record_and_send(
        self, send_cb: Callable[..., Any], role: str, content: str, stage: str, **extra: Any
    ) -> None:
        entry: dict[str, Any] = {"role": role, "stage": stage, "content": content, **extra}
        self.transcript.append(entry)
        await send_cb(
            {
                "type": "assistant_complete",
                "content": f"**{ROLE_LABELS.get(role, role)}：**\n\n{content}",
                "metadata": {"role": role, "stage": stage, **extra},
            }
        )

    async def _send_stage(self, send_cb: Callable[..., Any], stage: str, label: str) -> None:
        await send_cb(
            {
                "type": "system_message",
                "content": f"\n{'═' * 50}\n## 📋 {label}\n{'═' * 50}",
                "metadata": {"stage": stage},
            }
        )

    async def _agent_speak(self, agent: Agent, prompt: str, send_cb: Callable[..., Any], stage: str) -> str:
        content = await agent.respond(prompt)
        await self._record_and_send(send_cb, agent.role, content, stage, model=agent.model)
        return content

    async def _wait_or_ai(self, agent: Agent, prompt: str, send_cb: Callable[..., Any], stage: str) -> str | None:
        if self.config.user_role == agent.role:
            await send_cb(
                {
                    "type": "system_message",
                    "content": f"💡 轮到 **{ROLE_LABELS[agent.role]}** 发言（由您代替）。请输入您的发言内容：",
                    "metadata": {"waiting_for": agent.role, "stage": stage},
                }
            )
            return None
        return await self._agent_speak(agent, prompt, send_cb, stage)

    # ══════════════════════════════════════════════════
    # 庭审各阶段 — 严格按照民事诉讼法程序
    # ══════════════════════════════════════════════════

    async def phase_1_opening(self, send_cb: Callable[..., Any]) -> None:
        """第一阶段：书记员宣布法庭纪律 + 审判长宣布开庭."""
        await self._send_stage(send_cb, "opening", "宣布开庭")

        # 书记员
        await self._record_and_send(send_cb, CLERK, CLERK_ANNOUNCE, "opening")

        # 审判长开庭
        p_name, d_name = self._party_names()
        cause = self.case_info.get("cause_of_action", "纠纷")
        if self.is_second:
            text = JUDGE_OPEN_SECOND.format(
                court_name="本院",
                appellant_name=p_name,
                appellee_name=d_name,
                cause=cause,
                judge_info="审判长及两名审判员",
                clerk_name="书记员",
            )
        else:
            text = JUDGE_OPEN_FIRST.format(
                court_name="本院",
                plaintiff_name=p_name,
                defendant_name=d_name,
                cause=cause,
                judge_info="审判长及两名审判员",
                clerk_name="书记员",
            )
        await self._record_and_send(send_cb, JUDGE, text, "opening")

    async def phase_2_identity_check(self, send_cb: Callable[..., Any]) -> None:
        """第二阶段：核实当事人身份."""
        await self._send_stage(send_cb, "identity_check", "核实当事人身份")
        await self._record_and_send(send_cb, JUDGE, JUDGE_IDENTITY_CHECK, "identity_check")

        # 原告自报身份
        p_name, d_name = self._party_names()
        p_prompt = f"请以原告代理人身份，向法庭报告委托人和代理人的基本信息。委托人：{p_name}。"
        await self._wait_or_ai(self.plaintiff, p_prompt, send_cb, "identity_check") or ""

        # 被告自报身份
        d_prompt = f"请以被告代理人身份，向法庭报告委托人和代理人的基本信息。委托人：{d_name}。"
        await self._wait_or_ai(self.defendant, d_prompt, send_cb, "identity_check") or ""

    async def phase_3_rights_notice(self, send_cb: Callable[..., Any]) -> None:
        """第三阶段：告知权利义务 + 询问回避."""
        await self._send_stage(send_cb, "rights_notice", "告知权利义务、询问回避")
        await self._record_and_send(send_cb, JUDGE, JUDGE_RIGHTS_NOTICE, "rights_notice")
        await self._record_and_send(send_cb, PLAINTIFF, "审判长，听清楚了，不申请回避。", "rights_notice")
        await self._record_and_send(send_cb, DEFENDANT, "审判长，听清楚了，不申请回避。", "rights_notice")

    async def phase_4_appeal(self, send_cb: Callable[..., Any]) -> str | None:
        """第四阶段（二审特有）：上诉请求与答辩."""
        if not self.is_second:
            return ""
        await self._send_stage(send_cb, "appeal_statement", "上诉请求与答辩（二审特有）")
        await self._record_and_send(
            send_cb,
            JUDGE,
            "现在由上诉人陈述上诉请求及上诉理由，并说明对一审判决哪些部分不服、请求如何改判。",
            "appeal_statement",
        )
        prompt = (
            f"你是上诉人的代理律师。请向法庭陈述：\n"
            f"1. 对一审判决哪些部分不服\n"
            f"2. 上诉请求（请求如何改判）\n"
            f"3. 上诉理由（一审认定事实错误/适用法律错误/程序违法）\n\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.plaintiff, prompt, send_cb, "appeal_statement")

    async def phase_5_plaintiff_statement(self, send_cb: Callable[..., Any]) -> str | None:
        """第五阶段：原告陈述诉讼请求和事实理由."""
        label = "上诉人陈述" if self.is_second else "原告陈述诉讼请求及事实理由"
        start_text = JUDGE_INVESTIGATION_START_SECOND if self.is_second else JUDGE_INVESTIGATION_START_FIRST
        await self._send_stage(send_cb, "plaintiff_statement", label)
        await self._record_and_send(send_cb, JUDGE, start_text, "plaintiff_statement")

        prompt = (
            f"请作为{'上诉人' if self.is_second else '原告'}代理律师，向法庭陈述：\n"
            f"1. 明确列出全部诉讼请求\n"
            f"2. 详细阐述事实经过\n"
            f"3. 引用关键证据支撑\n"
            f"4. 说明法律依据\n\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.plaintiff, prompt, send_cb, "plaintiff_statement")

    async def phase_6_defendant_response(self, send_cb: Callable[..., Any], p_statement: str) -> str | None:
        """第六阶段：被告答辩."""
        label = "被上诉人答辩" if self.is_second else "被告答辩"
        await self._send_stage(send_cb, "defendant_response", label)
        await self._record_and_send(send_cb, JUDGE, JUDGE_EVIDENCE_START, "defendant_response")

        prompt = (
            f"{'上诉人' if self.is_second else '原告'}刚才的陈述如下：\n\n{p_statement}\n\n"
            f"请作为{'被上诉人' if self.is_second else '被告'}代理律师进行答辩：\n"
            f"1. 逐条回应对方的诉讼请求\n"
            f"2. 指出对方陈述中的事实错误和逻辑漏洞\n"
            f"3. 提出抗辩理由和证据\n"
            f"4. 引用法律条文反驳\n\n案件信息：\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.defendant, prompt, send_cb, "defendant_response")

    async def phase_7_investigation(self, send_cb: Callable[..., Any]) -> str | None:
        """第七阶段：法庭调查（举证质证 + 法官询问）."""
        await self._send_stage(send_cb, "investigation", "法庭调查（举证质证）")
        await self._record_and_send(send_cb, JUDGE, JUDGE_CROSS_EXAM, "investigation")

        history = "\n\n".join(f"【{ROLE_LABELS.get(t['role'], t['role'])}】{t['content']}" for t in self.transcript)
        prompt = (
            f"根据双方的陈述和答辩，请主持法庭调查：\n"
            f"1. 归纳本案争议焦点\n"
            f"2. 组织双方对证据进行质证（真实性、合法性、关联性）\n"
            f"3. 就关键事实向双方提问\n"
            f"4. {'重点审查一审判决认定事实是否清楚' if self.is_second else '查明案件事实'}\n\n"
            f"庭审记录：\n{history}\n\n案件信息：\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.judge, prompt, send_cb, "investigation")

    async def phase_8_debate(self, send_cb: Callable[..., Any]) -> None:
        """第八阶段：法庭辩论（多轮激烈对抗）."""
        await self._send_stage(send_cb, "debate", "法庭辩论")
        await self._record_and_send(send_cb, JUDGE, JUDGE_DEBATE_START, "debate")

        last_content = self.transcript[-1]["content"] if self.transcript else ""
        for i in range(1, self.config.debate_rounds + 1):
            await send_cb(
                {
                    "type": "system_message",
                    "content": f"### 🔥 第 {i}/{self.config.debate_rounds} 轮辩论",
                    "metadata": {"stage": "debate", "round": i, "total": self.config.debate_rounds},
                }
            )

            recent = "\n\n".join(
                f"【{ROLE_LABELS.get(t['role'], t['role'])}】{t['content']}" for t in self.transcript[-6:]
            )

            # 原告辩论
            p_prompt = (
                f"这是第{i}轮辩论。对方上一轮的发言：\n\n{last_content}\n\n"
                f"请针对对方论点进行犀利反驳，必须逐条回应。同时提出新的攻击点。\n\n"
                f"近期庭审记录：\n{recent}"
            )
            p_content = await self._wait_or_ai(self.plaintiff, p_prompt, send_cb, "debate")
            if p_content is None:
                return  # 等用户

            # 被告辩论
            d_prompt = (
                f"这是第{i}轮辩论。原告刚才的发言：\n\n{p_content}\n\n"
                f"请逐条驳斥原告的每一个论点，找出逻辑漏洞，提出有力反驳。绝不能示弱。\n\n"
                f"近期庭审记录：\n{recent}"
            )
            d_content = await self._wait_or_ai(self.defendant, d_prompt, send_cb, "debate")
            if d_content is None:
                return
            last_content = d_content

            # 法官每 2 轮追问
            if i % 2 == 0 and i < self.config.debate_rounds:
                j_prompt = (
                    f"第{i}轮辩论结束。请就双方辩论中的薄弱环节进行追问，"
                    f"要求双方进一步说明。\n\n近期庭审记录：\n{recent}"
                )
                j_content = await self._wait_or_ai(self.judge, j_prompt, send_cb, "debate")
                if j_content is None:
                    return

    async def phase_9_final_statement(self, send_cb: Callable[..., Any]) -> None:
        """第九阶段：最后陈述."""
        await self._send_stage(send_cb, "final_statement", "最后陈述")
        await self._record_and_send(send_cb, JUDGE, JUDGE_FINAL_STATEMENT, "final_statement")

        p_prompt = "请作为原告代理人作最后陈述，简明扼要地总结己方观点和诉讼请求。200字以内。"
        await self._wait_or_ai(self.plaintiff, p_prompt, send_cb, "final_statement") or ""

        d_prompt = "请作为被告代理人作最后陈述，简明扼要地总结己方观点和抗辩意见。200字以内。"
        await self._wait_or_ai(self.defendant, d_prompt, send_cb, "final_statement") or ""

    async def phase_10_mediation(self, send_cb: Callable[..., Any]) -> None:
        """第十阶段：法庭调解."""
        await self._send_stage(send_cb, "mediation", "法庭调解")
        await self._record_and_send(send_cb, JUDGE, JUDGE_MEDIATION, "mediation")
        await self._record_and_send(send_cb, PLAINTIFF, "审判长，我方暂不同意调解，请求法庭依法判决。", "mediation")
        await self._record_and_send(send_cb, DEFENDANT, "审判长，我方也请求法庭依法判决。", "mediation")

    async def phase_11_summary(self, send_cb: Callable[..., Any]) -> str:
        """第十一阶段：法官总结评议."""
        await self._send_stage(send_cb, "summary", "合议庭评议与总结")
        full = "\n\n".join(
            f"【{ROLE_LABELS.get(t['role'], t['role'])}】（{t['stage']}）\n{t['content']}" for t in self.transcript
        )
        agent = Agent(JUDGE, self.config.judge_model, JUDGE_SUMMARY_SYSTEM)
        prompt = f"以下是完整的庭审记录：\n\n{full}\n\n案件信息：\n{self._case_brief()}"
        content = await self._agent_speak(agent, prompt, send_cb, "summary")

        # 宣布休庭
        await self._record_and_send(send_cb, JUDGE, JUDGE_CLOSING, "closing")
        return content

    # ══════════════════════════════════════════════════
    # 完整庭审编排
    # ══════════════════════════════════════════════════

    async def run_full_trial(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        """运行完整庭审流程（一审/二审）."""
        level_label = "二审" if self.is_second else "一审"
        await send_cb(
            {
                "type": "system_message",
                "content": f"🏛️ **{level_label}庭审正式开始**\n\n严格按照《民事诉讼法》庭审程序进行。",
            }
        )

        # 第一阶段：开庭
        await set_step(ctx.session_id, MockTrialStep.COURT_OPENING)
        await self.phase_1_opening(send_cb)

        # 第二阶段：核实身份
        await set_step(ctx.session_id, MockTrialStep.IDENTITY_CHECK)
        await self.phase_2_identity_check(send_cb)

        # 第三阶段：告知权利
        await set_step(ctx.session_id, MockTrialStep.RIGHTS_NOTICE)
        await self.phase_3_rights_notice(send_cb)

        # 第四阶段：上诉请求（二审特有）
        if self.is_second:
            await set_step(ctx.session_id, MockTrialStep.APPEAL_STATEMENT)
            result = await self.phase_4_appeal(send_cb)
            if result is None:
                return

        # 第五阶段：原告陈述
        await set_step(ctx.session_id, MockTrialStep.PLAINTIFF_STATEMENT)
        p_statement = await self.phase_5_plaintiff_statement(send_cb)
        if p_statement is None:
            return

        # 第六阶段：被告答辩
        await set_step(ctx.session_id, MockTrialStep.DEFENDANT_RESPONSE)
        d_response = await self.phase_6_defendant_response(send_cb, p_statement)
        if d_response is None:
            return

        # 第七阶段：法庭调查
        await set_step(ctx.session_id, MockTrialStep.COURT_INVESTIGATION)
        investigation = await self.phase_7_investigation(send_cb)
        if investigation is None:
            return

        # 第八阶段：法庭辩论
        await set_step(ctx.session_id, MockTrialStep.COURT_DEBATE)
        await self.phase_8_debate(send_cb)

        # 第九阶段：最后陈述
        await set_step(ctx.session_id, MockTrialStep.FINAL_STATEMENT)
        await self.phase_9_final_statement(send_cb)

        # 第十阶段：调解
        await set_step(ctx.session_id, MockTrialStep.MEDIATION)
        await self.phase_10_mediation(send_cb)

        # 第十一阶段：总结
        await set_step(ctx.session_id, MockTrialStep.COURT_SUMMARY)
        await self.phase_11_summary(send_cb)

        # 完成
        await send_cb(
            {
                "type": "system_message",
                "content": (
                    f"✅ {level_label}庭审结束！共进行 {self.config.debate_rounds} 轮辩论。\n\n"
                    f"原告模型：{self.config.plaintiff_model or '默认'}\n"
                    f"被告模型：{self.config.defendant_model or '默认'}\n"
                    f"法官模型：{self.config.judge_model or '默认'}\n\n"
                    "回复 **导出报告** 可下载完整庭审报告。"
                ),
                "metadata": {"stage": "finished", "transcript": self.transcript},
            }
        )
        await set_step(ctx.session_id, MockTrialStep.SUMMARY)

    # ── 用户介入处理 ──

    async def handle_user_input(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        """处理用户代替角色的发言，然后继续流程."""
        role = self.config.user_role
        stage = ctx.current_step.value.replace("mt_", "")

        await self._record_and_send(send_cb, role, user_input, stage, is_user=True)

        # 根据当前步骤继续
        step = ctx.current_step
        if step == MockTrialStep.PLAINTIFF_STATEMENT:
            await set_step(ctx.session_id, MockTrialStep.DEFENDANT_RESPONSE)
            d = await self.phase_6_defendant_response(send_cb, user_input)
            if d is None:
                return
            await self._continue_from_defendant(ctx, send_cb, set_step)
        elif step == MockTrialStep.DEFENDANT_RESPONSE:
            await self._continue_from_defendant(ctx, send_cb, set_step)
        elif step == MockTrialStep.COURT_INVESTIGATION:
            await self._continue_from_investigation(ctx, send_cb, set_step)
        elif step == MockTrialStep.COURT_DEBATE:
            await self._continue_debate(ctx, user_input, send_cb, set_step)
        elif step == MockTrialStep.APPEAL_STATEMENT:
            await set_step(ctx.session_id, MockTrialStep.PLAINTIFF_STATEMENT)
            p = await self.phase_5_plaintiff_statement(send_cb)
            if p is None:
                return
            await set_step(ctx.session_id, MockTrialStep.DEFENDANT_RESPONSE)
            d = await self.phase_6_defendant_response(send_cb, p)
            if d is None:
                return
            await self._continue_from_defendant(ctx, send_cb, set_step)

    async def _continue_from_defendant(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        await set_step(ctx.session_id, MockTrialStep.COURT_INVESTIGATION)
        inv = await self.phase_7_investigation(send_cb)
        if inv is None:
            return
        await self._continue_from_investigation(ctx, send_cb, set_step)

    async def _continue_from_investigation(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        await set_step(ctx.session_id, MockTrialStep.COURT_DEBATE)
        await self.phase_8_debate(send_cb)
        await set_step(ctx.session_id, MockTrialStep.FINAL_STATEMENT)
        await self.phase_9_final_statement(send_cb)
        await set_step(ctx.session_id, MockTrialStep.MEDIATION)
        await self.phase_10_mediation(send_cb)
        await set_step(ctx.session_id, MockTrialStep.COURT_SUMMARY)
        await self.phase_11_summary(send_cb)
        level_label = "二审" if self.is_second else "一审"
        await send_cb(
            {
                "type": "system_message",
                "content": f"✅ {level_label}庭审结束！回复 **导出报告** 下载庭审报告。",
                "metadata": {"stage": "finished", "transcript": self.transcript},
            }
        )
        await set_step(ctx.session_id, MockTrialStep.SUMMARY)

    async def _continue_debate(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        role = self.config.user_role
        if role == PLAINTIFF:
            d_prompt = f"原告刚才说：\n\n{user_input}\n\n请逐条驳斥，不能示弱。"
            await self._agent_speak(self.defendant, d_prompt, send_cb, "debate")
        elif role == DEFENDANT:
            p_prompt = f"被告刚才说：\n\n{user_input}\n\n请犀利反驳，穷追猛打。"
            await self._agent_speak(self.plaintiff, p_prompt, send_cb, "debate")

        await send_cb(
            {
                "type": "system_message",
                "content": "请继续发言，或回复 **结束辩论** 进入最后陈述。",
            }
        )
