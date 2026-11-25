"""文档工作面：对项目文件夹文件的写入口。

**为什么新开一个前缀**：`/contract-review/direct-edit/*` 是旧的任务式审查链路，
即将随 `apps/contract_review` 一起移除；新链路以「文件夹里的那一份文件」为坐标，
不需要 `task_id`，也不产生第二份产物 docx。挂在旧前缀下会让调用方以为两者等价。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

from ..services import write_service

logger = logging.getLogger(__name__)

router = Router(tags=["文档工作面"], auth=JWTOrSessionAuth())


class DocApplySpanIn(Schema):
    """一段原文 → 一段改写，以修订痕迹写回原文件。"""

    kind: str
    """`contract` | `case`（对应合同/案件的绑定文件夹）。"""

    owner_id: int
    subpath: str
    selection: str
    """要替换的原文片段（定位锚点，必须与文档现行文本一致）。"""

    suggested: str
    base_mtime: float | None = None
    """打开时文件的 mtime。**AI 路径也必须传**，否则等于放弃乐观锁。"""


class DocApplySpanOut(Schema):
    applied: bool
    mode: str = "disk"
    reason: str = ""
    candidates: int = 0
    how: str = ""
    author: str = ""
    rev_ids: list[int] = []
    file_url: str = ""
    mirror_to_canvas: bool = False


class DocPatchIn(Schema):
    selection: str
    suggested: str


class DocApplyBatchIn(Schema):
    kind: str
    owner_id: int
    subpath: str
    patches: list[DocPatchIn]
    base_mtime: float | None = None


class DocCommentIn(Schema):
    selection: str
    text: str


class DocApplyCommentsIn(Schema):
    kind: str
    owner_id: int
    subpath: str
    comments: list[DocCommentIn]
    base_mtime: float | None = None


class DocWriteResultOut(Schema):
    """一条写路径的统一回执。

    `applied=false` 且 `mode=canvas` 表示「已下发画布、未落盘」（前端编排流程）；
    `applied=false` 且 `reason` 非空才是真的失败。
    """

    applied: bool
    mode: str = "disk"
    reason: str = ""
    failed_index: int | None = None
    count: int = 0
    rev_ids: list[int] = []
    comment_ids: list[int] = []
    failures: list[dict[str, Any]] = []
    author: str = ""
    file_url: str = ""
    mirror_to_canvas: bool = False
    patches: list[dict[str, str]] = []
    wrote_disk: bool = True


class DocPresenceIn(Schema):
    kind: str
    owner_id: int
    subpath: str
    open: bool = True


@router.post("/apply-batch", response=DocWriteResultOut, summary="一次落多条修订（全或无）")
async def apply_batch(request: HttpRequest, payload: DocApplyBatchIn) -> Any:
    """十条修订里有一条定位不到，就**一个字都不写**。

    半改过的文件既不是原稿也不是审完稿，律师无法判断哪几条生效了。
    """
    user = getattr(request, "auth", None)
    result = await sync_to_async(write_service.apply_batch, thread_sensitive=True)(
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath=payload.subpath,
        patches=[p.model_dump() for p in payload.patches],
        base_mtime=payload.base_mtime,
        user=user,
        org_access=getattr(user, "org_access", None),
    )
    return DocWriteResultOut(**result)


@router.post("/comments", response=DocWriteResultOut, summary="给若干段挂 Word 原生批注（不改正文）")
async def apply_comments(request: HttpRequest, payload: DocApplyCommentsIn) -> Any:
    """批注不做全或无：部分成功仍是一份完整可用的文档。"""
    user = getattr(request, "auth", None)
    result = await sync_to_async(write_service.apply_comments, thread_sensitive=True)(
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath=payload.subpath,
        comments=[c.model_dump() for c in payload.comments],
        base_mtime=payload.base_mtime,
        user=user,
        org_access=getattr(user, "org_access", None),
    )
    return DocWriteResultOut(**result)


@router.post("/canvas-presence", summary="登记/注销「这份文件的画布开着」")
async def canvas_presence(request: HttpRequest, payload: DocPresenceIn) -> dict[str, Any]:
    """前端在 `OfficeView` 就绪时登记，每 30 秒心跳续期，卸载时注销。

    后端用它决定「写完盘要不要同时下发画布重放」，**不用它决定写不写盘**
    （写盘永远做，否则重放失败就等于内容丢了）。
    """
    from ..services import presence

    user = getattr(request, "auth", None)
    if payload.open:
        presence.mark_open(
            kind=payload.kind,
            owner_id=payload.owner_id,
            subpath=payload.subpath,
            user_id=getattr(user, "pk", None),
        )
    else:
        presence.mark_closed(kind=payload.kind, owner_id=payload.owner_id, subpath=payload.subpath)
    return {"ok": True, "open": payload.open, "ttl_seconds": presence.PRESENCE_TTL_SECONDS}


@router.post("/apply", response=DocApplySpanOut, summary="把一段原文改写为 Word 修订痕迹写回原文件")
async def apply_span(request: HttpRequest, payload: DocApplySpanIn) -> Any:
    """落笔一条修订。

    失败（找不到原文 / 原文不唯一 / 含有不可切分元素）时返回 `applied=false` +
    可读 `reason`，**不抛 500**：模型要能据 reason 自纠（把选区加长或换写法），
    抛异常只会让它当整次调用失败。

    真正的并发冲突（mtime 变了）走 `ConflictError` → 全局处理器映射成 **409**：
    这不是「模型做错了」，而是「文件被别人改过」，必须让调用方重新读一遍再决定。
    """
    user = getattr(request, "auth", None)
    result = await sync_to_async(write_service.apply_span, thread_sensitive=True)(
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath=payload.subpath,
        selection=payload.selection,
        suggested=payload.suggested,
        base_mtime=payload.base_mtime,
        user=user,
        org_access=getattr(user, "org_access", None),
    )
    return DocApplySpanOut(**result)


class DocRevisionOut(Schema):
    paragraph_index: int
    author: str
    original: str
    suggested: str
    rev_ids: list[int] = []


class DocRevisionListOut(Schema):
    items: list[DocRevisionOut] = []


class DocCreateFileIn(Schema):
    kind: str
    owner_id: int
    subpath_dir: str = ""
    """目标目录（绑定根下的相对路径，posix）；空串 = 根目录"""
    name: str
    paragraphs: list[str] = []
    markdown: str = ""


class DocCreateFileOut(Schema):
    created: bool
    name: str = ""
    subpath: str = ""
    file_url: str = ""


@router.get("/revisions", response=DocRevisionListOut, summary="文件里已有的修订（AI 避免重复提同一件事）")
def list_revisions(request: HttpRequest, kind: str, owner_id: int, subpath: str) -> Any:
    user = getattr(request, "auth", None)
    items = write_service.read_revisions(
        kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=getattr(user, "org_access", None)
    )
    return DocRevisionListOut(items=[DocRevisionOut(**item) for item in items])


@router.post("/files", response=DocCreateFileOut, summary="在文件夹里新建 docx（同名不覆盖）")
def create_file(request: HttpRequest, payload: DocCreateFileIn) -> Any:
    """新建文件。同名会自动加序号（`_unique_destination`），**绝不覆盖**已有文件。"""
    user = getattr(request, "auth", None)
    result = write_service.create_file(
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath_dir=payload.subpath_dir,
        name=payload.name,
        paragraphs=payload.paragraphs or None,
        markdown=payload.markdown,
        user=user,
        org_access=getattr(user, "org_access", None),
    )
    return DocCreateFileOut(**result)


class DocDraftIn(Schema):
    kind: str
    owner_id: int
    subpath_dir: str = ""
    name: str
    template_id: int
    """`documents.DocumentTemplate` 主键；起草必须从**律所已验证的模板**开始"""
    facts: dict[str, str] = {}
    auto_review: bool = True
    stance: str = "neutral"
    contract_type: str = ""


class DocDraftOut(Schema):
    created: bool
    name: str = ""
    subpath: str = ""
    file_url: str = ""
    filled: dict[str, str] = {}
    pending: list[str] = []
    slot_fill_rate: float = 0.0
    review_run_id: int | None = None
    reason: str = ""


@router.post("/draft", response=DocDraftOut, summary="按模板起草一份文书并落进项目文件夹")
def draft_document(request: HttpRequest, payload: DocDraftIn) -> Any:
    """模板 + 事实 → 成稿 → 落盘 → （可选）自动排一轮审查。

    **不做整篇自由生成**：模板是律所已验证的资产，模型只能填槽，不能改结构
    （`draft_service._assert_skeleton_intact` 会炸）。
    """
    from pathlib import Path

    from ..services import draft_service, queries

    user = getattr(request, "auth", None)
    template, location = queries.document_template_file(payload.template_id)
    if template is None:
        return DocDraftOut(created=False, reason="模板不存在")
    if not location:
        return DocDraftOut(created=False, reason="模板文件缺失或路径不可用")

    result = draft_service.draft_contract(
        template_bytes=Path(location).read_bytes(),
        name=payload.name,
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath_dir=payload.subpath_dir,
        facts=payload.facts,
        user=user,
        org_access=getattr(user, "org_access", None),
        auto_review=payload.auto_review,
        stance=payload.stance,
        contract_type=payload.contract_type,
    )
    return DocDraftOut(**result.__dict__)
