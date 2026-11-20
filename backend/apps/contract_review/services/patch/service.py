"""写补丁的两步：**收集**（不落盘）与**单点应用**（一次写盘 + 二次校验 mtime）。

## 为什么必须拆成两步

三栏并答时，每一栏手里的 `original` 都是"我读到的那一刻的原文"。第一栏直接落盘
之后，第二栏的 `original` 就已经失效——它会失败（看起来像模型笨），或者更糟：
在别处撞上同一串字，改错位置。所以并答期间只允许产出 **patch 草案**
（`collect_patch`，零落盘），等律师裁决后由 `apply_patches` **一次**写盘。

"一次"是字面意思：同一份文件的全部改动先在内存里落成修订痕迹，最后只做一次
`save_file_content`。逐条写盘会把"第二条改不动"变成"文件已经被改了一半"。

## 二次校验 mtime（乐观锁）

提案时记下 `base_mtime`，应用前再比一次；真正兜底的是
`save_file_content(expect_mtime=...)` 里那次原子 CAS（读与写之间没有窗口）。
容差与那里同口径（1 秒），见 `bound_folder_browse.save_file_content` 的注释。

同一份文件上多条 patch 的 `base_mtime` **必须一致**（它们记的是同一个文件的
mtime）：出现两个不同的值，说明有人在这期间动过文件，此时应用任何一份都可能
盖掉那次改动 → 一律按冲突拒绝，让律师重新看一眼再裁决。

## 冲突与重复

`detect_conflicts` 的 `overlap_diff`（同一段原文、两种改法）**直接拒绝应用**：
B1 阶段不做自动挑选，挑错一段比多问一句贵得多。`duplicate`（同一段、同一改法）
不拒绝——重复提案合并成一次写盘，其余行记 `merged` 状态（不是 `applied`：
它们没有各自写盘，只是内容已经被写入）。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table
from docx.text.paragraph import Paragraph

from apps.contract_review.services.write_contracts import PatchConflict, WritePatch
from apps.core.exceptions import ConflictError, ValidationException

from ..formatting.docx_revision_tool import DocxRevisionTool, enable_track_changes, visible_text
from ..review.direct_edit_service import (
    DEFAULT_AUTHOR,
    _browse,
    _bump_editor_doc_key,
    _read_bytes,
    locate_paragraph,
    read_file_mtime,
)
from .conflict import detect_conflicts
from .models import ContractWritePatch, PatchOwnerKind, PatchStatus

logger = logging.getLogger(__name__)

#: mtime 比较容差（秒）。与 `bound_folder_browse.save_file_content` 同一口径：
#: 不同文件系统的 mtime 精度不同（ext4 纳秒 / HFS+ 秒），严格相等会误报冲突。
MTIME_TOLERANCE = 1.0

_OWNER_KINDS = frozenset(PatchOwnerKind.values)


def to_write_patch(row: ContractWritePatch) -> WritePatch:
    """存储行 → 冻结契约里的领域对象（冲突检测与应用只认领域对象）。"""
    return WritePatch(
        patch_id=row.patch_id,
        session_id=row.session_id,
        turn=row.turn,
        agent_kind=row.agent_kind,
        run_id=row.run_id,
        owner_kind=row.owner_kind,  # type: ignore[arg-type]  # choices 保证取值
        owner_id=row.owner_id,
        subpath=row.subpath,
        original=row.original,
        replacement=row.replacement,
        base_mtime=row.base_mtime,
        status=row.status,  # type: ignore[arg-type]  # 同上
        created_at=row.created_at,
    )


def collect_patch(
    *,
    owner_kind: str,
    owner_id: int,
    subpath: str,
    original: str,
    replacement: str,
    base_mtime: float | None = None,
    session_id: str = "",
    turn: int = 0,
    agent_kind: str = "",
    run_id: str = "",
) -> WritePatch:
    """登记一条候选改写（**不碰磁盘**）。

    `original` / `replacement` 原样入库：定位靠逐字原文，任何归一化都会让应用
    时对不上（见 `models.py` 的模块 docstring）。

    Raises:
        ValidationException: 归属/路径/原文/改写为空或非法。
    """
    if owner_kind not in _OWNER_KINDS:
        raise ValidationException(message=f"owner_kind 仅支持 contract/case，收到：{owner_kind!r}")
    if owner_id <= 0:
        raise ValidationException(message="owner_id 必须为正整数", errors={"owner_id": owner_id})
    clean_subpath = (subpath or "").strip()
    if not clean_subpath:
        raise ValidationException(message="subpath 不能为空", errors={"subpath": subpath})
    if not (original or "").strip():
        raise ValidationException(message="original 不能为空：它是定位锚点", errors={"original": ""})
    if not (replacement or "").strip():
        raise ValidationException(message="replacement 不能为空", errors={"replacement": ""})

    row = ContractWritePatch.objects.create(
        owner_kind=owner_kind,
        owner_id=owner_id,
        subpath=clean_subpath,
        original=original,
        replacement=replacement,
        base_mtime=base_mtime,
        session_id=session_id or "",
        turn=turn,
        agent_kind=agent_kind or "",
        run_id=run_id or "",
        status=PatchStatus.PROPOSED,
    )
    logger.info(
        "patch 草案已登记 patch=%s owner=%s/%s subpath=%s turn=%s",
        row.patch_id,
        owner_kind,
        owner_id,
        clean_subpath,
        turn,
    )
    return to_write_patch(row)


def docx_full_text(doc: DocumentType) -> str:
    """docx 的"全文"口径（冲突区间用它算）：正文与表格按文档顺序，段落间用 `\\n`。

    不直接用 `doc.paragraphs`：那会漏掉表格里的条款（付款方式、违约金常写在表
    格里），于是"同一段被两种改法命中"在表格里永远判不出来。
    """
    lines: list[str] = []
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            lines.append(visible_text(block))
        elif isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    lines.extend(visible_text(paragraph) for paragraph in cell.paragraphs)
    return "\n".join(lines)


def apply_patches(
    *,
    patch_ids: Sequence[str],
    note: str = "",
    user: Any | None = None,
    org_access: dict[str, Any] | None = None,
    perm_open_access: bool = False,
    author: str = DEFAULT_AUTHOR,
) -> dict[str, Any]:
    """把选中的 patch **一次性**写进文件（以 Word 修订痕迹留痕）。

    Args:
        patch_ids: 律师裁决后的 patch 清单；必须同属**一份文件**。
        note: 应用备注（留痕）；B4 的 Decision 落地前先存在 patch 行上。
        user / org_access / perm_open_access: 走与划词直改同一套绑定文件夹 ACL。

    Returns:
        ``{"subpath", "name", "applied": [...], "merged": [...]}``。

    Raises:
        ValidationException: patch 不存在 / 跨文件 / 状态不是草案。
        ConflictError: 互斥冲突（同一段两种改法）或文件在提案后被改过（409）。
    """
    rows = _load_rows(patch_ids)
    owner_kind, owner_id, subpath = _single_target(rows)
    _require_proposed(rows)
    clean_note = (note or "").strip()[:200]

    browse = _browse(owner_kind)
    source = _read_bytes(
        browse,
        owner_id=owner_id,
        subpath=subpath,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
    doc = Document(BytesIO(source))
    patches = [to_write_patch(row) for row in rows]
    conflicts = detect_conflicts(patches, {subpath: docx_full_text(doc)})
    _reject_mutex(rows, conflicts)

    applied_ids, merged_ids = _split_duplicates(patches, conflicts)
    _reject_stale_mtime(
        applied_ids,
        subpath=subpath,
        patches=patches,
        actual_mtime=_mtime_or_none(
            browse,
            owner_id=owner_id,
            subpath=subpath,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        ),
    )

    payload = _render_revisions(doc, patches=patches, keep_ids=applied_ids, subpath=subpath, author=author)
    browse.save_file_content(
        owner_id=owner_id,
        subpath=subpath,
        data=payload,
        # 二次校验的最后一道：读与写之间没有窗口（见模块 docstring）
        expect_mtime=_cas_mtime(patches, applied_ids),
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
    _mark_applied(applied_ids, merged_ids, note=clean_note)
    _bump_editor_doc_key(kind=owner_kind, owner_id=owner_id, subpath=subpath)
    logger.info(
        "patch 已一次性应用 owner=%s/%s subpath=%s applied=%s merged=%s",
        owner_kind,
        owner_id,
        subpath,
        applied_ids,
        merged_ids,
    )
    return {
        "subpath": subpath,
        "name": Path(subpath).name,
        "applied": applied_ids,
        "merged": merged_ids,
    }


def _load_rows(patch_ids: Sequence[str]) -> list[ContractWritePatch]:
    """按 id 取行；缺失/空清单直接拒绝（不猜"是不是已经应用过"）。"""
    ids = [str(pid).strip() for pid in patch_ids if str(pid).strip()]
    if not ids:
        raise ValidationException(message="patch_ids 不能为空", errors={"patch_ids": list(patch_ids)})
    rows = {row.patch_id: row for row in ContractWritePatch.objects.filter(patch_id__in=ids)}
    missing = sorted(set(ids) - set(rows))
    if missing:
        raise ValidationException(message=f"patch 不存在：{missing}", errors={"missing": missing})
    # 按入参顺序返回，日志/返回体与律师勾选的顺序一致
    return [rows[pid] for pid in dict.fromkeys(ids)]


def _single_target(rows: Sequence[ContractWritePatch]) -> tuple[str, int, str]:
    """一次只能应用同一份文件上的 patch（跨文件无法"一次性"）。"""
    targets = {(row.owner_kind, row.owner_id, row.subpath) for row in rows}
    if len(targets) > 1:
        raise ValidationException(
            message="一次只能应用同一份文件上的 patch",
            errors={"targets": sorted(f"{kind}:{oid}:{sub}" for kind, oid, sub in targets)},
        )
    owner_kind, owner_id, subpath = targets.pop()
    return owner_kind, int(owner_id), subpath


def _require_proposed(rows: Sequence[ContractWritePatch]) -> None:
    """只应用"草案"；已应用/已否决的行再应用一次就是重复写盘。"""
    stale = {row.patch_id: row.status for row in rows if row.status != PatchStatus.PROPOSED}
    if stale:
        raise ValidationException(message=f"patch 状态不是草案，不能应用：{stale}", errors={"statuses": stale})


def _reject_mutex(rows: Sequence[ContractWritePatch], conflicts: Sequence[PatchConflict]) -> None:
    """互斥冲突 → 标 `conflict` 并拒绝应用（一份都不写）。"""
    mutex = [conflict for conflict in conflicts if conflict.kind == "overlap_diff"]
    if not mutex:
        return
    conflicted = {pid for conflict in mutex for pid in conflict.patch_ids}
    ContractWritePatch.objects.filter(patch_id__in=conflicted, status=PatchStatus.PROPOSED).update(
        status=PatchStatus.CONFLICT
    )
    raise ConflictError(
        message="同一段原文有两种不同的改法，需律师裁决后再应用",
        code="PATCH_OVERLAP",
        errors={"conflicts": [conflict.summary for conflict in mutex]},
    )


def _split_duplicates(
    patches: Sequence[WritePatch],
    conflicts: Sequence[PatchConflict],
) -> tuple[list[str], list[str]]:
    """按冲突分组去重：每组 `duplicate` 只留第一条写盘，其余记 merged。"""
    keep = [patch.patch_id for patch in patches]
    merged: list[str] = []
    for conflict in conflicts:
        if conflict.kind != "duplicate":
            continue
        first, *rest = conflict.patch_ids
        for patch_id in rest:
            if patch_id in keep:
                keep.remove(patch_id)
            merged.append(patch_id)
    return keep, merged


def _reject_stale_mtime(
    patch_ids: Sequence[str],
    *,
    subpath: str,
    patches: Sequence[WritePatch],
    actual_mtime: float | None,
) -> None:
    """二次校验 mtime：提案后文件被改过 / 同一份文件出现两个基准值 → 409。"""
    bases = {patch.base_mtime for patch in patches if patch.base_mtime is not None}
    if len(bases) > 1:
        raise ConflictError(
            message="这几条 patch 的基准 mtime 不一致（期间文件已被改过），请重新生成候选",
            code="FILE_MODIFIED",
            errors={"base_mtimes": sorted(bases), "patch_ids": list(patch_ids)},
        )
    if not bases:
        logger.warning("patch 未带 base_mtime，跳过乐观锁二次校验 subpath=%s patches=%s", subpath, list(patch_ids))
        return
    base = bases.pop()
    if actual_mtime is not None and abs(actual_mtime - base) > MTIME_TOLERANCE:
        raise ConflictError(
            message="文件在提案后被修改过，请重新打开确认后再应用",
            code="FILE_MODIFIED",
            errors={"mtime": actual_mtime, "expect": base},
        )


def _mtime_or_none(browse: Any, **kwargs: Any) -> float | None:
    """取当前 mtime；ACL 已在上游校验过（这里只为乐观锁服务，取不到就不锁）。"""
    try:
        return read_file_mtime(browse, **kwargs)
    except Exception:
        logger.warning("patch 应用前取 mtime 失败（乐观锁退化为不锁）", exc_info=True)
        return None


def _cas_mtime(patches: Sequence[WritePatch], patch_ids: Sequence[str]) -> float | None:
    """交给 `save_file_content` 的 expect_mtime（原子 CAS 用）。"""
    wanted = set(patch_ids)
    for patch in patches:
        if patch.patch_id in wanted and patch.base_mtime is not None:
            return patch.base_mtime
    return None


def _render_revisions(
    doc: DocumentType,
    *,
    patches: Sequence[WritePatch],
    keep_ids: Sequence[str],
    subpath: str,
    author: str,
) -> bytes:
    """在内存里把每一条 patch 落成修订痕迹；任何一条落空都整批拒绝。

    "落空"包括：原文已不在文档里（律师刚改过）、选区跨段、格式无法定位。
    这时**一个字都不写**——半批应用会让律师看到"改了一半"的文档，且再点一次
    应用会因为状态已变而卡住。
    """
    wanted = set(keep_ids)
    enable_track_changes(doc)
    tool = DocxRevisionTool()
    for patch in patches:
        if patch.patch_id not in wanted:
            continue
        paragraph = locate_paragraph(doc, patch.original)
        if paragraph is None:
            raise ConflictError(
                message="文档里已找不到这段原文（可能刚被改过），请重新生成候选",
                code="PATCH_ANCHOR_MISSING",
                errors={"patch_id": patch.patch_id, "subpath": subpath},
            )
        if not tool.apply_revision(paragraph, patch.original, patch.replacement, author=author):
            raise ConflictError(
                message="无法在原文里精确落笔（选区可能跨段或含特殊格式）",
                code="PATCH_ANCHOR_UNRESOLVED",
                errors={"patch_id": patch.patch_id, "subpath": subpath},
            )
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _mark_applied(applied_ids: Sequence[str], merged_ids: Sequence[str], *, note: str) -> None:
    """写盘成功后一次性改状态（失败不回滚状态：文件已经写进去了）。"""
    ContractWritePatch.objects.filter(patch_id__in=list(applied_ids)).update(
        status=PatchStatus.APPLIED, note=note
    )
    if merged_ids:
        ContractWritePatch.objects.filter(patch_id__in=list(merged_ids)).update(
            status=PatchStatus.MERGED, note=note
        )


__all__ = ["MTIME_TOLERANCE", "apply_patches", "collect_patch", "docx_full_text", "to_write_patch"]
