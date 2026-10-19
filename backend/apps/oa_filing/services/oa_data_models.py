"""OA 导入通用数据结构。

供 import services 使用，不依赖任何律所特定模块。
各律所 adapter 产出这些数据结构，services 消费它们。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 案件导入数据 ──────────────────────────────────────────────────


@dataclass
class OACaseCustomerData:
    """OA客户数据（案件中提取）。"""

    name: str
    customer_type: str  # natural / legal
    address: str | None = None
    phone: str | None = None
    id_number: str | None = None
    industry: str | None = None
    legal_representative: str | None = None


@dataclass
class OACaseInfoData:
    """OA案件信息数据。"""

    case_no: str
    case_name: str | None = None
    case_stage: str | None = None
    acceptance_date: str | None = None
    case_category: str | None = None
    case_type: str | None = None
    responsible_lawyer: str | None = None
    description: str | None = None
    client_side: str | None = None
    # 委托合同信息 tab 的收费字段（OA 未填时保持 None）
    fee_mode_text: str | None = None  # 收费方式原文，如「定额收费」
    fee_amount_text: str | None = None  # 合同总额原文，如「5000.00」
    fee_currency: str | None = None  # 币种，如「人民币」
    fee_waived: str | None = None  # 是否免费或减免代理（「是」/「否」）


@dataclass
class OAConflictData:
    """OA利益冲突数据。"""

    name: str
    conflict_type: str | None = None


@dataclass
class OACaseData:
    """OA案件完整数据。"""

    case_no: str
    keyid: str
    customers: list[OACaseCustomerData] = field(default_factory=list)
    case_info: OACaseInfoData | None = None
    conflicts: list[OAConflictData] = field(default_factory=list)


# ── 客户导入数据 ──────────────────────────────────────────────────


@dataclass
class OACustomerData:
    """OA客户数据。"""

    name: str
    client_type: str  # natural / legal
    phone: str | None = None
    address: str | None = None
    id_number: str | None = None
    legal_representative: str | None = None
    gender: str | None = None
