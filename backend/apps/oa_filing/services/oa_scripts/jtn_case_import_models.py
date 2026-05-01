"""金诚同达 OA 案件导入 - 数据结构."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OACaseCustomerData:
    """OA客户数据（案件中提取）。"""

    name: str  # 客户名称
    customer_type: str  # natural=自然人 / legal=企业
    address: str | None = None  # 地址
    phone: str | None = None  # 联系电话
    id_number: str | None = None  # 身份证号码（自然人）
    industry: str | None = None  # 行业（企业）
    legal_representative: str | None = None  # 法定代表人（企业）


@dataclass
class OACaseInfoData:
    """OA案件信息数据。"""

    case_no: str  # 案件编号
    case_name: str | None = None  # 案件名称
    case_stage: str | None = None  # 案件阶段（一审/二审/执行）
    acceptance_date: str | None = None  # 收案日期
    case_category: str | None = None  # 案件类别/案件类型（合同类型映射主字段）
    case_type: str | None = None  # 业务种类（兼容字段）
    responsible_lawyer: str | None = None  # 案件负责人
    description: str | None = None  # 案情简介
    client_side: str | None = None  # 代理何方


@dataclass
class OAConflictData:
    """OA利益冲突数据。"""

    name: str  # 冲突方名称
    conflict_type: str | None = None  # 冲突类型


@dataclass
class OACaseData:
    """OA案件完整数据。"""

    case_no: str  # 案件编号（OA案件编号）
    keyid: str  # OA系统KeyID
    customers: list[OACaseCustomerData] = field(default_factory=list)  # 客户列表
    case_info: OACaseInfoData | None = None  # 案件信息
    conflicts: list[OAConflictData] = field(default_factory=list)  # 利益冲突列表


@dataclass
class CaseSearchItem:
    """案件搜索结果项。"""

    case_no: str  # 案件编号
    keyid: str  # 详情页KeyID


@dataclass
class OAListCaseCandidate:
    """OA 列表页候选案件。"""

    case_no: str
    case_name: str
    keyid: str
    detail_url: str


@dataclass
class CaseListFormState:
    """案件列表表单状态。"""

    action_url: str
    payload: dict[str, str]
