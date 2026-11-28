"""Agent app 请求/响应契约（Ninja Schema）。

按子域分文件，统一从本包导出。SSE 流事件契约另见 ``apps.agent.sse_types``
（pydantic codegen 单一来源，生成前端 TS 类型）。
"""

from __future__ import annotations

from .agent_backend_schemas import BackendOptionOut
from .approval_schemas import ApprovalDecideIn, PiApprovalIn, PiApprovalOut
from .attachment_schemas import AttachmentOut, AttachmentPageOut, AttachmentPagesOut, FolderRefIn
from .chat_schemas import ClearQueueOut, SteerIn, SteerOut
from .memory_schemas import (
    MemoryConfirmIn,
    MemoryCreateIn,
    MemoryHitOut,
    MemoryOut,
    NoteConfirmIn,
    ProjectNoteIn,
    PromoteCandidateOut,
    PromoteIn,
    SnapshotOut,
)
from .question_schemas import QuestionAnswerIn, QuestionAnswerItem
from .session_schemas import (
    AgentSpecIn,
    CompactOut,
    MessageIn,
    MessageOut,
    SessionIn,
    SessionOut,
    SessionRenameIn,
    SessionStatsOut,
)
from .skill_schemas import (
    SkillContentOut,
    SkillCreateIn,
    SkillDetailOut,
    SkillDiffHunk,
    SkillDiffOut,
    SkillFieldError,
    SkillListOut,
    SkillOut,
    SkillQuotaOut,
    SkillReviewIn,
    SkillTrialIn,
    SkillTrialOut,
    SkillTrialQuotaOut,
    SkillToolError,
    SkillSafetyFinding,
    SkillScopeCounts,
    SkillShadowRef,
    SkillSubmitIn,
    SkillToggleIn,
    SkillToggleOut,
    SkillUpdateIn,
    SkillValidateIn,
    SkillValidateOut,
)
from .task_schemas import TaskIn, TaskOut
from .ui_schemas import UiActionResultIn, UiSnapshotIn
from .usage_schemas import UsageOut

__all__ = [
    "AgentSpecIn",
    "ApprovalDecideIn",
    "BackendOptionOut",
    "AttachmentOut",
    "AttachmentPageOut",
    "AttachmentPagesOut",
    "ClearQueueOut",
    "CompactOut",
    "FolderRefIn",
    "MemoryConfirmIn",
    "MemoryCreateIn",
    "MemoryHitOut",
    "MemoryOut",
    "MessageIn",
    "MessageOut",
    "PiApprovalIn",
    "PiApprovalOut",
    "PromoteCandidateOut",
    "PromoteIn",
    "QuestionAnswerIn",
    "QuestionAnswerItem",
    "SessionIn",
    "SessionOut",
    "SessionRenameIn",
    "SessionStatsOut",
    "SkillContentOut",
    "SkillCreateIn",
    "SkillDetailOut",
    "SkillDiffHunk",
    "SkillDiffOut",
    "SkillFieldError",
    "SkillListOut",
    "SkillOut",
    "SkillQuotaOut",
    "SkillReviewIn",
    "SkillTrialIn",
    "SkillTrialOut",
    "SkillTrialQuotaOut",
    "SkillToolError",
    "SkillSafetyFinding",
    "SkillScopeCounts",
    "SkillShadowRef",
    "SkillSubmitIn",
    "SkillToggleIn",
    "SkillToggleOut",
    "SkillUpdateIn",
    "SkillValidateIn",
    "SkillValidateOut",
    "SnapshotOut",
    "SteerIn",
    "SteerOut",
    "TaskIn",
    "TaskOut",
    "UiActionResultIn",
    "UiSnapshotIn",
    "UsageOut",
]
