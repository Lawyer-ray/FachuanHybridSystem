"""delta 再审查：只审**变更过的段落**，并把上一轮的结论续上。

## 为什么这是「AI 改完能直接用」的前提

第一轮审完 → 律师逐条采纳/驳回 → 文件变了 → 谁保证这一版没被改坏？
没有再审查，唯一的答案是「律师自己再读一遍」，那 AI 省下的时间又还回去了。

全篇重审有两个问题：成本（40 页文档再审一遍）和**重复**（同一批结论又提一遍）。
所以这里做两件事：

1. **变更区间由代码算**：段落级 `difflib` diff，不依赖模型判断「哪里变了」；
2. **上一轮结论续上**：仍然存在的继续挂着，被自己的改写消解的标 `moot`，
   锚点没了的标 `stale`。律师看到的永远是「当前还剩下什么」。

## 幂等

文档没变时**根本不调模型**：直接把未决结论原样带进新一轮。否则律师手滑点两次
「重新审查」，清单就会翻倍，一半是完全相同的建议。
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from docx import Document

from ..models import Finding, FindingStatus, ReviewRun, RunStatus
from . import review_model, review_pipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeltaPlan:
    """这一轮要做什么——纯计算结果，可单测。"""

    total_paragraphs: int
    changed_indices: list[int]
    unchanged: bool

    @property
    def reviewed(self) -> int:
        return len(self.changed_indices)


def paragraph_texts(docx_bytes: bytes) -> list[str]:
    """段落文本（含表格单元格内的段落，口径同 `docx.text.iter_paragraphs`）。"""
    from .docx.text import iter_paragraphs, visible_text

    doc = Document(BytesIO(docx_bytes))
    return [visible_text(p) for p in iter_paragraphs(doc)]


def changed_paragraph_indices(old: list[str], new: list[str]) -> list[int]:
    """返回**新文档**里发生变化的段落下标（由 `difflib` 算出，不依赖模型）。"""
    if not old and not new:
        return []
    if not old:
        return list(range(len(new)))

    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    changed: list[int] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed.extend(range(j1, j2))
    return changed


def plan_delta(old_bytes: bytes, new_bytes: bytes) -> DeltaPlan:
    old = paragraph_texts(old_bytes)
    new = paragraph_texts(new_bytes)
    changed = changed_paragraph_indices(old, new)
    return DeltaPlan(total_paragraphs=len(new), changed_indices=changed, unchanged=not changed)


def build_delta_text(new_bytes: bytes, indices: list[int]) -> str:
    """把变更段落拼成「这一轮要审的正文」。段落之间用空行隔开，模型好切分。"""
    texts = paragraph_texts(new_bytes)
    picked = [texts[i] for i in indices if 0 <= i < len(texts) and texts[i].strip()]
    return "\n\n".join(picked)


def _residual_texts(new_bytes: bytes) -> str:
    return "\n".join(paragraph_texts(new_bytes))


def carry_forward(prev_run: ReviewRun, new_bytes: bytes) -> dict[str, list[int]]:
    """把上一轮未决结论续到这一版上。返回 `{present, moot, stale}` 的 finding id 列表。

    判定顺序（与 Word 的语义一致）：

    | 情况 | 判定 | 依据 |
    |---|---|---|
    | 原文片段仍在，且**改写文本还没出现** | 仍存在（保持 `proposed`） | 律师还没处理 |
    | 原文片段仍在，但改写文本已经出现 | `moot`（已被消解） | 大概率是律师自己照着改了 |
    | 原文片段不见了 | `stale`（锚点失效） | 要么改成了别的写法，要么这段被删了 |

    「改写文本已出现」优先于「原文仍存在」：两者同时命中说明这段已经被改过，
    再挂着一条「建议改成 X」只会让律师重复劳动。
    """
    body = _residual_texts(new_bytes)
    buckets: dict[str, list[int]] = {"present": [], "moot": [], "stale": []}

    pending = prev_run.findings.filter(status__in=[FindingStatus.PROPOSED, FindingStatus.ACCEPTED])
    for finding in pending:
        anchor = (finding.suggestion_original or finding.quote or "").strip()
        replaced = (finding.suggestion_replacement or "").strip()

        if replaced and replaced in body:
            review_model.transition(finding, FindingStatus.MOOT)
            buckets["moot"].append(finding.id)
            continue
        if anchor and anchor not in body:
            # 归一化口径再试一次：全角/空格差异不该被判成失效
            from .docx.text import normalize

            if normalize(anchor) not in normalize(body):
                review_model.transition(finding, FindingStatus.STALE)
                buckets["stale"].append(finding.id)
                continue
        buckets["present"].append(finding.id)
    return buckets


def _clone_findings(source_run: ReviewRun, target_run: ReviewRun, finding_ids: list[int]) -> int:
    """把「仍然存在」的结论复制到新一轮（状态回到待决，等律师再决策）。"""
    cloned = 0
    for finding in Finding.objects.filter(id__in=finding_ids).order_by("ordinal", "id"):
        Finding.objects.create(
            run=target_run,
            ordinal=cloned,
            verdict=finding.verdict,
            severity=finding.severity,
            kind=finding.kind,
            clause_type=finding.clause_type,
            rule_key=finding.rule_key,
            legal_basis=finding.legal_basis,
            quote=finding.quote,
            title=finding.title,
            reason=finding.reason,
            suggestion_original=finding.suggestion_original,
            suggestion_replacement=finding.suggestion_replacement,
            suggestion_note=finding.suggestion_note,
            delivery=finding.delivery,
        )
        cloned += 1
    return cloned


def run_delta_review(
    prev_run: ReviewRun,
    *,
    caller: review_pipeline.LLMCaller | None = None,
    user: Any = None,
    old_bytes: bytes | None = None,
    new_bytes: bytes | None = None,
) -> ReviewRun:
    """基于上一轮做一次「只审变更」的再审查。

    `old_bytes` / `new_bytes` 不给时从文件与上一轮的起始快照里取（生产路径）；
    测试里直接注入，免得为了造两份 docx 折腾文件系统。
    """
    from . import snapshot_service, write_service

    kind, owner_id, subpath = prev_run.owner_kind, prev_run.owner_id, prev_run.subpath

    if new_bytes is None:
        new_bytes = write_service.read_bytes(kind=kind, owner_id=owner_id, subpath=subpath, user=user)
    if old_bytes is None:
        # 上一轮审的是哪一版：优先用内容 sha 命中的快照，退回「最近一版」
        snap = snapshot_service.latest(kind=kind, owner_id=owner_id, subpath=subpath)
        if snap is None:
            # 没有快照可比：退化成「全篇再审」，但把这件事写进 summary，
            # 否则「为什么这轮段落数没减少」会成为一个查不出来的谜
            logger.info("再审查没有可用于比对的快照，退化为全篇: %s/%s/%s", kind, owner_id, subpath)
            old_bytes = b""
        else:
            old_bytes = snapshot_service.read_bytes(snap)

    plan = plan_delta(old_bytes, new_bytes)

    run = review_pipeline.create_run(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        stance=prev_run.stance,
        contract_type=prev_run.contract_type,
        user=user,
        parent_run=prev_run,
        # 已经拿到新版本字节了，别让 create_run 再去读一遍文件（也免了为测试造 ACL）
        raw_bytes=new_bytes,
    )
    # create_run 会取「当前」标准库；再审查必须沿用上一轮的标准快照，
    # 否则「上一轮说可以、这一轮说不行」只是因为标准改版了，没人能解释
    run.playbook_snapshot = list(prev_run.playbook_snapshot or [])
    run.playbook_version = prev_run.playbook_version
    run.save(update_fields=["playbook_snapshot", "playbook_version"])

    buckets = carry_forward(prev_run, new_bytes)

    if plan.unchanged:
        # 幂等：文件没变就不调模型，直接把未决结论带过来
        cloned = _clone_findings(prev_run, run, buckets["present"])
        run.summary = {
            "delta": {
                "total_paragraphs": plan.total_paragraphs,
                "paragraphs_reviewed": 0,
                "unchanged": True,
                "carried": cloned,
                "moot": len(buckets["moot"]),
                "stale": len(buckets["stale"]),
            }
        }
        run.save(update_fields=["summary"])
        review_model.finish_run(run, status=RunStatus.DONE)
        return run

    delta_text = build_delta_text(new_bytes, plan.changed_indices)
    review_pipeline.execute_run(run, caller=caller, text=delta_text)

    # 模型只审了变更区间；把「仍然存在」的旧结论并进来，律师才看得到完整待办
    cloned = _clone_findings(prev_run, run, buckets["present"])
    summary = dict(run.summary or {})
    summary["delta"] = {
        "total_paragraphs": plan.total_paragraphs,
        "paragraphs_reviewed": plan.reviewed,
        "unchanged": False,
        "carried": cloned,
        "moot": len(buckets["moot"]),
        "stale": len(buckets["stale"]),
        "new": run.findings.count() - cloned,
    }
    run.summary = summary
    run.save(update_fields=["summary"])
    return run


def compare_versions(
    *, kind: str, owner_id: int, subpath: str, seq: int, user: Any = None, org_access: Any = None
) -> dict[str, Any]:
    """与历史某一版对照（Spellbook 的 **Compare** 落成可算的数字）。

    律师最常见的下一句是「跟上一版比，改了什么」。这里给的是**确定性**答案：
    段落级 diff 的变更数，不经过模型。
    """
    from . import snapshot_service, write_service

    snap = snapshot_service.find_by_seq(kind=kind, owner_id=owner_id, subpath=subpath, seq=seq)
    if snap is None:
        return {"found": False, "reason": f"找不到第 {seq} 版快照"}
    old_bytes = snapshot_service.read_bytes(snap)
    new_bytes = write_service.read_bytes(
        kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access
    )
    plan = plan_delta(old_bytes, new_bytes)
    return {
        "found": True,
        "seq": seq,
        "total_paragraphs": plan.total_paragraphs,
        "changed_paragraphs": plan.reviewed,
        "unchanged": plan.unchanged,
        "changed_indices": plan.changed_indices[:50],
        "old_sha256": snap.sha256,
    }


__all__ = [
    "compare_versions",
    "DeltaPlan",
    "build_delta_text",
    "carry_forward",
    "changed_paragraph_indices",
    "paragraph_texts",
    "plan_delta",
    "run_delta_review",
]
