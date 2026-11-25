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
    tier: int = 0


class VerifyRunOut(Schema):
    """一次核对（详情与待裁决清单共用）。"""

    id: int
    artifact_id: int
    case_id: int | None = None
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
