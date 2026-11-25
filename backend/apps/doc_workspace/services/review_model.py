"""审查结论的状态机、落笔与口径统计。

## 为什么状态机要写死在代码里

七个状态各自代表一件**不同的事**，而它们的差别只在「下一步该做什么」：

| 状态 | 含义 | 下一步 |
|---|---|---|
| `proposed` | AI 提了，律师还没看 | 等裁决 |
| `accepted` | 已采纳（修订/批注已落进文件） | 结束 |
| `rejected` | 律师驳回，带理由码 | 结束（理由码进统计） |
| `stale` | 锚点失效：原文已经不在文档里了 | 重新框选后可回到 `proposed` |
| `moot` | 已被消解：律师自己把这段改了 | 结束 |
| `merged` | 与另一条重复，被合并 | 结束 |
| `unanchored` | 一开始就锚不到（缺失项、无法定位） | 人工补锚后可回到 `proposed` |

**没有 `stale` / `moot` 会怎样**：律师边改边让 AI 审，清单里挂着「建议把 X 改成 Y」
而 X 早就不在了；点「定位」跳到空白处，信任损毁只发生一次。

允许的迁移写在 `ALLOWED` 里，非法迁移直接抛错——静默放过一个非法迁移，等于
让状态机名存实亡，而统计口径全靠它。
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from django.db import transaction
from django.utils import timezone

from ..models import Delivery, Finding, FindingStatus, RejectReason, ReviewRun, RunStatus, Severity, Verdict

logger = logging.getLogger(__name__)

#: 允许的状态迁移。终态（accepted / rejected / moot / merged）不可再变——
#: 要改结论就新建一条 finding，历史结论不能就地改写（审计要求）。
ALLOWED: dict[str, frozenset[str]] = {
    FindingStatus.PROPOSED: frozenset(
        {
            FindingStatus.ACCEPTED,
            FindingStatus.REJECTED,
            FindingStatus.STALE,
            FindingStatus.MOOT,
            FindingStatus.MERGED,
            FindingStatus.UNANCHORED,
        }
    ),
    FindingStatus.UNANCHORED: frozenset(
        {
            FindingStatus.PROPOSED,
            FindingStatus.ACCEPTED,
            FindingStatus.REJECTED,
            FindingStatus.STALE,
            FindingStatus.MOOT,
            FindingStatus.MERGED,
        }
    ),
    FindingStatus.STALE: frozenset(
        {FindingStatus.PROPOSED, FindingStatus.ACCEPTED, FindingStatus.REJECTED, FindingStatus.MOOT}
    ),
    FindingStatus.ACCEPTED: frozenset(),
    FindingStatus.REJECTED: frozenset(),
    FindingStatus.MOOT: frozenset(),
    FindingStatus.MERGED: frozenset(),
}

TERMINAL = frozenset({FindingStatus.ACCEPTED, FindingStatus.REJECTED, FindingStatus.MOOT, FindingStatus.MERGED})

#: 进「误报」分子的理由码。只有这一个码算误报——「商业让步」「已被覆盖」是律师
#: 的专业判断，不是 AI 错了。
FALSE_POSITIVE_REASONS = frozenset({RejectReason.FALSE_POSITIVE})


class IllegalTransition(ValueError):
    """状态迁移不被允许（防止把历史结论就地改写）。"""


def transition(
    finding: Finding,
    to_status: str,
    *,
    reason_code: str = "",
    note: str = "",
    user: Any = None,
    rev_ids: list[int] | None = None,
    comment_ids: list[int] | None = None,
) -> Finding:
    """迁移状态并记录裁决痕迹。非法迁移抛 `IllegalTransition`。"""
    current = str(finding.status)
    if to_status not in ALLOWED.get(current, frozenset()):
        raise IllegalTransition(f"结论 {finding.id} 不能从 {current} 迁到 {to_status}")

    fields: list[str] = ["status"]
    finding.status = to_status

    if to_status == FindingStatus.REJECTED:
        if not reason_code:
            raise ValueError("驳回必须给理由码（自由文本没法统计误报率）")
        if reason_code not in RejectReason.values:
            raise ValueError(f"未知驳回理由码：{reason_code}")
        finding.reject_reason_code = reason_code
        finding.reject_note = (note or "")[:255]
        finding.decided_by_id = getattr(user, "pk", None)
        finding.decided_at = timezone.now()
        fields += ["reject_reason_code", "reject_note", "decided_by_id", "decided_at"]
    elif to_status in (FindingStatus.ACCEPTED, FindingStatus.MOOT):
        finding.decided_by_id = getattr(user, "pk", None)
        finding.decided_at = timezone.now()
        fields += ["decided_by_id", "decided_at"]

    if rev_ids:
        finding.docx_rev_ids = [*finding.docx_rev_ids, *rev_ids]
        fields.append("docx_rev_ids")
    if comment_ids:
        finding.comment_ids = [*finding.comment_ids, *comment_ids]
        fields.append("comment_ids")

    finding.save(update_fields=fields)
    return finding


def accept(
    finding: Finding, *, user: Any = None, rev_ids: list[int] | None = None, comment_ids: list[int] | None = None
) -> Finding:
    return transition(finding, FindingStatus.ACCEPTED, user=user, rev_ids=rev_ids, comment_ids=comment_ids)


def reject(finding: Finding, *, reason_code: str, note: str = "", user: Any = None) -> Finding:
    return transition(finding, FindingStatus.REJECTED, reason_code=reason_code, note=note, user=user)


def mark_stale(finding: Finding) -> Finding:
    return transition(finding, FindingStatus.STALE)


def mark_moot(finding: Finding, *, user: Any = None) -> Finding:
    return transition(finding, FindingStatus.MOOT, user=user)


def apply_finding(
    finding: Finding,
    *,
    user: Any = None,
    org_access: Any = None,
    base_mtime: float | None = None,
) -> dict[str, Any]:
    """把一条结论**落到文件上**（修订或批注），并推进状态。

    ## 锚点失效 = `stale`，且文件一个字节都不动

    定位失败时 `write_service` 返回 `applied=False` 并且**根本没写盘**；这里只把
    状态改成 `stale` 就返回。绝不能降级成「改到最像的那一段」——法律文书容不得
    错位改字。
    """
    from ..models import FindingKind
    from . import write_service

    run = finding.run
    kind = run.owner_kind
    owner_id = run.owner_id
    subpath = run.subpath

    if finding.kind == FindingKind.MANUAL:
        # 人工留下的痕迹不需要 AI 再落一遍
        return {"applied": False, "reason": "人工痕迹不重复落笔", "status": str(finding.status)}

    if str(finding.status) not in (FindingStatus.PROPOSED, FindingStatus.STALE, FindingStatus.UNANCHORED):
        return {"applied": False, "reason": f"结论已处于终态（{finding.status}）", "status": str(finding.status)}

    payload: dict[str, Any] = {"applied": False, "status": str(finding.status)}

    wants_revision = finding.delivery in (Delivery.REVISION, Delivery.BOTH) and finding.suggestion_replacement.strip()
    wants_comment = finding.delivery in (Delivery.COMMENT, Delivery.BOTH)

    if wants_revision:
        result = write_service.apply_span(
            kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            selection=finding.suggestion_original,
            suggested=finding.suggestion_replacement,
            base_mtime=base_mtime,
            user=user,
            org_access=org_access,
        )
        if not result.get("applied"):
            # 锚点失效：文件没动，状态置 stale，律师重新框选后可以再来
            mark_stale(finding)
            return {
                "applied": False,
                "reason": result.get("reason", ""),
                "status": str(finding.status),
                "stale": True,
            }
        payload.update(applied=True, rev_ids=result.get("rev_ids") or [])

    if wants_comment:
        text = finding.suggestion_note or finding.reason or finding.title
        result = write_service.apply_comments(
            kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            comments=[{"selection": finding.quote or finding.suggestion_original, "text": text}],
            user=user,
            org_access=org_access,
        )
        if result.get("applied"):
            # 批注也算「落笔成功」：delivery=comment 的结论本来就不改正文，
            # 不能因为没写修订就把 applied 判成 False
            payload["applied"] = True
            payload.update(comment_ids=result.get("comment_ids") or [])

    if not payload.get("applied") and not payload.get("comment_ids"):
        # 只进清单的结论（list_only）也算「采纳」——律师把它当检查项确认过了
        if finding.delivery != Delivery.LIST_ONLY:
            return payload

    accept(finding, user=user, rev_ids=payload.get("rev_ids"), comment_ids=payload.get("comment_ids"))
    payload["status"] = str(finding.status)
    return payload


def run_metrics(run: ReviewRun) -> dict[str, Any]:
    """覆盖率 / 误报率 / 采纳率——**每一个分母都写明它是什么**。

    没有 `not_applicable` 这一档时，一份只有 6 条可审条款的框架协议会被算成
    「47 条标准里满足 6 条 = 12 分」。所以分母必须是「适用条款数」。
    """
    findings = list(run.findings.all())
    total = len(findings)

    verdicts = Counter(str(f.verdict) for f in findings)
    statuses = Counter(str(f.status) for f in findings)
    severities = Counter(str(f.severity) for f in findings)

    applicable = total - verdicts.get(Verdict.NOT_APPLICABLE, 0)
    compliant = sum(1 for f in findings if f.verdict == Verdict.COMPLIANT)
    coverage = (compliant / applicable) if applicable else 0.0

    accepted = statuses.get(FindingStatus.ACCEPTED, 0)
    rejected = statuses.get(FindingStatus.REJECTED, 0)
    reviewed = accepted + rejected
    accept_rate = (accepted / reviewed) if reviewed else 0.0
    false_positives = sum(
        1 for f in findings if f.status == FindingStatus.REJECTED and f.reject_reason_code in FALSE_POSITIVE_REASONS
    )
    false_positive_rate = (false_positives / reviewed) if reviewed else 0.0

    top = sorted(
        (f for f in findings if f.verdict != Verdict.NOT_APPLICABLE and f.severity == Severity.HIGH),
        key=lambda f: f.ordinal,
    )[:3]

    return {
        "total": total,
        "applicable": applicable,
        "compliant": compliant,
        "coverage": round(coverage, 4),
        "accepted": accepted,
        "rejected": rejected,
        "reviewed": reviewed,
        "accept_rate": round(accept_rate, 4),
        "false_positives": false_positives,
        "false_positive_rate": round(false_positive_rate, 4),
        "by_verdict": dict(verdicts),
        "by_status": dict(statuses),
        "by_severity": dict(severities),
        "top_high": [{"id": f.id, "title": f.title} for f in top],
    }


def refresh_summary(run: ReviewRun) -> ReviewRun:
    """把口径统计并进 `summary`，**不覆盖**已有键。

    `summary` 是一个共享袋子：`gates`（三道闸的报告）与 `delta`（再审查的段落对比）
    都在里面。上一版直接 `run.summary = run_metrics(run)`，把先写进去的键全抹掉了
    ——表现是「明明跑了 delta 再审查，`summary` 里却查不到 delta」。
    """
    merged = dict(run.summary or {})
    merged.update(run_metrics(run))
    run.summary = merged
    run.save(update_fields=["summary"])
    return run


@transaction.atomic
def finish_run(run: ReviewRun, *, status: str = RunStatus.DONE, error: str = "") -> ReviewRun:
    run.status = status
    run.error_message = error[:2000]
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error_message", "finished_at"])
    return refresh_summary(run)


def supersede_previous_runs(run: ReviewRun) -> int:
    """同一份文件上更早的、还没结束的轮次标记为被取代。

    不这么做的话，同一份文件会同时挂着两个 `proposed` 清单，律师看到的建议里
    有一半是上一版的。
    """
    return int(
        ReviewRun.objects.filter(
            owner_kind=run.owner_kind,
            owner_id=run.owner_id,
            subpath=run.subpath,
            id__lt=run.id,
        )
        .exclude(status__in=[RunStatus.SUPERSEDED, RunStatus.FAILED])
        .update(status=RunStatus.SUPERSEDED)
    )
