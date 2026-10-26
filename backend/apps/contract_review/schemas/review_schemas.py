from __future__ import annotations

from typing import Literal
from uuid import UUID

from ninja import Schema


class ConfirmPartyIn(Schema):
    represented_party: Literal["party_a", "party_b", "party_c", "party_d"]
    reviewer_name: str = ""
    selected_steps: list[str] = []
    party_a: str = ""
    party_b: str = ""
    party_c: str = ""
    party_d: str = ""
    # 客户特别交代（律师在发起审查抽屉里写的诉求）
    client_note: str = ""
    client_demands: list[str] = []
    # 我方单位全名：立场方向的语义锚点（party_a 只是位置，不代表「我方」）
    our_client_name: str = ""
    stance_basis: str = ""


class TaskCreatedOut(Schema):
    task_id: UUID
    status: str
    contract_title: str | None = None
    parties: dict[str, str] = {}


class TaskStatusOut(Schema):
    task_id: UUID
    status: str
    current_step: str | None = None
    error_message: str | None = None
    output_filename: str | None = None


class RevisionOut(Schema):
    """单条审查修订（复审台左栏的判定单元）。"""

    id: UUID
    ordinal: int
    kind: str
    severity: str
    title: str
    original: str
    suggested: str
    reason: str
    paragraph_index: int
    status: str
    reject_reason: str
    decided_at: str | None = None


class RevisionListOut(Schema):
    """修订清单 + 计数。计数由后端算：前端自己数容易与列表不一致。"""

    task_id: UUID
    total: int
    pending: int
    accepted: int
    rejected: int
    items: list[RevisionOut]


class ResolveRevisionIn(Schema):
    """律师对单条建议的决策。

    accept：标记已采纳，文档侧由编辑器以修订模式写入痕迹（前端驱动）；
    reject：标记已驳回，不动文档，理由可留空；
    reset：撤销决策回到待决策，清掉理由与决策时间。
    """

    action: Literal["accept", "reject", "reset"]
    reason: str = ""


class ResolveRevisionOut(Schema):
    """决策结果 + 该任务剩余待决策数（前端据此更新进度不再发第二次请求）。"""

    revision_id: UUID
    status: str
    pending: int


class ContentVersionOut(Schema):
    """文档内容版本：画布到底该不该重载。

    `content_version` 直接给 OfficeView 当 `version` 用：内容没变则值不变
    （DS 缓存命中、不重建），保存回写后才变（换 key 重新取文件）。
    """

    content_version: str
    saved_version: int
    output_file: str


class DocumentVersionOut(Schema):
    """版本链上的一个节点。"""

    id: str
    version_no: int
    kind: str
    kind_label: str
    file_name: str
    file_path: str
    author: str
    note: str
    parent_id: str | None = None
    created_at: str | None = None


class VersionChainOut(Schema):
    task_id: UUID
    total: int
    items: list[DocumentVersionOut]
