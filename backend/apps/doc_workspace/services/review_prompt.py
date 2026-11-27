"""审查提示词渲染 —— 从 ``review_pipeline`` 拆出的纯渲染模块。

``build_prompt`` 只做一件事：把标准库（数据）与立场 / 法域 / 外部证据（参数）
拼成一对 messages。它不调模型、不读库，所以测试可以直接断言提示词里出现了
哪条硬约束，而不必跑一轮审查。

依赖方向单向：``review_pipeline`` import 本模块；本模块**不**反向 import。
原模块 ``review_pipeline`` 按原路径 re-export 本模块全部符号，历史 import 不断裂。
"""

from __future__ import annotations

from typing import Any

from ..models import Consequence, Jurisdiction, RiskSource, RuleClass, Stage, Stance

#: 立场 → 提示词里的一句话（用 `dict[str, str]` 而不是 `Stance` 键，避免 mypy 的
#: `.get(Stance, str)` 重载歧义）
_STANCE_TEXT: dict[str, str] = {
    Stance.PARTY_A: "代表甲方（我方是甲方）",
    Stance.PARTY_B: "代表乙方（我方是乙方）",
    Stance.NEUTRAL: "中立复核（不代表任何一方，按法律风险给意见）",
}

#: 法域 → 提示词里的「你是谁、按什么法审」。
#:
#: 以前这一行写死「你是中国执业律师」。审一份泰国土地租赁合同时，这句话会让模型：
#: ① 用中国法的形式要件（统一社会信用代码/不动产登记簿）去要求一份泰国合同；
#: ② 把自己知道的中国法条当依据写进 `legal_basis`；
#: ③ 完全不去想 Land Code / CCC 那几条真正的硬约束。
_JURISDICTION_TEXT: dict[str, str] = {
    Jurisdiction.CN: "你熟悉中国法，正在审查一份适用中国法的合同。",
    Jurisdiction.TH: (
        "你熟悉泰国法（Civil and Commercial Code / Land Code / Foreign Business Act / "
        "Condominium Act / Labour Protection Act / Revenue Code），正在审查一份适用**泰国法**的合同。"
    ),
    Jurisdiction.VN: "你熟悉越南法，正在审查一份适用**越南法**的合同。",
    Jurisdiction.MY: "你熟悉马来西亚法，正在审查一份适用**马来西亚法**的合同。",
    Jurisdiction.SG: "你熟悉新加坡法，正在审查一份适用**新加坡法**的合同。",
    Jurisdiction.ID: "你熟悉印度尼西亚法，正在审查一份适用**印度尼西亚法**的合同。",
    Jurisdiction.PH: "你熟悉菲律宾法，正在审查一份适用**菲律宾法**的合同。",
    Jurisdiction.LA: "你熟悉老挝法，正在审查一份适用**老挝法**的合同。",
    Jurisdiction.KH: "你熟悉柬埔寨法，正在审查一份适用**柬埔寨法**的合同。",
    Jurisdiction.MM: "你熟悉缅甸法，正在审查一份适用**缅甸法**的合同。",
    Jurisdiction.BN: "你熟悉文莱法，正在审查一份适用**文莱法**的合同。",
}

#: 非中国法域的提示词硬约束。
#:
#: 「不许凭记忆引外国法」必须是**显式规则**而不是期望：模型对外国法的记忆错误率远高于
#: 中国法，而错误的法条引用比不提法条更危险（看起来最专业）。
_FOREIGN_LAW_RULES = (
    "## 域外法硬约束（违反即整条结论作废）\n"
    "1. **不许凭记忆引用外国法条文**。只能引用「域外法查明结果」一节里实际列出的法条；\n"
    "2. 引用时必须写清「法名 + 条号」（如 `Civil and Commercial Code Section 540`），"
    "不写「泰国法律规定」这种无法核验的表述；\n"
    "3. 合同里出现的**查无此法 / 查无此条**引用，无论你觉得它多合理，都必须报出来；\n"
    "4. 你不确定某条是否现行有效时，写 `risk_source=scenario` 并在 `reason` 里注明「待查明」，"
    "不要编一个条号。\n\n"
)


