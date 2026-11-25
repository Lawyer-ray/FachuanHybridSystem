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


class VerifyRunOut(Schema):
    """一次核对（详情与待裁决清单共用）。"""

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
