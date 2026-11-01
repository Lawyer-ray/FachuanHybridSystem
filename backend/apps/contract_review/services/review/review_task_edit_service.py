"""审查任务的划词直改。

## 与 `direct_edit_service` 的区别（只差「文件从哪来」）

`direct_edit_service` 面向**绑定文件夹里的文件**：靠 `contract_id`/`case_id`
反查 ACL，读写都走 `browse`。审查任务不是这样 —— 它的 docx 在
`MEDIA_ROOT/contract_review/output/`，不属于任何绑定文件夹，没有 subpath，
也没有文件夹 ACL 可言。它的归属判定是**任务本身**：`ReviewTask.user` 是唯一
有权改这份文件的人。

所以这里只做一件事：把「取文件 / 存文件」换成任务口径，
**修订痕迹的写入逻辑（`DocxRevisionTool` + `locate_paragraph`）原样复用**。
两处各写一份 OOXML 修订逻辑是最容易产生行为漂移的地方，必须共用。

## 为什么覆写 output_file 而不是存新版本

律师的预期是「我在编辑器里改，文档就变了」。DS 的画布靠 `content_version`
（= `output_file` 的 mtime）决定要不要重建；覆写同一路径并 bump mtime，
画布刷新后就能看到红删绿增。另存新文件会让版本链多出一条噪音节点，
而这次改动本质上是「当前这一版的编辑」，不是新版本。
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from docx import Document

from apps.contract_review.models import ReviewTask

from .direct_edit_service import locate_paragraph

logger = logging.getLogger(__name__)

DEFAULT_AUTHOR = "法穿SI"


class ReviewTaskEditError(Exception):
    """审查任务直改的业务错误（文件缺失 / 无产出 / 定位失败由返回值表达）"""


def _task_output_path(task: ReviewTask) -> Path:
    """任务产物的绝对路径。没有产物时回落到上传原件。"""
    rel = task.output_file or task.original_file
    if not rel:
        raise ReviewTaskEditError("该任务还没有可编辑的文件")
    path = Path(settings.MEDIA_ROOT) / rel
    if not path.exists():
        raise ReviewTaskEditError("文件不存在，可能已被清理")
    if path.suffix.lower() != ".docx":
        raise ReviewTaskEditError("只有 .docx 支持带修订痕迹的直改")
    return path


def apply_to_task(
    *,
    task_id: str,
    selection: str,
    suggested: str,
    user: Any | None = None,
    author: str = DEFAULT_AUTHOR,
) -> dict[str, Any]:
    """把 `selection → suggested` 写成修订痕迹，覆写任务产物。

    返回 `{"applied": bool, "name": str, "reason": str}`。定位失败返回
    `applied=False` 而不是抛错 —— 「选区已被前一次改动破坏」是律师正常操作结果。
    """
    from apps.core.exceptions import ForbiddenError, ValidationException

    if not (selection or "").strip():
        raise ValidationException(message="选区为空", errors={"selection": ""})
    if not (suggested or "").strip():
        raise ValidationException(message="改写结果为空", errors={"suggested": ""})

    task = ReviewTask.objects.filter(id=task_id).first()
    if task is None:
        raise ValidationException(message="审查任务不存在", errors={"task_id": task_id})

    # 归属：只有任务创建者（或管理员）能改这份文件
    if user is not None and task.user_id and task.user_id != getattr(user, "id", None):
        if not getattr(user, "is_superuser", False):
            raise ForbiddenError("无权修改该审查任务的文档")

    path = _task_output_path(task)

    from apps.contract_review.services.formatting.docx_revision_tool import DocxRevisionTool, enable_track_changes

    doc = Document(str(path))
    para = locate_paragraph(doc, selection)
    if para is None:
        logger.info("审查任务直改：未定位到选区 task=%s", task_id)
        return {
            "applied": False,
            "name": path.name,
            "reason": "文档中已找不到这段原文（可能已被改动），请重新框选",
        }

    # 强制打开修订模式，否则 <w:del>/<w:ins> 在 Word 里会被当成已接受的普通文本
    enable_track_changes(doc)

    tool = DocxRevisionTool()
    ok = tool.apply_revision(para, selection, suggested, author=author)
    if not ok:
        logger.warning("审查任务直改：落笔失败 task=%s selection=%s", task_id, selection[:60])
        return {
            "applied": False,
            "name": path.name,
            "reason": "无法在原文里精确落笔（选区可能跨段或含特殊格式），请缩小选区后重试",
        }

    buf = BytesIO()
    doc.save(buf)
    path.write_bytes(buf.getvalue())

    # 触摸 mtime：前端拿 content_version（mtime）判断要不要重建画布，
    # 不 bump 的话律师采纳后画布不会刷新，看着像没生效
    revised = timezone.now()
    ReviewTask.objects.filter(id=task.id).update(updated_at=revised)

    logger.info(
        "审查任务直改已落盘: task=%s 长度 %d→%d",
        task_id,
        len(selection),
        len(suggested),
    )
    return {"applied": True, "name": path.name, "reason": ""}


__all__ = ["ReviewTaskEditError", "apply_to_task"]
