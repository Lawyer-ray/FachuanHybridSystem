"""LLM 结构化抽取契约（Pydantic）。

与 ``apps.core.llm.structured_output.json_schema_instructions`` 配合使用：
schema 交给模型、输出交给 :func:`parse_model_content` 校验。

设计原则：
- **模型只输出文档里字面存在的信息**，不做推测。找不到就给 ``null``/
  空列表——把「没有」和「没找到」区分开，避免模型用常识补全（例如把签约
  日期填成今天、把律所名字脑补成我方）。
- 数值一律用字符串承载（``amount_text``/``date_text``），真实换算放到
  ``normalize`` 里做确定性处理。模型对「贰万元整 → 20000」这类换算容易
  在复杂表述上出错，且不同合同写法差异极大。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: 每个字段允许出现在 ``source_quote`` 里的定位依据上限（防止模型粘贴整段）
_MAX_QUOTE_CHARS = 120


class ExtractedParty(BaseModel):
    """合同当事人（甲方/委托方一侧，以及对方当事人）。"""

    name: str = Field(default="", description="当事人全称，按合同原文逐字抄录，不要缩写或补全")
    role_in_contract: str = Field(
        default="",
        description="合同中的身份，取值：甲方 / 乙方 / 丙方 / 委托人 / 对方当事人 / 其他",
    )
    entity_type: str = Field(
        default="",
        description="主体类型：legal=公司等法人或非法人组织，natural=自然人，unknown=无法判断",
    )
    id_number: str = Field(
        default="",
        description="统一社会信用代码或身份证号，逐字抄录，没有则留空",
    )
    legal_representative: str = Field(default="", description="法定代表人或负责人姓名，没有则留空")
    address: str = Field(default="", description="合同载明的地址，没有则留空")
    is_law_firm: bool = Field(
        default=False,
        description="该主体是否为提供法律服务的律所（乙方）。律所不是合同当事人，必须标 true",
    )


class ExtractedLawyer(BaseModel):
    """合同指定的承办/主办律师。"""

    name: str = Field(default="", description="律师姓名，逐字抄录，不要带「律师」二字以外的职衔")
    law_firm: str = Field(default="", description="该律师所在的律所名称，没有则留空")
    is_primary: bool = Field(
        default=False,
        description="合同是否明确指明其为主办律师（出现「主办律师」字样）。无法判断时填 false",
    )


class ContractExtraction(BaseModel):
    """LLM 对一份法律服务合同的抽取结果。"""

    document_kind: str = Field(
        default="",
        description=(
            "文档性质，取值：legal_service_contract=法律服务/委托代理合同，"
            "supplementary=补充协议，advisor=常年法律顾问合同，other=其他"
        ),
    )
    title: str = Field(default="", description="合同标题，如「非诉法律服务合同」「委托代理合同」")
    case_type: str = Field(
        default="",
        description=(
            "合同类型，只能取以下之一：civil=民商事诉讼，criminal=刑事，administrative=行政，"
            "labor=劳动仲裁，intl=商事仲裁，special=专项服务（含非诉专项、税务稽查应对等），"
            "advisor=常年法律顾问"
        ),
    )
    client_name: str = Field(default="", description="委托方（甲方）名称，逐字抄录")
    matter_summary: str = Field(
        default="",
        description="委托事项的一句话概括（不超过 40 字），用于生成合同名称。例：税务稽查应对非诉咨询",
    )
    counterparty_names: list[str] = Field(
        default_factory=list,
        description="除委托方外，合同中出现的其他当事人名称（不含律所）。没有则为空数组",
    )

    fee_mode: str = Field(
        default="",
        description=(
            "收费模式，只能取以下之一：FIXED=固定收费，SEMI_RISK=半风险（固定+风险），"
            "FULL_RISK=全风险，CUSTOM=其他自定义。无法判断时留空"
        ),
    )
    amount_text: str = Field(
        default="",
        description=(
            "律师费总额的原文表述，逐字抄录（如「贰万元整（20000.00）」）。"
            "若分多个律所分别收费，抄录合计总额；若为风险比例则填比例原文"
        ),
    )
    amount_is_total: bool = Field(
        default=False,
        description="amount_text 是否为本合同项下的费用总额（true）还是单一主体份额（false，如各付一万元）",
    )
    custom_terms: str = Field(
        default="",
        description="其他与收费、支付节点相关的特殊约定原文摘录（不超过 100 字），没有则留空",
    )

    start_date_text: str = Field(default="", description="服务起始日期的原文表述，没有则留空")
    end_date_text: str = Field(default="", description="服务终止日期或终止条件的原文表述，没有则留空")
    sign_date_text: str = Field(
        default="",
        description="签约日期的原文表述。若落款处是空的「年 月 日」，则留空，不要填其他日期",
    )

    parties: list[ExtractedParty] = Field(
        default_factory=list,
        description="合同当事人列表。**必须包含律所**（标 is_law_firm=true），系统会自行剔除",
    )
    lawyers: list[ExtractedLawyer] = Field(default_factory=list, description="合同指派的主办/承办律师，没有则为空数组")

    source_quotes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "关键字段的原文依据，键为字段名（client_name/case_type/fee_mode/amount_text/start_date_text/"
            "end_date_text/sign_date_text），值为不超过 60 字的原文片段"
        ),
    )
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "各字段把握度 0-1，键同 source_quotes。低于 0.6 表示需要人工核对。没有把握的字段请给低分而不是填猜测值"
        ),
    )
    notes: str = Field(
        default="",
        description="需要提醒录入人员的注意事项（如合同信息自相矛盾、金额表述不清），没有则留空",
    )


def trim_quotes(extraction: ContractExtraction) -> ContractExtraction:
    """裁掉模型可能超长的原文依据，避免前端展示炸开。"""
    cleaned: dict[str, str] = {}
    for key, quote in extraction.source_quotes.items():
        text = str(quote or "").strip()
        if text:
            cleaned[key] = text[:_MAX_QUOTE_CHARS]
    extraction.source_quotes = cleaned
    return extraction
