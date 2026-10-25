"""文档版本链的写入与查询。

**链路语义**：每产生一个新文件就挂一个节点，`parent` 指向它改自的那一版。
版本序号 `version_no` 在任务内单调递增（有唯一约束），由服务层算，
不让调用方各自拍脑袋——两条路径（流水线跑完、编辑器保存）都会追加节点，
谁后到谁拿大号。

**为什么保存要挂父节点而不是永远接在链尾**：编辑器保存可能来自不同会话
（两个律师同时改同一份），都从 AI 版出发。全接在链尾会让「谁改自谁」失真；
接 parent 才是真实结构。这里统一接到**当前最新版**上——DS 是多用户协同
同一份文档（同 key），实际只有一个内容分支，这个近似与产品行为一致。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Max

from apps.contract_review.models.document_version import DocumentVersion, VersionKind

logger = logging.getLogger(__name__)


def _next_version_no(task_id: UUID) -> int:
    agg = DocumentVersion.objects.filter(task_id=task_id).aggregate(m=Max("version_no"))
    return int(agg["m"] or 0) + 1


def _latest(task_id: UUID) -> DocumentVersion | None:
    return DocumentVersion.objects.filter(task_id=task_id).order_by("-version_no").first()


@transaction.atomic
def record_version(
    *,
    task_id: UUID,
    kind: str,
    file_path: str,
    file_name: str = "",
    author: str = "",
    note: str = "",
) -> DocumentVersion:
    """追加一个版本节点（接到当前最新版之后）。

    并发安全：`version_no` 有唯一约束，两个请求同时算到同一个号时
    后者会 IntegrityError；外层调用方（保存回写 / 流水线）都会重试，
    这里不自己吞异常——静默改号会让链错乱。
    """
    parent = _latest(task_id)
    v = DocumentVersion.objects.create(
        task_id=task_id,
        parent=parent,
        kind=kind,
        version_no=_next_version_no(task_id),
        file_path=file_path or "",
        file_name=file_name or "",
        author=author or "",
        note=note or "",
    )
    logger.info("版本链追加: task=%s V%d (%s) %s", task_id, v.version_no, kind, file_name or file_path)
    return v


def ensure_original_version(*, task_id: UUID, file_path: str, file_name: str = "") -> DocumentVersion | None:
    """保证链头存在（客户来稿）。已存在则不动，避免重跑流水线重复建链头。"""
    head = DocumentVersion.objects.filter(task_id=task_id, kind=VersionKind.ORIGINAL).first()
    if head is not None:
        return head
    return record_version(
        task_id=task_id,
        kind=VersionKind.ORIGINAL,
        file_path=file_path,
        file_name=file_name,
        author="客户",
        note="客户来稿",
    )


def list_versions(task_id: UUID) -> list[dict[str, Any]]:
    """按序号返回整条链（前端版本链面板消费）。"""
    rows = DocumentVersion.objects.filter(task_id=task_id).order_by("version_no")
    return [
        {
            "id": str(v.id),
            "version_no": v.version_no,
            "kind": v.kind,
            "kind_label": v.get_kind_display(),
            "file_name": v.file_name or "",
            "file_path": v.file_path or "",
            "author": v.author or "",
            "note": v.note or "",
            "parent_id": str(v.parent_id) if v.parent_id else None,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in rows
    ]
