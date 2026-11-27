"""审查执行链：标准库 → 提示词 → 结论 → 立场对齐 → 三道闸 → 落库。

本模块只保留**执行链本身**（建轮次、调模型、落库、一页纸）。原来混在同一个文件里的
三个纯函数域已各自独立成模块，本模块按原路径 re-export 它们的全部符号，
``review_pipeline.X`` 的历史 import 与测试断言全部照旧可用：

- ``review_prompt``  —— 提示词渲染（``build_prompt``）与中文文案表；
- ``review_parse``   —— 模型输出解析、截断抢救、条目归一化；
- ``review_gates``   —— 立场对齐与三道闸（治过度审查的可测判据）。

依赖方向单向：本模块 → 上述三个模块，三个模块都不反向 import 本模块。

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
import logging
from typing import Any, Callable

from django.db import transaction
from django.utils import timezone

from ..models import Finding, Jurisdiction, ReviewRun, RuleClass, RunStatus, SourceWeight, Stance, Verdict
from . import playbook_service, review_model, write_service

# 解耦（2026-11-29）：提示词 / 解析 / 闸门三块纯函数分别搬到
# review_prompt / review_parse / review_gates，此处按原路径 re-export，
# 使 ``review_pipeline.build_prompt``、``review_pipeline._normalize_item``、
# ``review_pipeline.align_to_stance`` 等历史访问方式保持可用。
from .review_gates import (
    _QUANTIFIED_RE,
    _SEVERITY_ORDER,
    FORMAT_RATIO_MAX,
    MAX_MAIN_ITEMS,
    TOP_N,
    GateReport,
    _downgrade,
    align_to_stance,
    enforce_gates,
    has_quantified_consequence,
)
from .review_parse import (
    _JSON_ARRAY_RE,
    ReviewOutput,
    _normalize_item,
    _salvage_findings,
    parse_findings,
    parse_review_output,
)
from .review_prompt import (
    _FOREIGN_LAW_RULES,
    _JURISDICTION_TEXT,
    _STANCE_TEXT,
    CONSEQUENCE_TEXT,
    RISK_SOURCE_TEXT,
    STAGE_TEXT,
    build_prompt,
)

logger = logging.getLogger(__name__)

#: 一次 LLM 调用（注入点）。测试注入假函数，生产用默认实现。
LLMCaller = Callable[[list[dict[str, str]]], str]


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
