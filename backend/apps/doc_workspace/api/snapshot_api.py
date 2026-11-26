"""版本快照的读取与回滚。

只暴露「看时间线」和「回到某一版」两件事——快照本身不可改不可删，
要「撤销回滚」就再回滚到 `previous_seq`（回滚前的内容已经被自动存了一版）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

from ..services import snapshot_service

logger = logging.getLogger(__name__)

router = Router(tags=["文档工作面"], auth=JWTOrSessionAuth())


class DocSnapshotOut(Schema):
    seq: int
    sha256: str
    size: int
    reason: str
    actor_kind: str
    actor_id: int | None = None
    created_at: datetime


class DocSnapshotListOut(Schema):
    items: list[DocSnapshotOut] = []


class DocRestoreIn(Schema):
    kind: str
    owner_id: int
    subpath: str
    seq: int


class DocRestoreOut(Schema):
    restored: bool
    reason: str = ""
    seq: int = 0
    sha256: str = ""
    previous_seq: int = 0
    """回滚前那一刻内容的快照号——想撤销这次回滚就再回滚到它。"""


def _to_out(snap: Any) -> DocSnapshotOut:
    return DocSnapshotOut(
        seq=snap.seq,
        sha256=snap.sha256,
        size=snap.size,
        reason=snap.reason,
        actor_kind=snap.actor_kind,
        actor_id=snap.actor_id,
        created_at=snap.created_at,
    )


@router.get("/snapshots", response=DocSnapshotListOut, summary="该文件的版本时间线（新→旧）")
async def list_snapshots(request: HttpRequest, kind: str, owner_id: int, subpath: str, limit: int = 50) -> Any:
    """**只列不取正文**：列表用在右栏时间线里，正文走单独端点按需拉。"""
    user = getattr(request, "auth", None)
    if user is None:
        return DocSnapshotListOut(items=[])
    items = await sync_to_async(snapshot_service.list_snapshots, thread_sensitive=True)(
        kind=kind, owner_id=owner_id, subpath=subpath, limit=max(1, min(limit, 200))
    )
    return DocSnapshotListOut(items=[_to_out(s) for s in items])


@router.post("/snapshots/restore", response=DocRestoreOut, summary="回滚到某一版（回滚本身可回滚）")
async def restore_snapshot(request: HttpRequest, payload: DocRestoreIn) -> Any:
    user = getattr(request, "auth", None)
    if user is None:
        return DocRestoreOut(restored=False, reason="未登录")
    result = await sync_to_async(snapshot_service.restore, thread_sensitive=True)(
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath=payload.subpath,
        seq=payload.seq,
        user=user,
        org_access=getattr(user, "org_access", None),
    )
    return DocRestoreOut(**result)


class DocCompareOut(Schema):
    found: bool
    reason: str = ""
    seq: int = 0
    total_paragraphs: int = 0
    changed_paragraphs: int = 0
    unchanged: bool = True
    changed_indices: list[int] = []
    old_sha256: str = ""


@router.get("/compare", response=DocCompareOut, summary="与历史某一版对照（段落级、确定性）")
def compare_versions(request: HttpRequest, kind: str, owner_id: int, subpath: str, seq: int) -> Any:
    """「跟上一版比，改了什么」——由代码算段落 diff，不经过模型。"""
    from ..services import delta_review

    user = getattr(request, "auth", None)
    result = delta_review.compare_versions(
        kind=kind, owner_id=owner_id, subpath=subpath, seq=seq, user=user, org_access=getattr(user, "org_access", None)
    )
    return DocCompareOut(**result)
