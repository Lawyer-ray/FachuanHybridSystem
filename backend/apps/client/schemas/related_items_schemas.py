"""客户关联案件/合同 Schema。"""

from __future__ import annotations

from ninja import Schema


class RelatedCaseOut(Schema):
    """关联案件输出 Schema"""

    id: int
    name: str
    case_type: str | None = None
    status: str | None = None
    current_stage: str | None = None
    legal_status: str | None = None


class RelatedContractOut(Schema):
    """关联合同输出 Schema"""

    id: int
    name: str
    case_type: str | None = None
    status: str | None = None
    role: str | None = None


class RelatedItemsOut(Schema):
    """关联案件和合同输出 Schema"""

    cases: list[RelatedCaseOut]
    contracts: list[RelatedContractOut]
