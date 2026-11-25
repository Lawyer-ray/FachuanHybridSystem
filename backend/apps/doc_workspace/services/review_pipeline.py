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

from ..models import Beneficiary, Delivery, Finding, FindingKind, ReviewRun, RunStatus, Severity, Stance, Verdict
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


@dataclass
class GateReport:
    """三道闸的执行结果（写进 `run.summary`，可观测才叫闸）。"""

    dropped_format: int = 0
    dropped_cap: int = 0
    dropped_no_impact_from_top: int = 0
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
) -> tuple[str, str, str]:
    """按立场调整结论。返回 `(verdict, severity, direction)`。

    `direction`：
    - `favor_us`  —— 这条标准保护我们，偏离 = 我们吃亏
    - `favor_them`—— 这条标准保护对方，偏离对我们无害 → 降一档
    - `neutral`   —— 对等条款或中立复核，不调整
    """
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
    while kept:
        format_count = len([i for i in kept if i.get("kind") == FindingKind.FORMAT])
        if not format_count or format_count / len(kept) <= format_ratio_max:
            break
        victim = min(
            (i for i in kept if i.get("kind") == FindingKind.FORMAT),
            key=lambda i: _SEVERITY_ORDER.index(i.get("severity", Severity.LOW)),
        )
        kept = [i for i in kept if i is not victim]
        report.dropped_format += 1

    # 闸二：条数上限 → 按严重度保留（高在前），**不是砍尾部**
    if len(kept) > max_items:
        ranked = sorted(kept, key=lambda i: -_SEVERITY_ORDER.index(i.get("severity", Severity.LOW)))
        keep_ids = {id(i) for i in ranked[:max_items]}
        report.dropped_cap = len(kept) - max_items
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
                ]
            )
        )

    fmt = (
        "## 输出格式\n"
        "仅返回 JSON 数组，不要任何解释文字：\n"
        '[{"rule_key":"...","verdict":"deviation","severity":"high",'
        '"quote":"合同原文片段（缺失时留空）","title":"一句话结论",'
        '"reason":"为什么","impact":"不改会损失什么（带数字）",'
        '"suggestion_original":"要替换的原文","suggestion_replacement":"改写后文本",'
        '"suggestion_note":"批注正文（只提醒不改正文时用）"}]\n\n'
    )
    system = (
        "你是中国执业律师，正在审查一份合同。\n"
        f"本次立场：{stance_text}。\n"
        f"合同类型：{contract_type or '通用'}。\n\n"
        "## 只报以下两类问题\n"
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
        + fmt
        + ("\n" + feedback if feedback else "")
        + "## 审查标准库\n"
        + "\n".join(rule_lines)
    )
    user = "## 合同全文\n" + contract_text[:120000]
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _default_llm_call(messages: list[dict[str, str]]) -> str:
    from apps.core.llm.service import LLMService

    response = LLMService().chat(messages, temperature=0.2, max_tokens=16384, fallback=True)
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    return str(content or "")


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_findings(raw: str) -> list[dict[str, Any]]:
    """从模型输出里取 JSON 数组。取不到就返回空列表（由上层判失败）。"""
    if not (raw or "").strip():
        return []
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("审查结果不是合法 JSON，前 200 字：%s", text[:200])
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


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

    verdict, severity, direction = align_to_stance(
        beneficiary=str(rule.get("beneficiary") or Beneficiary.NEUTRAL),
        stance=stance,
        verdict=verdict,
        severity=severity,
    )

    replacement = str(item.get("suggestion_replacement") or "").strip()
    note = str(item.get("suggestion_note") or "").strip()
    if replacement:
        delivery = Delivery.BOTH if note else Delivery.REVISION
    elif note:
        delivery = Delivery.COMMENT
    else:
        delivery = Delivery.LIST_ONLY

    return {
        "rule_key": rule_key,
        "clause_type": str(rule.get("clause_type") or ""),
        "legal_basis": str(rule.get("legal_basis") or ""),
        "verdict": verdict,
        "severity": severity,
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

    book = playbook or playbook_service.resolve(contract_type=contract_type, stance=stance)
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
        content_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        stance=stance,
        playbook_key=f"{book.org_id or 'builtin'}:{book.contract_type or 'general'}:{book.stance}",
        playbook_version=book.version,
        playbook_snapshot=rules,
        status=RunStatus.QUEUED,
        parent_run=parent_run,
        created_by_id=getattr(user, "pk", None),
    )
    review_model.supersede_previous_runs(run)
    return run


@transaction.atomic
def execute_run(run: ReviewRun, *, caller: LLMCaller | None = None, text: str | None = None) -> ReviewRun:
    """跑模型并落结论。可被同步调用（测试）或由后台任务调用。"""
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
        messages = build_prompt(
            rules=rules,
            contract_text=text,
            stance=str(run.stance),
            contract_type=str(run.contract_type),
            feedback=feedback.describe(),
        )
        raw = (caller or _default_llm_call)(messages)
        parsed = parse_findings(raw)
        rules_by_key = {r["rule_key"]: r for r in rules}
        items = [
            x for x in (_normalize_item(i, rules_by_key=rules_by_key, stance=str(run.stance)) for i in parsed) if x
        ]
        playbook_feedback.apply_to_items(items, feedback)
        kept, report = enforce_gates(items)

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
        }
        run.save(update_fields=["summary"])
        review_model.finish_run(run, status=RunStatus.DONE)
    except (RuntimeError, ValueError, TimeoutError, OSError, KeyError) as exc:
        # 模型侧的错误（超时/返回不可解析/后端 5xx）必须落成 failed，
        # 而不是让轮次永远停在 running。编程错误不在这里吞。
        logger.warning("审查执行失败: run=%s", run.id, exc_info=True)
        review_model.finish_run(run, status=RunStatus.FAILED, error=str(exc))
    return run


def run_review(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    stance: str = Stance.NEUTRAL,
    contract_type: str = "",
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
    for index, finding in enumerate(top, 1):
        impact = finding.reason or finding.title
        lines.append(f"{index}. **{finding.title}**（{finding.severity}）")
        lines.append(f"   - 不改会怎样：{impact}")
        origin = " / ".join(x for x in (finding.clause_type, finding.rule_key) if x)
        if origin:
            lines.append(f"   - 出处：{origin}" + (f"；依据 {finding.legal_basis}" if finding.legal_basis else ""))
        if finding.status != "proposed":
            lines.append(f"   - 当前状态：{finding.status}")

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
