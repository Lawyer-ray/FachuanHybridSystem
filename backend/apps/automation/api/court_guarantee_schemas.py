"""法院一张网申请担保 API — 常量与 Schema 定义。"""

from __future__ import annotations

import os
from typing import Any

from ninja import Schema


def _read_int_env(name: str, default_value: int) -> int:
    raw_value = str(os.getenv(name, str(default_value))).strip()
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default_value
    return parsed if parsed >= 0 else default_value


_PLAINTIFF_SIDE_STATUSES = {"plaintiff", "applicant", "appellant", "orig_plaintiff"}
_RESPONDENT_SIDE_STATUSES = {"defendant", "respondent", "appellee", "orig_defendant"}
_DEFAULT_INSURANCE_COMPANY = "中国平安财产保险股份有限公司"
_SUNSHINE_INSURANCE_COMPANY = "阳光财产保险股份有限公司"
_SUNSHINE_DEFAULT_CONSULTANT_CODE = "08740007"
_PROPERTY_CLUE_TYPE_DISPLAY = {
    "bank": "银行账户",
    "alipay": "支付宝账户",
    "wechat": "微信账户",
    "real_estate": "不动产",
    "other": "其他",
}
_GUARANTEE_INSURANCE_COMPANY_OPTIONS = [
    "中国平安财产保险股份有限公司",
    "中国人民财产保险股份有限公司",
    "中国太平洋财产保险股份有限公司",
    "中国人寿财产保险股份有限公司",
    "中华联合财产保险股份有限公司",
    "阳光财产保险股份有限公司",
    "大地财产保险股份有限公司",
    "太平财产保险有限公司",
    "永安财产保险股份有限公司",
    "安盛天平财产保险有限公司",
]
_DEFAULT_PRESERVATION_CORP_ID = "2550"
_DEFAULT_PRESERVATION_CATEGORY_ID = "127000"
_QUOTE_RETRY_ALLOWED_STATUSES = {"failed", "partial_success"}
_BROWSER_SLOW_MO_MS = 300
_BROWSER_HOLD_SECONDS = _read_int_env("COURT_GUARANTEE_BROWSER_HOLD_SECONDS", 8)
_BROWSER_HOLD_SECONDS_ON_FAILURE = _read_int_env("COURT_GUARANTEE_BROWSER_HOLD_SECONDS_ON_FAILURE", 30)
_DEFAULT_NATURAL_ID_NUMBER = "110101" + "19900307" + "7715"
_DEFAULT_LEGAL_ID_NUMBER = "91440101MA59TEST8X"


class CaseGuaranteeInfoOut(Schema):
    case_id: int
    case_name: str
    court_name: str | None
    cause_of_action: str
    preserve_amount: str | None
    preserve_category: str
    has_case_number: bool
    has_court_credential: bool = False
    our_party_is_plaintiff_side: bool = False
    insurance_company_name: str = _DEFAULT_INSURANCE_COMPANY
    insurance_company_options: list[str] = _GUARANTEE_INSURANCE_COMPANY_OPTIONS
    consultant_code: str = ""
    quote_context: dict[str, Any] | None = None
    reusable_quotes: list[dict[str, Any]] = []
    respondent_options: list[dict[str, Any]] = []


class CaseQuoteOperationIn(Schema):
    case_id: int


class CaseQuoteOperationOut(Schema):
    success: bool
    message: str
    quote_context: dict[str, Any] | None = None


class ExecuteCourtGuaranteeIn(Schema):
    case_id: int
    insurance_company_name: str | None = None
    consultant_code: str | None = None
    selected_respondent_ids: list[int] | None = None


class ExecuteCourtGuaranteeOut(Schema):
    success: bool
    message: str
    session_id: int | None = None
    status: str | None = None
