"""划词直改 API：框选一段 → 说一句要求 → 出候选 → 采纳落成修订。

## 为什么不是合同审查的一个子接口

审查是「任务」：上传、定立场、跑流水线、产物落盘、逐条决策，全程有状态。
划词直改是「一问一答」：律师已经框定范围、已经说出意图，不需要立场识别、
不需要全篇扫描、不需要评估报告。做成 `/contract-review/{task_id}/...` 的子路由
会逼着前端先造一个任务，而任务模型里的 `represented_party` 必填——正是
本次要摆脱的那个字段。

## 两个端点，职责不重叠

- `POST /direct-edit/suggest`：只调 LLM 出候选，**零副作用**。模型失败、
  超时、返回垃圾都不该动到律师的文件。
- `POST /direct-edit/apply`：只落盘，不再调 LLM。律师点哪条就写哪条。

拆开的直接好处：律师可以反复「换个说法再生成一次」，而文件始终是原样，
直到他明确采纳。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router, Schema

from apps.contract_review.schemas.direct_edit_schemas import (
    DirectEditApplyIn,
    DirectEditApplyOut,
    DirectEditSuggestIn,
    DirectEditSuggestOut,
    TaskEditApplyIn,
    TaskEditApplyOut,
)
from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger(__name__)
router = Router()


def _get_suggest_service() -> Any:  # pragma: no cover
    from apps.contract_review.services.review.direct_editor import get_direct_editor

    return get_direct_editor()


def _get_apply_service() -> Any:  # pragma: no cover
    from apps.contract_review.services.review.direct_edit_service import get_direct_edit_service

    return get_direct_edit_service()


def _resolve_target(contract_id: int | None, case_id: int | None) -> tuple[str, int]:
    """`contract_id` / `case_id` 二选一 → (kind, owner_id)。

    两个都给或都不给直接 422：直改的落盘目标必须唯一，猜一个就是写错文件。
    """
    from apps.core.exceptions import ValidationException

    if (contract_id is None) == (case_id is None):
        raise ValidationException(message="contract_id 与 case_id 必须二选一", errors={"contract_id": contract_id})
    if case_id is not None:
        return "case", case_id
    assert contract_id is not None
    return "contract", contract_id


def _load_paragraph_context(kind: str, owner_id: int, subpath: str, selection: str, user: Any) -> tuple[str, str]:
    """取选区所在段落，切出前后文给模型。

    失败一律返回空上下文：上下文是「让改写更贴合语境」的加分项，
    取不到（文件被移走、权限刚好变了、docx 解析失败）不该让整次改写失败。
    """
    from io import BytesIO

    from docx import Document

    from apps.contract_review.services.review.direct_edit_service import _browse, locate_paragraph
    from apps.contract_review.services.review.direct_editor import compute_context

    try:
        browse = _browse(kind)
        path = browse.resolve_file(
            owner_id=owner_id,
            subpath=subpath,
            user=user,
            org_access=getattr(user, "org_access", None),
            perm_open_access=False,
        )
        doc = Document(BytesIO(path.read_bytes()))
        para = locate_paragraph(doc, selection)
        if para is None:
            return "", ""
        # 现行文本口径（含修订插入）：模型与编辑器看到的是同一份文本
        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        return compute_context(visible_text(para), selection)
    except Exception:
        logger.warning(
            "划词直改：取上下文失败（不影响改写）kind=%s owner=%s subpath=%s", kind, owner_id, subpath, exc_info=True
        )
        return "", ""


@router.post("/suggest", response=DirectEditSuggestOut)
@rate_limit_from_settings("TASK", by_user=True)
async def suggest_edit(request: HttpRequest, payload: DirectEditSuggestIn) -> dict[str, Any]:
    """按律师的要求，为框选的这一段生成 2~3 条改写候选（不改文件）。"""
    user = request.user
    kind, owner_id = _resolve_target(payload.contract_id, payload.case_id)
    # 取上下文要先过 ACL（resolve_file 内部校验），所以放在线程池里跑同步 IO
    ctx_before, ctx_after = await sync_to_async(_load_paragraph_context, thread_sensitive=True)(
        kind, owner_id, payload.subpath, payload.selection, user
    )
    svc = _get_suggest_service()
    candidates = await sync_to_async(svc.suggest, thread_sensitive=True)(
        selection=payload.selection,
        instruction=payload.instruction,
        context_before=ctx_before,
        context_after=ctx_after,
        model_name=payload.model_name,
    )
    return {
        "candidates": [{"suggested": c.suggested, "reason": c.reason} for c in candidates],
        "context_before": ctx_before,
        "context_after": ctx_after,
    }


@router.post("/apply", response=DirectEditApplyOut)
@rate_limit_from_settings("TASK", by_user=True)
async def apply_edit(
    request: HttpRequest,
    payload: DirectEditApplyIn,
    expect_mtime: float | None = None,
) -> dict[str, Any]:
    """采纳一条候选：写成 Word 修订痕迹（`<w:del>` + `<w:ins>`）并覆写原文件。

    定位失败返回 `applied=false` 而不是报错——「选中的原文已被改过」是律师
    常见操作结果，前端要能提示「重新框选」，而不是弹 500。

    `expect_mtime`（query，与 `contracts/{id}/folder-save` 同口径）是**乐观锁**：
    调用方读到文件时的 mtime。不一致说明这期间文件已被别人改过，此时必须
    409 而不是覆写——不传就等于放弃这道锁（服务层 `save_file_content` 会
    整段跳过 mtime 校验），所以只要调用方拿得到 mtime 就必须带上。
    """
    user = request.user
    kind, owner_id = _resolve_target(payload.contract_id, payload.case_id)
    svc = _get_apply_service()
    result: dict[str, Any] = await sync_to_async(svc.apply, thread_sensitive=True)(
        owner_id=owner_id,
        subpath=payload.subpath,
        selection=payload.selection,
        suggested=payload.suggested,
        user=user,
        org_access=getattr(user, "org_access", None),
        perm_open_access=False,
        expect_mtime=expect_mtime,
        kind=kind,
    )
    # 回传归属 id：MCP 工具结果原样透传到前端，编辑器据「哪份合同/案件的
    # 哪个文件被覆写」定向刷新画布（入参 id 本身不在 service 返回里）
    result["contract_id"] = payload.contract_id or 0
    result["case_id"] = payload.case_id or 0
    return result


# ───────────────────────── 审查任务的划词直改 ─────────────────────────


@router.post("/task/apply", response=TaskEditApplyOut)
@rate_limit_from_settings("TASK", by_user=True)
async def apply_task_edit(request: HttpRequest, payload: TaskEditApplyIn) -> dict[str, Any]:
    """在**审查任务的产物**上落一处修订痕迹。

    为什么需要这个平行端点（而不是复用 `/apply`）：
    `/apply` 的入参是 `contract_id`/`case_id` + `subpath`，它靠绑定文件夹反查
    文件并做文件夹 ACL。审查任务的 docx 在 `MEDIA_ROOT/contract_review/output/`，
    不在任何绑定文件夹里，没有 subpath、也没有文件夹可反查；它的归属判定
    是任务本身（`ReviewTask.user`）。

    修订逻辑与 `/apply` 共用同一套（`DocxRevisionTool` + `locate_paragraph`），
    两条路只在「文件从哪来、写回哪去」上不同。
    """
    user = getattr(request, "user", None) or getattr(request, "auth", None)
    from apps.contract_review.services.review.review_task_edit_service import apply_to_task

    result: dict[str, Any] = await sync_to_async(apply_to_task, thread_sensitive=True)(
        task_id=payload.task_id,
        selection=payload.selection,
        suggested=payload.suggested,
        user=user,
    )
    return result


# ───────────────────────── 多栏并答的 patch 草案区 ─────────────────────────
#
# 三个写类端点里，只有这里两个是「多栏并答」用的：
# - `/patch/propose` 只登记候选改写（不碰磁盘），多栏各提各的；
# - `/patch/apply` 由律师裁决后调用，一次性写盘（服务层还会二次校验 mtime）。
#
# 请求/响应模型刻意**留在本文件**而不是 `schemas/direct_edit_schemas.py`：这套
# 结构只服务这两个端点，字段口径直接来自冻结契约 `write_contracts.WritePatch`，
# 与划词直改的三个 Schema（无状态一问一答）没有共用形状，拆到共用模块反而
# 让「谁能改这两个字段」多一处入口。


class WritePatchProposeIn(Schema):
    """登记一条候选改写（**不落盘**）。"""

    contract_id: int | None = None
    case_id: int | None = None
    subpath: str
    """绑定根下的相对路径，如 `3-办案/专项合同.docx`"""
    original: str
    """要替换的逐字原文（定位锚点，不许做任何归一化）"""
    replacement: str
    """改写后的完整文本"""
    session_id: str = ""
    """产出它的会话标识（MCP 侧从 X-Fachuan-Session 取）"""
    turn: int = 0
    """同一轮多栏共用的轮次号；0 = 调用方没给"""
    agent_kind: str = ""
    """产出后端（pi / dsh / openai-agents）；B1 阶段 MCP 侧拿不到，留空"""
    run_id: str = ""
    """同一轮里区分栏的运行 id；B1 阶段 MCP 侧拿不到，留空"""


class WritePatchOut(Schema):
    """一条候选改写的回执（字段与 `WritePatch` 契约同口径）。"""

    patch_id: str
    owner_kind: str
    owner_id: int
    subpath: str
    original: str
    replacement: str
    base_mtime: float | None = None
    status: str
    session_id: str = ""
    turn: int = 0


class WritePatchApplyIn(Schema):
    """应用选中的候选改写（一次性写盘，仍走 HIGH 审批闸门）。"""

    patch_ids: list[str]
    """律师勾选的 patch；必须同属一份文件"""
    note: str = ""
    """应用备注（留痕）"""


class WritePatchApplyOut(Schema):
    applied: list[str]
    """真正写进文档的 patch"""
    merged: list[str]
    """内容与别人完全相同的重复提案（合并成一次写盘）"""
    subpath: str
    name: str = ""


@router.post("/patch/propose", response=WritePatchOut)
@rate_limit_from_settings("TASK", by_user=True)
async def propose_write_patch_endpoint(request: HttpRequest, payload: WritePatchProposeIn) -> dict[str, Any]:
    """登记一条候选改写（**不碰文件**）。

    多栏并答时写类工具（`rewrite_folder_file` 等）被摘出工具面，模型改用
    `propose_write_patch` 出草案；三栏的草案在 `apply` 时统一做冲突检测。
    """
    from apps.contract_review.services.patch.service import collect_patch
    from apps.contract_review.services.review.direct_edit_service import _browse, read_file_mtime

    user = request.user
    kind, owner_id = _resolve_target(payload.contract_id, payload.case_id)
    # 基准 mtime 是乐观锁的锚：提案时刻的磁盘值，应用前会再比一次
    base_mtime = await sync_to_async(read_file_mtime, thread_sensitive=True)(
        _browse(kind),
        owner_id=owner_id,
        subpath=payload.subpath,
        user=user,
        org_access=getattr(user, "org_access", None),
        perm_open_access=False,
    )
    patch = await sync_to_async(collect_patch, thread_sensitive=True)(
        owner_kind=kind,
        owner_id=owner_id,
        subpath=payload.subpath,
        original=payload.original,
        replacement=payload.replacement,
        base_mtime=base_mtime,
        session_id=payload.session_id,
        turn=payload.turn,
        agent_kind=payload.agent_kind,
        run_id=payload.run_id,
    )
    return {
        "patch_id": patch.patch_id,
        "owner_kind": patch.owner_kind,
        "owner_id": patch.owner_id,
        "subpath": patch.subpath,
        "original": patch.original,
        "replacement": patch.replacement,
        "base_mtime": patch.base_mtime,
        "status": patch.status,
        "session_id": patch.session_id,
        "turn": patch.turn,
    }


@router.post("/patch/apply", response=WritePatchApplyOut)
@rate_limit_from_settings("TASK", by_user=True)
async def apply_write_patches_endpoint(request: HttpRequest, payload: WritePatchApplyIn) -> dict[str, Any]:
    """把选中的候选改写**一次性**写进文件（Word 修订痕迹）。

    互斥冲突（同一段原文两种改法）返回 409 且一个字都不写；文件在提案后被改过
    （mtime 不符）同样 409。审批不在这里做——它由工具名在网关侧判 HIGH 后弹卡，
    本端点不提供任何绕过开关。
    """
    from apps.contract_review.services.patch.service import apply_patches

    user = request.user
    return await sync_to_async(apply_patches, thread_sensitive=True)(
        patch_ids=payload.patch_ids,
        note=payload.note,
        user=user,
        org_access=getattr(user, "org_access", None),
        perm_open_access=False,
    )
