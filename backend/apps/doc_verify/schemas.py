"""doc_verify 的 API 出入参。

`FindingOut` 与 `domain.contracts.Finding.as_dict()` 一一对应：库里存的是那份
dict，前端按 `code` 折叠、按 `severity` 上色，所以这里的字段名不许各写一套。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Schema


class FindingOut(Schema):
    """一条失败项（红线 / 疑似 / 无法核对）。"""

    kind: str
    code: str
    title: str
    severity: str
    detail: str = ""
    expected: str = ""
    actual: str = ""
    page: int | None = None


class VerifyRunIn(Schema):
    """提交一次回传件核对。"""

    artifact_id: int
    #: 回传件字节的 base64。前端 `FileReader.readAsDataURL` 的结果（带 data: 前缀）也收。
    file_base64: str
    file_name: str = ""
    source_message_id: int | None = None
    #: 不传 = 自动（勾了核对 + 扫描件 → 升到 OCR 层）；显式 0 = 只要免费层
    tier: int | None = None


class RunFromMaterialIn(Schema):
    """从收件箱附件直接跑核对：字节由服务端自己取，前端不再整本 base64 上传。"""

    artifact_id: int
    #: 收件箱消息 id（`InboxMessage` 主键，与归案溯源 `source_message_id` 同一口径）
    message_id: int
    #: `attachments_meta[].part_index`，从 0 起
    part_index: int
    #: 不传 = 自动（同 `/runs`：勾了核对 + 扫描件 → 升到 OCR 层）
    tier: int | None = None


class VerifyRunOut(Schema):
    """一次核对（详情、待裁决清单与核对历史共用）。"""

    id: int
    artifact_id: int
    case_id: int | None = None
    #: 案名。跨案件清单必须带上，否则「起诉状」三字无法定位是哪一件
    case_name: str = ""
    doc_type: str
    state: str
    #: 状态的中文标签（`VerifyState` 的 label）。前端直接显示，不要自己翻译状态机。
    state_label: str
    tier: int
    inbound_file_name: str
    inbound_sha256: str
    page_count: int
    findings: list[FindingOut]
    coverage: dict[str, Any]
    source_message_id: int | None = None
    created_at: datetime


class RunPageOut(Schema):
    """某案的全部核对历史（分页）。`total` 是**过滤后的总数**，不是本页条数。"""

    total: int
    items: list[VerifyRunOut]


class DecisionIn(Schema):
    """律师裁决入参。"""

    action: str
    reason: str = ""


class DecisionOut(Schema):
    """一条已留痕的裁决。"""

    id: int
    verification_id: int
    action: str
    reason: str
    decided_by_id: int | None = None
    decided_at: datetime


class DecisionBatchIn(Schema):
    """批量裁决：一次提交多条待裁决的核对运行。"""

    run_ids: list[int]
    action: str
    reason: str = ""


class DecisionBatchOut(Schema):
    """批量裁决结果。

    逐条判：`items` 与入参 `run_ids` 等长，落库的带 `decision_id`，没落的带
    `skipped_reason`——前端据此提示「哪几条为什么没处理」。
    """

    decided: int
    skipped: int
    items: list[dict[str, Any]]


class ArtifactIn(Schema):
    """冻结一份出站基线（我们发出去的那一份）。

    `verify_required` 留空 = 按案件策略决定（高风险四类默认要核）。显式传 True/False
    可以覆盖策略——出站那一刻律师最清楚「这份要不要回签核对」。
    """

    doc_type: str
    file_base64: str
    file_name: str = ""
    version: str = ""
    case_id: int | None = None
    verify_required: bool | None = None
    capture_source: str = "manual"
    note: str = ""


class ArtifactOut(Schema):
    """一份出站基线。"""

    id: int
    case_id: int | None = None
    doc_type: str
    version: str
    file_name: str
    file_sha256: str
    page_count: int
    capture_source: str
    verify_required: bool
    captured_at: datetime


class PolicyItemOut(Schema):
    """一类文书的策略：实际值 + 代码默认值（前端据此标「恢复默认」）。"""

    doc_type: str
    enabled: bool
    default: bool


class PolicyOut(Schema):
    case_id: int
    items: list[PolicyItemOut]


class PolicyIn(Schema):
    """批量改策略；`doc_types` 留空 = 改全部高风险类。"""

    case_id: int
    enabled: bool
    doc_types: list[str] = []
