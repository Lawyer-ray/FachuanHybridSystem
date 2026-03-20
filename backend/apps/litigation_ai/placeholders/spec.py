"""Module for spec."""


class LitigationPlaceholderKeys:
    PLAINTIFF = "原告"
    DEFENDANT = "被告"
    RESPONDENT = "答辩人"
    CAUSE_OF_ACTION = "案由"
    DATE = "日期"

    COURT = "审理机构"

    COMPLAINT_PARTY = "起诉状当事人信息"
    COMPLAINT_SIGNATURE = "起诉状签名盖章信息"

    DEFENSE_PARTY = "答辩状当事人信息"
    DEFENSE_SIGNATURE = "答辩状签名盖章信息"

    VARIABLE_LITIGATION_REQUEST = "诉讼请求"
    VARIABLE_FACTS_AND_REASONS = "事实与理由"

    VARIABLE_DEFENSE_OPINION = "答辩意见"
    VARIABLE_DEFENSE_REASONS = "答辩理由"

    # 强制执行申请书
    ENFORCEMENT_APPLICANT_PARTY = "申请人信息"
    ENFORCEMENT_RESPONDENT_PARTY = "被申请人信息"
    ENFORCEMENT_RESPONDENT_NAME = "被申请人名称"
    ENFORCEMENT_CASE_NUMBER = "执行依据案号"
    ENFORCEMENT_COURT = "管辖法院"
    ENFORCEMENT_EFFECTIVE_DATE = "判决生效日期"
    ENFORCEMENT_TARGET_AMOUNT = "涉案金额"
    ENFORCEMENT_JUDGMENT_MAIN_TEXT = "执行依据主文"
