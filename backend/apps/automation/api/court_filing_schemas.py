"""法院一张网在线立案 API — 常量与 Schema 定义。"""

from __future__ import annotations

import re
from typing import Any

from ninja import Schema

_FILING_TYPE_CIVIL = "civil"
_FILING_TYPE_EXECUTION = "execution"
_VALID_FILING_TYPES = {_FILING_TYPE_CIVIL, _FILING_TYPE_EXECUTION}
_FILING_ENGINE_API = "api"
_FILING_ENGINE_PLAYWRIGHT = "playwright"
_VALID_FILING_ENGINES = {_FILING_ENGINE_API, _FILING_ENGINE_PLAYWRIGHT}

_PLAINTIFF_SIDE_STATUSES = {"plaintiff", "applicant", "appellant", "orig_plaintiff"}
_DEFENDANT_SIDE_STATUSES = {"defendant", "respondent", "appellee", "orig_defendant", "criminal_defendant"}
_THIRD_SIDE_STATUSES = {"third", "third_party", "orig_third", "victim"}
_EXECUTION_HINT_STATUSES = {"applicant", "respondent"}

_TEXT_NORMALIZE_PATTERN = re.compile(r"[\s\-_./\\()（）【】\[\]<>《》:：,，;；'\"`]+")
_DEFAULT_SLOT_BY_FILING_TYPE = {_FILING_TYPE_CIVIL: "5", _FILING_TYPE_EXECUTION: "4"}

_SLOT_RULES: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    _FILING_TYPE_CIVIL: {
        "0": {
            "strong": ("民事起诉状", "起诉状", "诉状", "起诉书"),
            "weak": ("诉讼请求", "事实与理由"),
            "exclude": ("执行申请书", "证据目录", "送达地址确认书"),
        },
        "1": {
            "strong": (
                "当事人身份证明",
                "身份证明",
                "身份证",
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
                "户口簿",
                "户籍证明",
            ),
            "weak": ("主体资格", "自然人身份证明"),
            "exclude": ("授权委托书", "证据目录", "委托代理", "委托手续"),
        },
        "2": {
            "strong": (
                "授权委托书",
                "授权委托",
                "委托代理",
                "委托手续",
                "委托材料",
                "律师执业证",
                "执业证",
                "律师证",
                "所函",
                "代理人身份证明",
            ),
            "weak": ("代理人", "受托人"),
            "exclude": (
                "送达地址确认书",
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
            ),
        },
        "3": {
            "strong": ("证据目录", "证据清单", "证据明细", "证据材料"),
            "weak": ("证据", "证明材料", "聊天记录", "转账记录", "录音"),
            "exclude": ("身份证明", "授权委托书", "委托材料"),
        },
        "4": {
            "strong": ("送达地址确认书", "送达地址确认", "地址确认书"),
            "weak": ("送达地址",),
            "exclude": (),
        },
    },
    _FILING_TYPE_EXECUTION: {
        "0": {
            "strong": ("执行申请书", "申请执行书", "强制执行申请书", "恢复执行申请书"),
            "weak": ("申请执行", "执行申请"),
            "exclude": ("限制高消费", "纳入失信", "公开信息", "出境", "送达地址确认书"),
        },
        "1": {
            "strong": ("执行依据", "判决书", "裁定书", "调解书", "生效法律文书", "执行裁定"),
            "weak": ("生效证明", "裁判文书"),
            "exclude": ("执行申请书",),
        },
        "2": {
            "strong": (
                "授权委托书",
                "授权委托",
                "委托代理",
                "委托手续",
                "委托材料",
                "律师执业证",
                "执业证",
                "律师证",
                "所函",
                "代理人身份证明",
            ),
            "weak": ("代理人", "受托人"),
            "exclude": (
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
            ),
        },
        "3": {
            "strong": (
                "申请人身份材料",
                "申请执行人身份材料",
                "申请人身份证明",
                "申请执行人身份证明",
                "身份证明",
                "身份证",
                "营业执照",
                "统一社会信用代码",
                "法定代表人身份证明",
                "户口簿",
            ),
            "weak": ("主体资格",),
            "exclude": ("授权委托书", "委托材料", "送达地址确认书", "委托代理", "委托手续"),
        },
        "4": {
            "strong": ("送达地址确认书", "送达地址确认", "地址确认书"),
            "weak": ("送达地址",),
            "exclude": (),
        },
    },
}


class CaseFilingInfoOut(Schema):
    """案件立案信息"""

    case_id: int
    case_name: str
    cause_of_action: str
    court_name: str | None
    target_amount: str | None
    plaintiff_name: str | None
    defendant_name: str | None
    our_party_is_plaintiff_side: bool = False
    has_court_credential: bool = False
    has_http_plugin: bool = False
    suggested_filing_type: str = _FILING_TYPE_CIVIL
    default_filing_engine: str = _FILING_ENGINE_API


class ExecuteCourtFilingIn(Schema):
    """执行立案请求"""

    case_id: int
    filing_type: str | None = None
    filing_engine: str | None = None


class ExecuteCourtFilingOut(Schema):
    """执行立案响应"""

    success: bool
    message: str
    session_id: int | None = None
    status: str | None = None
