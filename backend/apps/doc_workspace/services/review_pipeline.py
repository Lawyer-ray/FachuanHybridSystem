"""审查执行链：标准库 → 提示词 → 结论 → 立场对齐 → 三道闸 → 落库。

## 为什么结论要再过一层「立场对齐」（而不是全交给模型）

同一份合同代表甲方还是乙方，结论方向是**相反**的：同一条「违约金对等」的缺失，
站在受保护一方是高风险，站在另一方几乎没损失。把这件事完全交给模型，表现是
「换个立场重跑，结果时对时不对」。

所以标准库的每条检查项都声明 `beneficiary`（保护谁），程序按 run 的 `stance`
确定性地调整严重度与结论。模型只负责「这一段是否偏离标准」，**不负责判断这对谁
有利**——那是可以写死的规则，也是唯一能被测试钉住的部分。

## 三道闸（治过度审查）

过度审查是产品缺陷，不是勤奋：提 60 条、其中 40 条是「建议措辞更严谨」，律师
会把整份清单当噪音扔掉。三道闸各有可测判据：

| 闸 | 判据 |
|---|---|
| 提示词闸 | 只报「会造成经济损失或诉讼风险」，`kind=format` 占比 ≤ 20% |
| 条数闸 | 主清单 ≤ 25 条，超限按 severity 截断并要求模型自选（不是砍尾部） |
| 交付闸 | 一页纸 Top-3 必须带量化后果，写不出来的降级回清单 |
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from django.db import transaction
from django.utils import timezone

from ..models import (
    Beneficiary,
    Consequence,
    Delivery,
    Finding,
    FindingKind,
    Jurisdiction,
    ReviewRun,
    RiskSource,
    RuleClass,
    RunStatus,
    Severity,
    SourceWeight,
    Stage,
    Stance,
    Verdict,
)
from . import playbook_service, review_model, write_service

logger = logging.getLogger(__name__)

#: 一次 LLM 调用（注入点）。测试注入假函数，生产用默认实现。
LLMCaller = Callable[[list[dict[str, str]]], str]

MAX_MAIN_ITEMS = 25
FORMAT_RATIO_MAX = 0.20
TOP_N = 3

_SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH]

#: 量化后果的判据：出现数字 + 单位/比例/期限，才算「说不改会亏什么」。
_QUANTIFIED_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|万|亿|元|日|天|个月|年|倍|次|条|页)")

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


@dataclass
class GateReport:
    """三道闸的执行结果（写进 `run.summary`，可观测才叫闸）。"""

    dropped_format: int = 0
    dropped_cap: int = 0
    dropped_no_impact_from_top: int = 0
    mandatory_protected: int = 0
    """被闸门豁免的强制性条目数（它们既不被格式闸丢、也不被条数闸截）"""
    format_ratio_before: float = 0.0
    format_ratio_after: float = 0.0
    kept: int = 0
    top: list[str] = field(default_factory=list)


def _downgrade(severity: str) -> str:
    try:
        index = _SEVERITY_ORDER.index(severity)  # type: ignore[arg-type]
    except ValueError:
        return severity
    return _SEVERITY_ORDER[max(0, index - 1)]


def align_to_stance(
    *,
    beneficiary: str,
    stance: str,
    verdict: str,
    severity: str,
    rule_class: str = RuleClass.CONTRACTUAL,
) -> tuple[str, str, str]:
    """按立场调整结论。返回 `(verdict, severity, direction)`。

    `direction`：
    - `favor_us`  —— 这条标准保护我们，偏离 = 我们吃亏
    - `favor_them`—— 这条标准保护对方，偏离对我们无害 → 降一档
    - `neutral`   —— 对等条款或中立复核，不调整
    """
    # **强制性规则免疫立场对齐**：抵押未解除就转让、投资未达 25%、划拨地未审批……
    # 这些不是「对谁有利」的问题，是「转让本身可能无效」的问题。把它们的严重度
    # 按立场降一档，等于告诉律师「这条对你不重要」，而它会让整笔交易落空。
    if rule_class == RuleClass.MANDATORY:
        return verdict, severity, "mandatory"
    if stance == Stance.NEUTRAL or beneficiary == Beneficiary.NEUTRAL:
        return verdict, severity, "neutral"
    if beneficiary == stance:
        # 保护我们：缺失/偏离都要按标准库给的严重度算，不能降
        return verdict, severity, "favor_us"
    # 保护对方：偏离对我们反而是有利的，降一档并保留「观察到偏离」的事实
    return verdict, _downgrade(severity), "favor_them"


def has_quantified_consequence(text: str) -> bool:
    return bool(_QUANTIFIED_RE.search(text or ""))


def enforce_gates(
    items: list[dict[str, Any]],
    *,
    max_items: int = MAX_MAIN_ITEMS,
    format_ratio_max: float = FORMAT_RATIO_MAX,
    top_n: int = TOP_N,
) -> tuple[list[dict[str, Any]], GateReport]:
    """三道闸。返回 `(保留下来的条目, 报告)`。"""
    report = GateReport()
    total = len(items)
    if not total:
        return [], report

    formats = [i for i in items if i.get("kind") == FindingKind.FORMAT]
    report.format_ratio_before = round(len(formats) / total, 4)

    kept = list(items)

    # 闸一：格式类占比超限 → 从**低严重度**的格式条目开始丢。
    #
    # 注意分母会跟着变小：丢掉一条格式条目，分子和分母同时 -1，所以不能一次
    # 算好「该丢几条」，只能循环到占比真的落进阈值内。若清单里只有 2 条实质
    # 结论，20% 意味着格式条目标本应为 0 —— 这正是想要的结果（没有实质内容时
    # 不要拿格式条目凑数）。
    def _protected(item: dict[str, Any]) -> bool:
        """强制性规则不参与任何一道丢弃。"""
        return item.get("rule_class") == RuleClass.MANDATORY

    while kept:
        format_count = len([i for i in kept if i.get("kind") == FindingKind.FORMAT])
        if not format_count or format_count / len(kept) <= format_ratio_max:
            break
        victims = [i for i in kept if i.get("kind") == FindingKind.FORMAT and not _protected(i)]
        if not victims:
            break
        victim = min(victims, key=lambda i: _SEVERITY_ORDER.index(i.get("severity", Severity.LOW)))
        kept = [i for i in kept if i is not victim]
        report.dropped_format += 1

    # 闸二：条数上限 → 按严重度保留（高在前），**不是砍尾部**。
    # 强制性条目先占位、永不被截：条数闸治的是「格式/措辞类噪音」，
    # 把一条「合同可能无效」挤出去，等于用降噪的理由制造漏判。
    protected = [i for i in kept if _protected(i)]
    report.mandatory_protected = len(protected)
    if len(kept) > max_items:
        rest = [i for i in kept if not _protected(i)]
        room = max(0, max_items - len(protected))
        ranked = sorted(rest, key=lambda i: -_SEVERITY_ORDER.index(i.get("severity", Severity.LOW)))
        keep_ids = {id(i) for i in ranked[:room]} | {id(i) for i in protected}
        report.dropped_cap = len(kept) - len(keep_ids)
        kept = [i for i in kept if id(i) in keep_ids]

    live = len(kept)
    report.format_ratio_after = round(
        (len([i for i in kept if i.get("kind") == FindingKind.FORMAT]) / live) if live else 0.0, 4
    )
    report.kept = live

    # 闸三：Top-N 必须带量化后果；写不出来的降级回清单（不给上台）
    top_candidates = sorted(
        (i for i in kept if i.get("verdict") != Verdict.NOT_APPLICABLE),
        key=lambda i: -_SEVERITY_ORDER.index(i.get("severity", Severity.LOW)),
    )
    for item in top_candidates:
        if len(report.top) >= top_n:
            break
        impact = str(item.get("impact") or item.get("reason") or "")
        if not has_quantified_consequence(impact):
            item["in_top"] = False
            report.dropped_no_impact_from_top += 1
            continue
        item["in_top"] = True
        report.top.append(str(item.get("title") or item.get("rule_key") or ""))
    return kept, report


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


def _default_llm_call(messages: list[dict[str, str]]) -> str:
    from apps.core.llm.service import LLMService

    response = LLMService().chat(
        messages,
        temperature=0.2,
        # 16384 在「标准库 25 条 + 域外法条文原文」的提示词下不够：真机实测模型把
        # 预算花在输出分析文字上，JSON 被截断在半句（`审查结果不是合法 JSON`）。
        # 32k 给足余量；超时单独放到 300s——单条审查 2 分钟属正常。
        max_tokens=32768,
        fallback=True,
        timeout_seconds=300,
        # **审查是结构化抽取，不是思辨题**：必须关掉思考。
        # 真机症状：kimi-2.6 开着思考审泰国合同，3 分钟全花在输出
        # 「We need answer JSON only, first char { last }…」这类过程文字上，
        # JSON 一个字符都没写出来 → 整轮审查零结论。
        enable_thinking=False,
    )
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    return str(content or "")


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


@dataclass
class ReviewOutput:
    """一次审查的完整产出：标的画像 + 关系网 + 结论。"""

    findings: list[dict[str, Any]] = field(default_factory=list)
    subject_profile: list[str] = field(default_factory=list)
    relations: list[dict[str, str]] = field(default_factory=list)


def parse_review_output(raw: str) -> ReviewOutput:
    """解析模型输出。**同时兼容两种形状**：

    - 新契约：`{"subject_profile": [...], "relations": [...], "findings": [...]}`；
    - 老契约：裸 JSON 数组（早期版本 / 测试桩）。

    兼容不是偷懒：模型遵守新契约的比例永远不是 100%，而「因为整体结构不合规就把
    整份审查结果丢掉」是不可接受的——宁可少拿标的画像，也要把结论留下。
    """
    if not (raw or "").strip():
        return ReviewOutput()
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # 先试对象
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    if obj:
        try:
            parsed = json.loads(obj.group(0))
        except json.JSONDecodeError:
            parsed = None
        # **必须确认它真是新契约**：模型返回单元素数组 `[{...}]` 时，上面的
        # `\{.*\}` 只会截到内层那个对象，那个对象里没有 findings 键——若直接当成
        # 新契约，结论就被整份丢掉了（真机踩过：一份只有 1 条意见的合同永远空清单）。
        if isinstance(parsed, dict) and ({"findings", "subject_profile", "relations"} & set(parsed)):
            findings = parsed.get("findings")
            profile = parsed.get("subject_profile")
            relations = parsed.get("relations")
            return ReviewOutput(
                findings=[i for i in findings if isinstance(i, dict)] if isinstance(findings, list) else [],
                subject_profile=[str(p_) for p_ in profile if str(p_).strip()] if isinstance(profile, list) else [],
                relations=[
                    {
                        "relation": str(r.get("relation") or "").strip(),
                        "why": str(r.get("why") or "").strip(),
                        "risk": str(r.get("risk") or "").strip(),
                    }
                    for r in relations
                    if isinstance(r, dict) and str(r.get("relation") or "").strip()
                ]
                if isinstance(relations, list)
                else [],
            )

    # 截断抢救：模型把预算花在前面的口语分析上时，JSON 会被切在半句。
    # 整份丢弃的代价是「AI 审了半天，清单空白」——比拿到 3 条不完整结论严重得多。
    salvaged = _salvage_findings(text)
    if salvaged:
        logger.warning("审查输出被截断，已抢救出 %d 条结论", len(salvaged))
        return ReviewOutput(findings=salvaged)

    # 退回老契约：裸数组
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        logger.warning("审查结果无法解析（既不是对象也不是数组），前 200 字：%s", text[:200])
        return ReviewOutput()
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("审查结果不是合法 JSON，前 200 字：%s", text[:200])
        return ReviewOutput()
    return ReviewOutput(findings=[i for i in data if isinstance(i, dict)] if isinstance(data, list) else [])


def _salvage_findings(text: str) -> list[dict[str, Any]]:
    """从**被截断**的模型输出里捞出所有完整的 finding 对象。

    只做一件事：从 `"findings"` 后面的 `[` 开始按括号配对扫，遇到配对完整的
    `{...}` 就 `json.loads` 一次，遇到不完整的（被截断）就停。`subject_profile`
    与 `relations` 在截断场景下一律放弃——结论优先，画像可以下一轮再拿。

    刻意**不猜**：不补引号、不补逗号、不把半截对象当完整对象。捞不出来就返回空，
    让上层走「零结论 + 失败提示」这条确定路径，而不是拿一份改过的 JSON 去写库。
    """
    start = text.find('"findings"')
    if start < 0:
        return []
    array_start = text.find("[", start)
    if array_start < 0:
        return []

    findings: list[dict[str, Any]] = []
    depth = 0
    obj_start: int | None = None
    in_string = False
    escaped = False
    for index in range(array_start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                obj_start = index
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                chunk = text[obj_start : index + 1]
                obj_start = None
                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    findings.append(parsed)
            continue
        if char == "]" and depth == 0:
            break
    return findings


def parse_findings(raw: str) -> list[dict[str, Any]]:
    """兼容旧调用方：只取结论。"""
    return parse_review_output(raw).findings


def _normalize_item(
    item: dict[str, Any], *, rules_by_key: dict[str, dict[str, Any]], stance: str
) -> dict[str, Any] | None:
    rule_key = str(item.get("rule_key") or "").strip()
    rule = rules_by_key.get(rule_key)
    if rule is None:
        # 模型自创检查项：不入库。闸一拦不住的东西必须在这里拦。
        logger.info("丢弃自创检查项：%s", rule_key or "(空)")
        return None

    verdict = str(item.get("verdict") or Verdict.DEVIATION)
    if verdict not in Verdict.values:
        verdict = Verdict.DEVIATION
    severity = str(item.get("severity") or rule.get("severity_if_missing") or Severity.MEDIUM)
    if severity not in Severity.values:
        severity = Severity.MEDIUM

    rule_class = str(rule.get("rule_class") or RuleClass.CONTRACTUAL)
    verdict, severity, direction = align_to_stance(
        beneficiary=str(rule.get("beneficiary") or Beneficiary.NEUTRAL),
        stance=stance,
        verdict=verdict,
        severity=severity,
        rule_class=rule_class,
    )

    replacement = str(item.get("suggestion_replacement") or "").strip()
    note = str(item.get("suggestion_note") or "").strip()
    if replacement:
        delivery = Delivery.BOTH if note else Delivery.REVISION
    elif note:
        delivery = Delivery.COMMENT
    else:
        delivery = Delivery.LIST_ONLY

    risk_source = str(item.get("risk_source") or RiskSource.STATUTE)
    if risk_source not in RiskSource.values:
        risk_source = RiskSource.STATUTE
    source_weight = str(item.get("source_weight") or SourceWeight.CORE)
    if source_weight not in SourceWeight.values:
        source_weight = SourceWeight.CORE

    case_ref = str(item.get("case_ref") or "").strip()[:255]
    if risk_source == RiskSource.CASE and not case_ref:
        # 声称「据类案」却给不出案号 = 无法回指。降为辅助来源：可以留作线索，
        # 但不能当决定性依据（编案号比不提类案严重得多）。
        source_weight = SourceWeight.SUPPORTING

    return {
        "rule_key": rule_key,
        "case_ref": case_ref,
        "clause_type": str(rule.get("clause_type") or ""),
        "rule_class": rule_class,
        "stage": str(rule.get("stage") or Stage.GENERAL),
        "risk_source": risk_source,
        "source_weight": source_weight,
        "consequence": str(rule.get("consequence") or Consequence.BREACH),
        # 强制性条目的严重度不由模型决定：标准库里写的是什么就是什么。
        # 否则模型一句「这里影响不大」就能把「可能无效」降成低危。
        "severity": str(rule.get("severity_if_missing") or severity) if rule_class == RuleClass.MANDATORY else severity,
        "legal_basis": str(rule.get("legal_basis") or ""),
        "verdict": verdict,
        "kind": FindingKind.RISK,
        "quote": str(item.get("quote") or "").strip(),
        "title": (str(item.get("title") or "") or rule_key)[:200],
        "reason": str(item.get("reason") or ""),
        "impact": str(item.get("impact") or ""),
        "suggestion_original": str(item.get("suggestion_original") or "").strip(),
        "suggestion_replacement": replacement,
        "suggestion_note": note,
        "delivery": delivery,
        "direction": direction,
        "in_top": False,
    }


def create_run(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    stance: str = Stance.NEUTRAL,
    contract_type: str = "",
    jurisdiction: str = Jurisdiction.CN,
    playbook: Any = None,
    user: Any = None,
    org_access: Any = None,
    parent_run: ReviewRun | None = None,
    raw_bytes: bytes | None = None,
) -> ReviewRun:
    """只建轮次（不调模型）：接口层先返回 run_id，模型在后台跑。

    **为什么拆开**：一次审查要几十秒，同步 HTTP 会超时。而且律师需要先看到
    「正在审查」这个状态，而不是转圈 60 秒。
    """
    from io import BytesIO

    from docx import Document

    from .docx.text import full_text

    code = playbook_service.normalise_jurisdiction(jurisdiction)
    book = playbook or playbook_service.resolve(contract_type=contract_type, stance=stance, jurisdiction=code)
    rules = playbook_service.snapshot_rules(book)

    if raw_bytes is None:
        raw_bytes = write_service.read_bytes(
            kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access
        )
    text = full_text(Document(BytesIO(raw_bytes)))

    run = ReviewRun.objects.create(
        owner_kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        contract_type=contract_type,
        jurisdiction=code,
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        stance=stance,
        playbook_key=f"{book.org_id or 'builtin'}:{book.jurisdiction or code}:{book.contract_type or 'general'}:{book.stance}",
        playbook_version=book.version,
        playbook_snapshot=rules,
        status=RunStatus.QUEUED,
        parent_run=parent_run,
        created_by_id=getattr(user, "pk", None),
    )
    review_model.supersede_previous_runs(run)
    return run


def execute_run(run: ReviewRun, *, caller: LLMCaller | None = None, text: str | None = None) -> ReviewRun:
    """跑模型并落结论。可被同步调用（测试）或由后台任务调用。

    ## 为什么这个函数**不**是 `@transaction.atomic`

    它中间要等一次几十秒的模型调用 + 域外法查明（最坏 40s）。整段包在事务里，
    进程就在「idle in transaction」——而本项目的连接参数带
    `idle_in_transaction_session_timeout=60000`（`settings.DATABASES.OPTIONS`），
    于是**模型慢于 60 秒时，落库那一刻连接已被 PG 掐掉**，表现为
    `OperationalError: the connection is closed`，整轮审查作废。

    真机实测：一份 8 千字的泰国合同（提示词带域外法条文原文）就撞上了这条线。
    所以事务只包**真正的写库那一段**（删旧结论 → 写新结论 → 存 summary），
    外部调用一律在事务外。
    """
    from io import BytesIO

    from docx import Document

    from .docx.text import full_text

    run.status = RunStatus.RUNNING
    run.save(update_fields=["status"])

    try:
        if text is None:
            raw_bytes = write_service.read_bytes(
                kind=run.owner_kind, owner_id=run.owner_id, subpath=run.subpath, user=None
            )
            text = full_text(Document(BytesIO(raw_bytes)))

        rules = list(run.playbook_snapshot or [])
        # 驳回理由回流：本客户历史上被反复驳回的条款，本轮降权（不删条目）
        from . import playbook_feedback

        feedback = playbook_feedback.collect(kind=run.owner_kind, owner_id=run.owner_id)

        # 类案检索：第三维风险来源。查的是「这个标的/这类条款在法院实际怎么判」。
        # 查询词只用规则与（再审查时）上一轮的标的画像——首轮还没跑模型，拿不到
        # 画像，硬要拿就得多一次模型调用，不值得。
        from . import case_evidence

        prev_profile = list((run.parent_run.summary or {}).get("subject_profile") or []) if run.parent_run else []
        queries = case_evidence.build_queries(
            subject_profile=prev_profile,
            relations=list((run.parent_run.summary or {}).get("relations") or []) if run.parent_run else [],
            rules=rules,
        )
        evidence = case_evidence.gather(
            queries=queries,
            facts=text[:4000],
            searcher=case_evidence.default_searcher(),
        )

        # 域外法查明：第五个风险来源，且是**唯一能机械判死的那个**。
        # 中国法域下也会跑（合同里可能引用外国法），但无引用时成本为 0。
        from . import foreign_law

        foreign = foreign_law.gather(text=text, jurisdiction=str(run.jurisdiction or Jurisdiction.CN))

        messages = build_prompt(
            rules=rules,
            contract_text=text,
            stance=str(run.stance),
            contract_type=str(run.contract_type),
            feedback=feedback.describe(),
            case_evidence=evidence.to_prompt_block(),
            jurisdiction=str(run.jurisdiction or Jurisdiction.CN),
            foreign_law_evidence=foreign.to_prompt_block(),
        )
        raw = (caller or _default_llm_call)(messages)
        produced = parse_review_output(raw)
        rules_by_key = {r["rule_key"]: r for r in rules}
        items = [
            x
            for x in (_normalize_item(i, rules_by_key=rules_by_key, stance=str(run.stance)) for i in produced.findings)
            if x
        ]
        playbook_feedback.apply_to_items(items, feedback)
        # 查明结论是**确定性事实**，不经 `_normalize_item`（它只管模型自创的 rule_key），
        # 直接在闸门前注入：查无此法就是查无此法，不需要模型同意。
        escalated = foreign_law.escalate_model_citations(items, foreign)
        items = [*items, *foreign_law.deterministic_findings(foreign)]
        kept, report = enforce_gates(items)

        # 事务只包围写库这一段：外部调用（模型 / BARLC）已经全部完成。
        with transaction.atomic():
            _persist_findings(
                run=run,
                kept=kept,
                report=report,
                feedback=feedback,
                produced=produced,
                evidence=evidence,
                foreign=foreign,
                escalated=escalated,
            )
        review_model.finish_run(run, status=RunStatus.DONE)
    except (RuntimeError, ValueError, TimeoutError, OSError, KeyError) as exc:
        # 模型侧的错误（超时/返回不可解析/后端 5xx）必须落成 failed，
        # 而不是让轮次永远停在 running。编程错误不在这里吞。
        logger.warning("审查执行失败: run=%s", run.id, exc_info=True)
        review_model.finish_run(run, status=RunStatus.FAILED, error=str(exc))
    return run


def _persist_findings(
    *,
    run: ReviewRun,
    kept: list[dict[str, Any]],
    report: GateReport,
    feedback: Any,
    produced: ReviewOutput,
    evidence: Any,
    foreign: Any,
    escalated: int,
) -> None:
    """把本轮结论与汇总写进库（事务内，**不含任何外部调用**）。

    整段只有 DB 写，因此可以被一个短事务包住；模型调用与域外法查明都在外面——
    见 `execute_run` docstring 里 `idle_in_transaction_session_timeout` 的坑。
    """
    Finding.objects.filter(run=run).delete()
    for ordinal, item in enumerate(kept):
        Finding.objects.create(
            run=run,
            ordinal=ordinal,
            verdict=item["verdict"],
            severity=item["severity"],
            kind=item["kind"],
            clause_type=item["clause_type"],
            rule_key=item["rule_key"],
            rule_class=item["rule_class"],
            stage=item["stage"],
            risk_source=item["risk_source"],
            source_weight=item["source_weight"],
            consequence=item["consequence"],
            case_ref=item["case_ref"],
            legal_basis=item["legal_basis"],
            quote=item["quote"],
            title=item["title"],
            reason=item["reason"],
            suggestion_original=item["suggestion_original"],
            suggestion_replacement=item["suggestion_replacement"],
            suggestion_note=item["suggestion_note"],
            delivery=item["delivery"],
        )
    run.summary = {
        "gates": report.__dict__,
        "feedback": {"suppressed": sorted(feedback.suppressed), "counts": feedback.rules},
        # 标的画像与关系网本身就是交付内容：律师要看到「AI 认为这块地特殊在哪、
        # 它扫了哪些关系方」。就算零结论，这两块也证明审查做了功。
        "subject_profile": produced.subject_profile,
        "relations": produced.relations,
        "stages": review_model.stage_rollup(items=kept),
        "case_evidence": evidence.to_summary(),
        # 域外法查明：律师要能看到「这份合同的哪几条法条被查过、结论是什么」。
        # 一条引用都没查也算结论（「合同里没引外国法」本身就是有用的信息）。
        "foreign_law": {**foreign.to_summary(), "escalated": escalated},
    }
    run.save(update_fields=["summary"])


def run_review(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    stance: str = Stance.NEUTRAL,
    contract_type: str = "",
    jurisdiction: str = Jurisdiction.CN,
    playbook: Any = None,
    user: Any = None,
    org_access: Any = None,
    caller: LLMCaller | None = None,
    parent_run: ReviewRun | None = None,
    text: str | None = None,
    raw_bytes: bytes | None = None,
) -> ReviewRun:
    """建轮次 + 同步执行（测试与脚本用；接口层走 create_run + 后台任务）。"""
    run = create_run(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        stance=stance,
        contract_type=contract_type,
        jurisdiction=jurisdiction,
        playbook=playbook,
        user=user,
        org_access=org_access,
        parent_run=parent_run,
        raw_bytes=raw_bytes,
    )
    # 给了字节就直接从这里取文本：execute_run 不必再去读文件（也免了测试造 ACL）
    if text is None and raw_bytes is not None:
        from io import BytesIO as _BytesIO

        from docx import Document as _Document

        from .docx.text import full_text as _full_text

        text = _full_text(_Document(_BytesIO(raw_bytes)))
    # 测试里直接给文本时优先用（避免为了造一个 docx 而额外依赖文件系统）
    if text is not None:
        run.content_sha256 = hashlib.sha256(text.encode()).hexdigest()
        run.save(update_fields=["content_sha256"])
    return execute_run(run, caller=caller, text=text)


def build_top_report(run: ReviewRun) -> str:
    """一页纸：Top-N + 出处 + 人效口径 + AI 参与声明。

    ## 三条来自市面产品的做法（一手证据见 market-refresh.md）

    1. **每条必须带出处**（Definely：「Every finding sourced, every change
       approved by you」）→ 每条列出 `rule_key` / 条款类型 / 法律依据，
       律师能自己判断这条意见的成色，而不是被动接受一个结论。
    2. **人效口径要说出来**（Luminance 打「75% reduction in repetitive contract
       review work」这类数字）→ 附上「评估 N 条 / 采纳 M 条 / 因商业考量未采纳 K 条」。
       这既是给客户看的审计价值，也是收费说明。
    3. **AI 参与声明**是中文法域交付时的挡箭牌 → 页脚写明「AI 辅助、律师逐条确认，
      未发现问题不等于无风险」。
    """
    findings = list(run.findings.all())
    applicable = [f for f in findings if f.verdict != Verdict.NOT_APPLICABLE]
    top = applicable[:TOP_N]

    lines = [f"# 《{run.subpath}》审查要点", ""]

    # 强制性事项先行：这类违反可能让合同**无效**，不能和「建议措辞」混在一个 Top-3 里。
    # 也不受 Top-3 限制——把 4 条「可能无效」压成 3 条是拿清单整齐换法律风险。
    mandatory = [f for f in findings if f.rule_class == RuleClass.MANDATORY]
    if mandatory:
        lines.append("## 一、强制性事项（违反可能导致合同无效 / 不得对抗第三人 / 被处罚）")
        for index, finding in enumerate(mandatory, 1):
            basis = f"；依据 {finding.legal_basis}" if finding.legal_basis else ""
            consequence = CONSEQUENCE_TEXT.get(str(finding.consequence), "")
            tag = f"，{consequence}" if consequence else ""
            lines.append(
                f"{index}. **{finding.title}**（{finding.severity}{tag}，"
                f"{finding.clause_type or finding.rule_key}{basis}）"
            )
            if finding.reason:
                lines.append(f"   - 不改会怎样：{finding.reason}")
        lines.append("")

    lines.append("## 二、最要紧的几条" if mandatory else "## 最要紧的几条")
    for index, finding in enumerate(top, 1):
        impact = finding.reason or finding.title
        lines.append(f"{index}. **{finding.title}**（{finding.severity}）")
        lines.append(f"   - 不改会怎样：{impact}")
        origin = " / ".join(x for x in (finding.clause_type, finding.rule_key) if x)
        if origin:
            lines.append(f"   - 出处：{origin}" + (f"；依据 {finding.legal_basis}" if finding.legal_basis else ""))
        source = f"{RISK_SOURCE_TEXT.get(str(finding.risk_source), str(finding.risk_source))}"
        weight = "核心" if str(finding.source_weight) == SourceWeight.CORE else "辅助"
        lines.append(f"   - 来源：{source}（{weight}）")
        if finding.status != "proposed":
            lines.append(f"   - 当前状态：{finding.status}")

    stages = (run.summary or {}).get("stages") or review_model.stage_rollup(run=run)
    lines += ["", "## 覆盖情况（按阶段）"]
    for stage_key, bucket in stages.items():
        label = STAGE_TEXT.get(stage_key, stage_key)
        lines.append(
            f"- {label}：{bucket.get('total', 0)} 条"
            + (f"（高 {bucket.get('high', 0)}）" if bucket.get("high") else "")
            + ("——**本阶段无结论**" if not bucket.get("total") else "")
        )

    summary = run.summary or {}
    accepted = int(summary.get("accepted") or 0)
    rejected = int(summary.get("rejected") or 0)
    commercial = sum(1 for f in findings if f.reject_reason_code in ("commercial", "client_refused"))
    if applicable or accepted or rejected:
        lines += [
            "",
            "## 工作量",
            f"- 按标准评估 {len(applicable)} 项，其中需处理 {len(findings)} 项；"
            f"律师已采纳 {accepted} 项、驳回 {rejected} 项"
            + (f"（其中因商业考量/客户决定未采纳 {commercial} 项）" if commercial else ""),
        ]
    if summary.get("gates"):
        gates = summary["gates"]
        lines.append(
            f"- 已按三道闸过滤：格式类占比 {gates.get('format_ratio_after')}（上限 {FORMAT_RATIO_MAX}）、"
            f"主清单 {gates.get('kept')} 条（上限 {MAX_MAIN_ITEMS}）"
        )

    lines += [
        "",
        "> 本清单由 AI 辅助生成，全部修改需经执业律师逐条确认；「未发现问题」不等于无风险，也不构成法律意见。",
    ]
    return "\n".join(lines)


def stamp_finished(run: ReviewRun) -> None:
    if run.finished_at is None:
        run.finished_at = timezone.now()
        run.save(update_fields=["finished_at"])
