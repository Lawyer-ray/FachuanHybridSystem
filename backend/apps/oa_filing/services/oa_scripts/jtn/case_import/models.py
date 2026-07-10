"""金诚同达 OA 案件导入 - 数据结构。"""

from __future__ import annotations

from dataclasses import dataclass

# re-export 通用数据类
from apps.oa_filing.services.oa_data_models import OACaseCustomerData, OACaseData, OACaseInfoData, OAConflictData


@dataclass
class CaseSearchItem:
    """案件搜索结果项。"""

    case_no: str
    keyid: str


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
