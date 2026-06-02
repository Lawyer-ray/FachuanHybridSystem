from __future__ import annotations

from uuid import UUID

from ninja import Schema


class FormatNormalizeIn(Schema):
    """格式规范化输入"""

    task_id: UUID  # 关联的审查任务 ID
    reference_file: str | None = None  # 参考文档路径（可选）


class FormatNormalizeOut(Schema):
    """格式规范化输出"""

    task_id: UUID
    status: str  # success / failed
    output_file: str | None = None
    message: str = ""
