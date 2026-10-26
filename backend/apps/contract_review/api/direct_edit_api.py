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
from ninja import Router

from apps.contract_review.schemas.direct_edit_schemas import (
    DirectEditApplyIn,
    DirectEditApplyOut,
    DirectEditSuggestIn,
    DirectEditSuggestOut,
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


def _load_paragraph_context(contract_id: int, subpath: str, selection: str, user: Any) -> tuple[str, str]:
    """取选区所在段落，切出前后文给模型。

    失败一律返回空上下文：上下文是「让改写更贴合语境」的加分项，
    取不到（文件被移走、权限刚好变了、docx 解析失败）不该让整次改写失败。
    """
    from io import BytesIO

    from docx import Document

    from apps.contract_review.services.review.direct_edit_service import locate_paragraph
    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    try:
        browse = ContractFolderBrowseService()
        path = browse.resolve_file(
            owner_id=contract_id,
            subpath=subpath,
            user=user,
            org_access=getattr(user, "org_access", None),
            perm_open_access=False,
        )
        doc = Document(BytesIO(path.read_bytes()))
        para = locate_paragraph(doc, selection)
        if para is None:
            return "", ""
        from apps.contract_review.services.review.direct_editor import compute_context

        return compute_context(para.text, selection)
    except Exception:
        logger.warning(
            "划词直改：取上下文失败（不影响改写）contract=%s subpath=%s", contract_id, subpath, exc_info=True
        )
        return "", ""


@router.post("/suggest", response=DirectEditSuggestOut)
@rate_limit_from_settings("TASK", by_user=True)
async def suggest_edit(request: HttpRequest, payload: DirectEditSuggestIn) -> dict[str, Any]:
    """按律师的要求，为框选的这一段生成 2~3 条改写候选（不改文件）。"""
    user = request.user
    # 取上下文要先过 ACL（resolve_file 内部校验），所以放在线程池里跑同步 IO
    ctx_before, ctx_after = await sync_to_async(_load_paragraph_context, thread_sensitive=True)(
        payload.contract_id, payload.subpath, payload.selection, user
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
async def apply_edit(request: HttpRequest, payload: DirectEditApplyIn) -> dict[str, Any]:
    """采纳一条候选：写成 Word 修订痕迹（`<w:del>` + `<w:ins>`）并覆写原文件。

    定位失败返回 `applied=false` 而不是报错——「选中的原文已被改过」是律师
    常见操作结果，前端要能提示「重新框选」，而不是弹 500。
    """
    user = request.user
    svc = _get_apply_service()
    result: dict[str, Any] = await sync_to_async(svc.apply, thread_sensitive=True)(
        owner_id=payload.contract_id,
        subpath=payload.subpath,
        selection=payload.selection,
        suggested=payload.suggested,
        user=user,
        org_access=getattr(user, "org_access", None),
        perm_open_access=False,
    )
    return result