#: 阶段/来源的中文文案（一页纸与前端各有一份，改文案只需改这里与前端标签表）
STAGE_TEXT: dict[str, str] = {
    Stage.BEFORE: "转让前（能不能转）",
    Stage.DURING: "转让中（怎么付、怎么交付、怎么登记）",
    Stage.AFTER: "转让后（谁背什么）",
    Stage.GENERAL: "通用",
}

CONSEQUENCE_TEXT: dict[str, str] = {
    Consequence.INVALID: "可能无效",
    Consequence.UNENFORCEABLE: "不得对抗第三人",
    Consequence.UNEFFECTIVE: "未生效（可补正）",
    Consequence.ADMINISTRATIVE: "处罚/登记受阻",
    Consequence.BREACH: "违约责任",
}

RISK_SOURCE_TEXT: dict[str, str] = {
    RiskSource.STATUTE: "法律规定",
    RiskSource.CASE: "案例检索",
    RiskSource.SCENARIO: "场景推演",
    RiskSource.SUBJECT: "标的特性",
}


def build_prompt(
    *,
    rules: list[dict[str, Any]],
    contract_text: str,
    stance: str,
    contract_type: str,
    feedback: str = "",
    case_evidence: str = "",
    jurisdiction: str = Jurisdiction.CN,
    foreign_law_evidence: str = "",
) -> list[dict[str, str]]:
    """把标准库渲染成提示词。

    **标准是数据不是散文**：每条检查项单独列出来，模型逐条判定。这样
    「故意漏报」和「超范围发挥」都能被后面的闸拦住。
    """
    stance_text = _STANCE_TEXT.get(stance, "中立复核")

    rule_lines = []
    for rule in rules:
        rule_lines.append(
            "\n".join(
                [
                    f"- rule_key: {rule['rule_key']}",
                    f"  条款类型: {rule['clause_type']}",
                    f"  标准表述: {rule['standard_text']}",
                    f"  可接受区间: {rule.get('acceptable_range') or '（必须与标准一致）'}",
                    f"  法律依据: {rule.get('legal_basis') or '（无）'}",
                    f"  必备条款: {'是' if rule.get('required') else '否'}",
                    f"  规则类别: {rule.get('rule_class') or RuleClass.CONTRACTUAL}"
                    f"（mandatory=违反可能无效，必须报、不许降级）",
                    f"  阶段: {rule.get('stage') or Stage.GENERAL}",
                ]
            )
        )

    fmt = (
        "## 输出格式（**先读这一节，它决定你的整份回答**）\n"
        "**你的回答第一个字符必须是 `{`，最后一个字符必须是 `}`。**\n"
        "禁止输出任何分析过程、思考过程、前言、结语、道歉或 Markdown 说明；"
        "「Let me analyze…」「We need…」这类文字写出来就等于本次审查作废——"
        "下游只解析 JSON，其余全部丢弃。\n"
        "若需要先想清楚再写，也**只能想完直接输出 JSON**。\n"
        "**顺序很重要：先画标的、再展开关系、最后逐条判定**。\n"
        "```\n"
        "{\n"
        '  "subject_profile": ["这个标的的特殊性，逐条列（如：工业用地/带产业监管/历史污染/设备与不动产混杂/需政府审批）"],\n'
        '  "relations": [{"relation":"关系方","why":"为什么必须扫","risk":"不扫会漏掉什么"}],\n'
        '  "findings": [{\n'
        '    "rule_key":"...","verdict":"deviation","severity":"high",\n'
        '    "risk_source":"statute|case|scenario|subject","case_ref":"案号（仅 when risk_source=case）",\n'
        '    "source_weight":"core|supporting",\n'
        '    "quote":"合同原文片段（缺失时留空）","title":"一句话结论",\n'
        '    "reason":"为什么","impact":"不改会损失什么（带数字）",\n'
        '    "suggestion_original":"要替换的原文","suggestion_replacement":"改写后文本",\n'
        '    "suggestion_note":"批注正文（只提醒不改正文时用）"}]\n'
        "}\n"
        "```\n\n"
        "- `risk_source` 必须标：这条是**据法条**（statute）、**据类案**（case）、"
        "**据流程推演**（scenario）、还是**据本标的特性**（subject）；\n"
        "- `source_weight`：决定性依据填 core，旁证填 supporting；\n"
        "- 若确实没有可报的问题，`findings` 返回空数组，但 `subject_profile` 与 "
        "`relations` 仍要填——它们本身就是交付内容。\n\n"
    )
    persona = _JURISDICTION_TEXT.get(jurisdiction, _JURISDICTION_TEXT[Jurisdiction.CN])
    foreign_block = _FOREIGN_LAW_RULES if jurisdiction != Jurisdiction.CN else ""
    system = (
        fmt
        + persona
        + "\n"
        + f"本次立场：{stance_text}。\n"
        + f"合同类型：{contract_type or '通用'}。\n\n"
        + foreign_block
        + "## 只报以下两类问题\n"
        "1. 会造成**经济损失**的（金额、违约金、赔偿、付款条件、结算方式）；\n"
        "2. 会造成**诉讼风险**的（管辖、仲裁、举证、解除、时效）。\n"
        "纯措辞优化、纯排版问题**不要报**。宁缺毋滥：漏报一条可接受的，"
        "比多报十条噪音代价小。\n\n"
        "## 判定口径\n"
        "- 每条结论必须对应下面**某一个 rule_key**，不要自创检查项；\n"
        "- `verdict` 只能是 compliant / deviation / missing / not_applicable；\n"
        "- 合同里**没有**该条款 → verdict=missing；有但与标准不符 → deviation；\n"
        "- 该条款对本合同类型**不适用** → not_applicable（这一档必须用，"
        "否则覆盖率会被算错）；\n"
        "- `impact` 必须写「不改会损失什么」，能给数字就给数字（金额/比例/期限）。\n\n"
        "## 先展开关系，再逐条判定\n"
        "合同不只是甲乙双方。审查前必须先列出**与这个标的绑在一起的其他人**，"
        "并逐个说清「谁、为什么必须扫、不扫会漏什么」：\n"
        "- 政府部门（出让方/审批/监管：规划、产业监管、环评、消防）；\n"
        "- 抵押权人、查封机关（权利受限时转让可能无效）；\n"
        "- 承租人等享有**优先购买权**的人；\n"
        "- 相邻地块权利人（地役权/通行/采光）；\n"
        "- 历史污染责任人、原土地使用权人（修复义务与承继义务）；\n"
        "- 地下资源（矿藏、地下水属国家所有）；\n"
        "- 共有权人/按份共有人。\n"
        "**没有对应关系方就写空数组，不要编造**；但漏掉一个真实存在的关系方，"
        "就等于漏掉一整类风险。\n\n"
        "## 规则类别决定动作\n"
        "- `mandatory`（强制性）：违反可能**无效 / 不得对抗第三人 / 被处罚**——"
        "必须报，且不要因为「对我方有利」就降低 `severity`；\n"
        "- `inherited`（承继性）：义务随标的一起转过来，漏了就替前人背债；\n"
        "- `procedural`（程序性）：办不成事（过户被退、登记卡住）；\n"
        "- `contractual`（契约性）：可以谈，属于商业判断。\n\n"
        + ("\n" + feedback if feedback else "")
        + ("\n" + case_evidence if case_evidence else "")
        + ("\n" + foreign_law_evidence if foreign_law_evidence else "")
        + "## 审查标准库\n"
        + "\n".join(rule_lines)
    )
    user = "## 合同全文\n" + contract_text[:120000]
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
