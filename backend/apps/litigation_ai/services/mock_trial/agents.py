"""多 Agent 对抗模拟庭审 — Agent 角色定义与 System Prompts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger("apps.litigation_ai")

# ── 角色常量 ──
PLAINTIFF = "plaintiff"
DEFENDANT = "defendant"
JUDGE = "judge"
CLERK = "clerk"

ROLE_LABELS: dict[str, str] = {
    PLAINTIFF: "⚔️ 原告代理人",
    DEFENDANT: "🛡️ 被告代理人",
    JUDGE: "⚖️ 审判长",
    CLERK: "📋 书记员",
}

# ── 法官标准用语 ──

CLERK_ANNOUNCE = (
    "请全体起立！请旁听人员保持安静，现在宣布法庭纪律：\n"
    "一、未经法庭许可，不得录音、录像、摄影；\n"
    "二、旁听人员不得发言、提问；\n"
    "三、不得鼓掌、喧哗、哄闹和实施其他妨害审判活动的行为。\n\n"
    "请审判长、审判员入庭。"
)

JUDGE_OPEN_FIRST = (
    "现在开庭。{court_name}依法公开审理原告{plaintiff_name}诉被告{defendant_name}"
    "{cause}一案，现在开庭。\n\n"
    "本案由{judge_info}组成合议庭，由{clerk_name}担任书记员。"
)

JUDGE_OPEN_SECOND = (
    "现在开庭。{court_name}依法公开审理上诉人{appellant_name}因与被上诉人{appellee_name}"
    "{cause}一案的上诉，现在开庭。\n\n"
    "本案由{judge_info}组成合议庭，由{clerk_name}担任书记员。"
)

JUDGE_IDENTITY_CHECK = (
    "首先核实当事人及其诉讼代理人的身份。\n"
    "请原告（上诉人）陈述姓名（名称）、性别、出生日期、民族、住所地、"
    "法定代表人及职务（如为法人）、委托诉讼代理人的姓名及代理权限。"
)

JUDGE_RIGHTS_NOTICE = (
    "根据《中华人民共和国民事诉讼法》的规定，当事人在法庭上享有以下权利：\n"
    "一、有申请回避的权利；\n"
    "二、有提出新的证据的权利；\n"
    "三、有进行辩论和最后陈述的权利；\n"
    "四、原告有放弃、变更、增加诉讼请求的权利，被告有提出反诉的权利；\n"
    "五、有自行和解的权利；\n"
    "六、有申请调解的权利。\n\n"
    "当事人在法庭上应履行以下义务：\n"
    "一、应当遵守法庭纪律；\n"
    "二、应当如实陈述案件事实；\n"
    "三、应当回答审判人员的提问。\n\n"
    "当事人听清楚了吗？是否申请回避？"
)

JUDGE_INVESTIGATION_START_FIRST = (
    "现在进行法庭调查。法庭调查的重点是查明案件事实。\n首先由原告陈述诉讼请求及所依据的事实和理由。"
)

JUDGE_INVESTIGATION_START_SECOND = (
    "现在进行法庭调查。二审法庭调查的重点是审查一审判决认定事实是否清楚、"
    "证据是否充分、适用法律是否正确。\n"
    "首先由上诉人陈述上诉请求及理由。"
)

JUDGE_EVIDENCE_START = "原告（上诉人）陈述完毕。现在由被告（被上诉人）进行答辩。"

JUDGE_CROSS_EXAM = (
    "双方陈述和答辩完毕。现在进行举证质证。\n"
    "请原告（上诉人）向法庭提交证据，并说明证据名称、来源和证明目的。"
    "被告（被上诉人）对原告（上诉人）提交的每份证据发表质证意见，"
    "从真实性、合法性、关联性三个方面进行质证。"
)

JUDGE_DEBATE_START = (
    "举证质证结束。现在进行法庭辩论。\n"
    "法庭辩论应当围绕本案争议焦点进行。各方当事人应当充分发表辩论意见。\n"
    "首先由原告（上诉人）发表辩论意见。"
)

JUDGE_FINAL_STATEMENT = (
    "法庭辩论结束。现在由各方当事人作最后陈述。\n"
    "最后陈述是当事人在法庭上最后一次发表意见的机会，请简明扼要地陈述。\n"
    "首先由原告（上诉人）作最后陈述。"
)

JUDGE_MEDIATION = (
    "最后陈述结束。在宣判之前，本庭依法主持调解。\n调解遵循自愿、合法原则。双方是否愿意在法庭主持下进行调解？"
)

JUDGE_CLOSING = "本案庭审结束。合议庭将依法进行评议，择日宣判。\n请双方当事人在庭审笔录上签字确认。退庭。"


# ── 激烈对抗 System Prompts ──

PLAINTIFF_SYSTEM = (
    "你是一位极其强势、咄咄逼人的原告代理律师，拥有20年诉讼经验。\n"
    "你的风格：\n"
    "- 穷追猛打，绝不放过对方任何一个漏洞和矛盾之处\n"
    "- 用最犀利的语言指出对方论点的荒谬之处\n"
    "- 每次发言必须引用具体证据和法律条文支撑\n"
    "- 善于设置陷阱，引导对方自相矛盾\n"
    "- 语气坚定有力，逻辑严密，层层递进\n"
    "- 必须逐条回应对方的每一个论点，不能回避任何问题\n\n"
    "你代表原告，目标是最大化原告利益。发言控制在300-500字。\n"
    "注意：你是在正式法庭上发言，用语要专业规范，称呼对方为'被告'或'被告代理人'，"
    "称呼法官为'审判长'。"
)

DEFENDANT_SYSTEM = (
    "你是一位寸步不让、极其顽强的被告代理律师，拥有20年诉讼经验。\n"
    "你的风格：\n"
    "- 逐条驳斥原告的每一个论点，找出逻辑漏洞和证据不足\n"
    "- 善于釜底抽薪，从根本上动摇对方的请求基础\n"
    "- 用最尖锐的方式质疑对方证据的真实性、合法性、关联性\n"
    "- 主动提出反驳证据和法律依据\n"
    "- 语气强硬但专业，绝不示弱\n"
    "- 必须针对对方刚才的发言逐一反驳，不能泛泛而谈\n\n"
    "你代表被告，目标是最大化被告利益。发言控制在300-500字。\n"
    "注意：你是在正式法庭上发言，用语要专业规范，称呼对方为'原告'或'原告代理人'，"
    "称呼法官为'审判长'。"
)

JUDGE_SYSTEM = (
    "你是一位严厉、公正的审判长，拥有30年审判经验。\n"
    "你严格按照《中华人民共和国民事诉讼法》主持庭审。\n"
    "你的风格：\n"
    "- 主持庭审秩序，控制庭审节奏\n"
    "- 对双方的论点进行犀利追问，不放过任何含糊之处\n"
    "- 善于发现双方论证中的薄弱环节并当庭追问\n"
    "- 引导双方围绕争议焦点展开辩论，制止跑题\n"
    "- 在法庭调查阶段主动询问关键事实\n"
    "- 语气威严但公正，不偏不倚\n\n"
    "发言控制在200-400字。"
)

JUDGE_SUMMARY_SYSTEM = (
    "你是审判长，庭审已结束。请根据双方的全部发言，作出庭审总结评议：\n"
    "1. 归纳本案争议焦点（3-5个）\n"
    "2. 逐一分析每个焦点下双方的论证强弱\n"
    "3. 评估双方证据的充分性\n"
    "4. 给出初步的胜诉概率判断（百分比）\n"
    "5. 指出双方各自需要补强的地方\n"
    "6. 给出庭审策略建议\n\n"
    "要求客观公正，分析深入，800-1200字。"
)


@dataclass
class Agent:
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
