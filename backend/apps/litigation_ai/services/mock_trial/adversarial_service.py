"""多 Agent 对抗模拟庭审服务."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async

from .types import AdversarialConfig, MockTrialContext, MockTrialStep

logger = logging.getLogger("apps.litigation_ai")

# ── 角色常量 ──

PLAINTIFF = "plaintiff"
DEFENDANT = "defendant"
JUDGE = "judge"

ROLE_LABELS: dict[str, str] = {
    PLAINTIFF: "⚔️ 原告律师",
    DEFENDANT: "🛡️ 被告律师",
    JUDGE: "⚖️ 审判长",
}

# ── 激烈对抗 System Prompts ──

_PLAINTIFF_SYSTEM = (
    "你是一位极其强势、咄咄逼人的原告代理律师，拥有20年诉讼经验。\n"
    "你的风格：\n"
    "- 穷追猛打，绝不放过对方任何一个漏洞和矛盾之处\n"
    "- 用最犀利的语言指出对方论点的荒谬之处\n"
    "- 每次发言必须引用具体证据和法律条文支撑\n"
    "- 善于设置陷阱，引导对方自相矛盾\n"
    "- 语气坚定有力，逻辑严密，层层递进\n"
    "- 必须逐条回应对方的每一个论点，不能回避任何问题\n\n"
    "你代表原告，目标是最大化原告利益。发言控制在300-500字。"
)

_DEFENDANT_SYSTEM = (
    "你是一位寸步不让、极其顽强的被告代理律师，拥有20年诉讼经验。\n"
    "你的风格：\n"
    "- 逐条驳斥原告的每一个论点，找出逻辑漏洞和证据不足\n"
    "- 善于釜底抽薪，从根本上动摇对方的请求基础\n"
    "- 用最尖锐的方式质疑对方证据的真实性、合法性、关联性\n"
    "- 主动提出反驳证据和法律依据\n"
    "- 语气强硬但专业，绝不示弱\n"
    "- 必须针对对方刚才的发言逐一反驳，不能泛泛而谈\n\n"
    "你代表被告，目标是最大化被告利益。发言控制在300-500字。"
)

_JUDGE_SYSTEM = (
    "你是一位严厉、公正的审判长，拥有30年审判经验。\n"
    "你的风格：\n"
    "- 主持庭审秩序，控制庭审节奏\n"
    "- 对双方的论点进行犀利追问，不放过任何含糊之处\n"
    "- 善于发现双方论证中的薄弱环节并当庭追问\n"
    "- 引导双方围绕争议焦点展开辩论，制止跑题\n"
    "- 在法庭调查阶段主动询问关键事实\n"
    "- 语气威严但公正，不偏不倚\n\n"
    "发言控制在200-400字。"
)

_JUDGE_SUMMARY_SYSTEM = (
    "你是审判长，庭审辩论已结束。请根据双方的全部发言，作出庭审总结：\n"
    "1. 归纳本案争议焦点（3-5个）\n"
    "2. 逐一分析每个焦点下双方的论证强弱\n"
    "3. 评估双方证据的充分性\n"
    "4. 给出初步的胜诉概率判断（百分比）\n"
    "5. 指出双方各自需要补强的地方\n"
    "6. 给出庭审策略建议\n\n"
    "要求客观公正，分析深入，800-1200字。"
)


@dataclass
class _Agent:
    """单个 Agent 角色."""

    role: str
    model: str
    system_prompt: str

    async def respond(self, user_content: str) -> str:
        """调用 LLM 生成回复."""
        from apps.litigation_ai.services.wiring import get_llm_service

        llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]
        response = await llm_service.achat(messages=messages, model=self.model or None, temperature=0.5)
        return (response.content or "").strip()


class AdversarialTrialService:
    """多 Agent 对抗模拟庭审引擎."""

    def __init__(self, config: AdversarialConfig, case_info: dict[str, Any], evidence_text: str) -> None:
        self.config = config
        self.case_info = case_info
        self.evidence_text = evidence_text
        self.transcript: list[dict[str, str]] = []  # 完整庭审记录

        self.plaintiff = _Agent(PLAINTIFF, config.plaintiff_model, _PLAINTIFF_SYSTEM)
        self.defendant = _Agent(DEFENDANT, config.defendant_model, _DEFENDANT_SYSTEM)
        self.judge = _Agent(JUDGE, config.judge_model, _JUDGE_SYSTEM)

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

    async def _agent_speak(
        self, agent: _Agent, prompt: str, send_cb: Callable[..., Any], stage: str
    ) -> str:
        """让 Agent 发言并推送."""
        content = await agent.respond(prompt)
        self.transcript.append({"role": agent.role, "stage": stage, "content": content})
        await send_cb({
            "type": "assistant_complete",
            "content": f"**{ROLE_LABELS[agent.role]}：**\n\n{content}",
            "metadata": {"role": agent.role, "stage": stage, "model": agent.model},
        })
        return content

    async def _send_stage(self, send_cb: Callable[..., Any], stage: str, label: str) -> None:
        """推送阶段标题."""
        await send_cb({
            "type": "system_message",
            "content": f"\n{'═' * 40}\n## 📋 {label}\n{'═' * 40}",
            "metadata": {"stage": stage},
        })

    async def _wait_or_ai(
        self, agent: _Agent, prompt: str, send_cb: Callable[..., Any], stage: str
    ) -> str | None:
        """如果用户代替该角色，返回 None（暂停等待）；否则 AI 自动发言."""
        if self.config.user_role == agent.role:
            await send_cb({
                "type": "system_message",
                "content": f"💡 轮到 **{ROLE_LABELS[agent.role]}** 发言（由您代替）。请输入您的发言内容：",
                "metadata": {"waiting_for": agent.role, "stage": stage, "prompt_hint": prompt},
            })
            return None  # 暂停，等 handle_user_input
        return await self._agent_speak(agent, prompt, send_cb, stage)

    # ── 庭审各阶段 ──

    async def run_opening(self, send_cb: Callable[..., Any]) -> str | None:
        """法官宣布开庭."""
        await self._send_stage(send_cb, "opening", "开庭审理")
        prompt = (
            f"现在开庭。请宣布开庭，介绍案件基本情况，核实当事人身份，宣布庭审纪律。\n\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.judge, prompt, send_cb, "opening")

    async def run_plaintiff_statement(self, send_cb: Callable[..., Any]) -> str | None:
        """原告陈述."""
        await self._send_stage(send_cb, "plaintiff_statement", "原告陈述诉讼请求及事实理由")
        prompt = (
            f"请作为原告律师，陈述诉讼请求和事实理由。要求：\n"
            f"1. 明确列出全部诉讼请求\n"
            f"2. 详细阐述事实经过\n"
            f"3. 引用关键证据支撑\n"
            f"4. 说明法律依据\n\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.plaintiff, prompt, send_cb, "plaintiff_statement")

    async def run_defendant_response(self, send_cb: Callable[..., Any], plaintiff_statement: str) -> str | None:
        """被告答辩."""
        await self._send_stage(send_cb, "defendant_response", "被告答辩")
        prompt = (
            f"原告刚才的陈述如下：\n\n{plaintiff_statement}\n\n"
            f"请作为被告律师进行答辩。要求：\n"
            f"1. 逐条回应原告的诉讼请求\n"
            f"2. 指出原告陈述中的事实错误和逻辑漏洞\n"
            f"3. 提出被告的抗辩理由和证据\n"
            f"4. 引用法律条文反驳\n\n案件信息：\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.defendant, prompt, send_cb, "defendant_response")

    async def run_investigation(self, send_cb: Callable[..., Any]) -> str | None:
        """法庭调查."""
        await self._send_stage(send_cb, "investigation", "法庭调查")
        history_text = "\n\n".join(
            f"【{ROLE_LABELS.get(t['role'], t['role'])}】{t['content']}" for t in self.transcript
        )
        prompt = (
            f"根据双方的陈述和答辩，请主持法庭调查：\n"
            f"1. 归纳本案争议焦点\n"
            f"2. 就关键事实向双方提问\n"
            f"3. 组织双方对证据进行质证\n\n"
            f"庭审记录：\n{history_text}\n\n案件信息：\n{self._case_brief()}"
        )
        return await self._wait_or_ai(self.judge, prompt, send_cb, "investigation")

    async def run_debate_round(
        self, send_cb: Callable[..., Any], round_num: int, total_rounds: int, last_content: str
    ) -> tuple[str | None, str | None]:
        """一轮辩论：原告 → 被告."""
        await send_cb({
            "type": "system_message",
            "content": f"### 🔥 第 {round_num}/{total_rounds} 轮辩论",
            "metadata": {"stage": "debate", "round": round_num, "total": total_rounds},
        })

        history_text = "\n\n".join(
            f"【{ROLE_LABELS.get(t['role'], t['role'])}】{t['content']}"
            for t in self.transcript[-8:]  # 最近 8 条上下文
        )

        # 原告发言
        p_prompt = (
            f"这是第{round_num}轮辩论。对方（被告）上一轮的发言：\n\n{last_content}\n\n"
            f"请针对对方的论点进行犀利反驳，必须逐条回应，不能回避任何问题。"
            f"同时提出新的攻击点。\n\n近期庭审记录：\n{history_text}"
        )
        p_content = await self._wait_or_ai(self.plaintiff, p_prompt, send_cb, "debate")
        if p_content is None:
            return None, None  # 等用户

        # 被告发言
        d_prompt = (
            f"这是第{round_num}轮辩论。原告刚才的发言：\n\n{p_content}\n\n"
            f"请逐条驳斥原告的每一个论点，找出逻辑漏洞，提出有力反驳。"
            f"绝不能示弱。\n\n近期庭审记录：\n{history_text}"
        )
        d_content = await self._wait_or_ai(self.defendant, d_prompt, send_cb, "debate")
        return p_content, d_content

    async def run_judge_interjection(self, send_cb: Callable[..., Any], round_num: int) -> str | None:
        """法官追问（每 2-3 轮插入一次）."""
        history_text = "\n\n".join(
            f"【{ROLE_LABELS.get(t['role'], t['role'])}】{t['content']}"
            for t in self.transcript[-6:]
        )
        prompt = (
            f"第{round_num}轮辩论结束。请作为审判长，就双方辩论中的薄弱环节进行追问：\n"
            f"1. 指出双方论证中的不足\n"
            f"2. 要求双方就关键问题进一步说明\n"
            f"3. 引导辩论回到争议焦点\n\n"
            f"近期庭审记录：\n{history_text}"
        )
        return await self._wait_or_ai(self.judge, prompt, send_cb, "debate_judge")

    async def run_summary(self, send_cb: Callable[..., Any]) -> str:
        """法官总结."""
        await self._send_stage(send_cb, "summary", "法庭总结")
        full_transcript = "\n\n".join(
            f"【{ROLE_LABELS.get(t['role'], t['role'])}】（{t['stage']}）\n{t['content']}"
            for t in self.transcript
        )
        agent = _Agent(JUDGE, self.config.judge_model, _JUDGE_SUMMARY_SYSTEM)
        prompt = f"以下是完整的庭审记录：\n\n{full_transcript}\n\n案件信息：\n{self._case_brief()}"
        content = await self._agent_speak(agent, prompt, send_cb, "summary")
        return content

    # ── 完整庭审编排 ──

    async def run_full_trial(self, ctx: MockTrialContext, send_cb: Callable[..., Any], set_step: Callable[..., Any]) -> None:
        """运行完整庭审流程."""
        # 开庭
        await set_step(ctx.session_id, MockTrialStep.COURT_OPENING)
        result = await self.run_opening(send_cb)
        if result is None:
            return  # 等用户

        # 原告陈述
        await set_step(ctx.session_id, MockTrialStep.PLAINTIFF_STATEMENT)
        p_statement = await self.run_plaintiff_statement(send_cb)
        if p_statement is None:
            return

        # 被告答辩
        await set_step(ctx.session_id, MockTrialStep.DEFENDANT_RESPONSE)
        d_response = await self.run_defendant_response(send_cb, p_statement)
        if d_response is None:
            return

        # 法庭调查
        await set_step(ctx.session_id, MockTrialStep.COURT_INVESTIGATION)
        investigation = await self.run_investigation(send_cb)
        if investigation is None:
            return

        # 法庭辩论
        await set_step(ctx.session_id, MockTrialStep.COURT_DEBATE)
        last_content = d_response
        for i in range(1, self.config.debate_rounds + 1):
            p_content, d_content = await self.run_debate_round(send_cb, i, self.config.debate_rounds, last_content)
            if p_content is None or d_content is None:
                return  # 等用户
            last_content = d_content

            # 法官每 2-3 轮追问
            if i % 2 == 0 and i < self.config.debate_rounds:
                j_content = await self.run_judge_interjection(send_cb, i)
                if j_content is None:
                    return

        # 法官总结
        await set_step(ctx.session_id, MockTrialStep.COURT_SUMMARY)
        summary = await self.run_summary(send_cb)

        # 完成
        await send_cb({
            "type": "system_message",
            "content": (
                f"✅ 庭审结束！共进行 {self.config.debate_rounds} 轮辩论。\n\n"
                f"原告模型：{self.config.plaintiff_model or '默认'}\n"
                f"被告模型：{self.config.defendant_model or '默认'}\n"
                f"法官模型：{self.config.judge_model or '默认'}\n\n"
                "回复 **导出报告** 可下载完整庭审报告。"
            ),
            "metadata": {"stage": "finished", "transcript": self.transcript},
        })
        await set_step(ctx.session_id, MockTrialStep.SUMMARY)

    async def handle_user_input(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        """处理用户代替角色的发言，然后继续流程."""
        # 找到用户代替的角色
        role = self.config.user_role
        stage = ctx.current_step.value.replace("mt_", "")

        self.transcript.append({"role": role, "stage": stage, "content": user_input})
        await send_cb({
            "type": "assistant_complete",
            "content": f"**{ROLE_LABELS.get(role, role)}（您）：**\n\n{user_input}",
            "metadata": {"role": role, "stage": stage, "is_user": True},
        })

        # 根据当前步骤继续流程
        step = ctx.current_step
        if step == MockTrialStep.COURT_OPENING:
            await set_step(ctx.session_id, MockTrialStep.PLAINTIFF_STATEMENT)
            p = await self.run_plaintiff_statement(send_cb)
            if p is None:
                return
            await self._continue_from_plaintiff(ctx, p, send_cb, set_step)

        elif step == MockTrialStep.PLAINTIFF_STATEMENT:
            await self._continue_from_plaintiff(ctx, user_input, send_cb, set_step)

        elif step == MockTrialStep.DEFENDANT_RESPONSE:
            await self._continue_from_defendant(ctx, send_cb, set_step)

        elif step == MockTrialStep.COURT_INVESTIGATION:
            await self._continue_from_investigation(ctx, send_cb, set_step)

        elif step in (MockTrialStep.COURT_DEBATE,):
            await self._continue_debate(ctx, user_input, send_cb, set_step)

    async def _continue_from_plaintiff(
        self, ctx: MockTrialContext, p_statement: str, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        await set_step(ctx.session_id, MockTrialStep.DEFENDANT_RESPONSE)
        d = await self.run_defendant_response(send_cb, p_statement)
        if d is None:
            return
        await self._continue_from_defendant(ctx, send_cb, set_step)

    async def _continue_from_defendant(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        await set_step(ctx.session_id, MockTrialStep.COURT_INVESTIGATION)
        inv = await self.run_investigation(send_cb)
        if inv is None:
            return
        await self._continue_from_investigation(ctx, send_cb, set_step)

    async def _continue_from_investigation(
        self, ctx: MockTrialContext, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        await set_step(ctx.session_id, MockTrialStep.COURT_DEBATE)
        # 获取被告最后发言作为辩论起点
        last = next((t["content"] for t in reversed(self.transcript) if t["role"] == DEFENDANT), "")
        for i in range(1, self.config.debate_rounds + 1):
            p_c, d_c = await self.run_debate_round(send_cb, i, self.config.debate_rounds, last)
            if p_c is None or d_c is None:
                return
            last = d_c
            if i % 2 == 0 and i < self.config.debate_rounds:
                j = await self.run_judge_interjection(send_cb, i)
                if j is None:
                    return

        await set_step(ctx.session_id, MockTrialStep.COURT_SUMMARY)
        await self.run_summary(send_cb)
        await send_cb({
            "type": "system_message",
            "content": f"✅ 庭审结束！共 {self.config.debate_rounds} 轮辩论。回复 **导出报告** 下载庭审报告。",
            "metadata": {"stage": "finished", "transcript": self.transcript},
        })
        await set_step(ctx.session_id, MockTrialStep.SUMMARY)

    async def _continue_debate(
        self, ctx: MockTrialContext, user_input: str, send_cb: Callable[..., Any], set_step: Callable[..., Any]
    ) -> None:
        """用户在辩论阶段发言后，对方 AI 自动回应，然后继续."""
        role = self.config.user_role
        # 对方回应
        if role == PLAINTIFF:
            d_prompt = f"原告刚才说：\n\n{user_input}\n\n请逐条驳斥，不能示弱。"
            await self._agent_speak(self.defendant, d_prompt, send_cb, "debate")
        elif role == DEFENDANT:
            p_prompt = f"被告刚才说：\n\n{user_input}\n\n请犀利反驳，穷追猛打。"
            await self._agent_speak(self.plaintiff, p_prompt, send_cb, "debate")

        # 推送继续提示
        metadata = ctx.metadata or {}
        current_round = metadata.get("adversarial_debate_round", 1)
        if current_round < self.config.debate_rounds:
            await send_cb({
                "type": "system_message",
                "content": f"第 {current_round} 轮辩论完成。请继续发言，或回复 **结束辩论** 进入法官总结。",
            })
        else:
            await set_step(ctx.session_id, MockTrialStep.COURT_SUMMARY)
            await self.run_summary(send_cb)
            await send_cb({
                "type": "system_message",
                "content": "✅ 庭审结束！回复 **导出报告** 下载庭审报告。",
                "metadata": {"stage": "finished", "transcript": self.transcript},
            })
            await set_step(ctx.session_id, MockTrialStep.SUMMARY)
