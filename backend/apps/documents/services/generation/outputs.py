"""
Pydantic 输出模型定义

用于诉讼文书结构化输出解析.
"""

from pydantic import BaseModel, Field


class PartyInfo(BaseModel):
    name: str = Field(description="姓名/名称")
    role: str = Field(description="角色(原告/被告)")
    id_number: str = Field(default="", description="身份证号/统一社会信用代码")
    address: str = Field(default="", description="地址")


class ComplaintOutput(BaseModel):
    title: str = Field(description="标题")
    parties: list[PartyInfo] = Field(description="当事人信息")
    litigation_request: str = Field(description="诉讼请求")
    facts_and_reasons: str = Field(description="事实与理由")
    evidence: list[str] = Field(default_factory=list, description="证据列表")


class DefenseOutput(BaseModel):
    title: str = Field(description="标题")
    parties: list[PartyInfo] = Field(description="当事人信息")
    defense_opinion: str = Field(description="答辩意见")
    defense_reasons: str = Field(description="答辩理由")
    evidence: list[str] = Field(default_factory=list, description="证据列表")


class ExecutionRequestOutput(BaseModel):
    """强制执行申请书 - 申请执行事项 LLM 输出."""

    principal: float | None = Field(description="本金金额（元），如借款本金、货款本金", default=None)
    principal_desc: str = Field(description="本金描述，如'借款本金'、'货款'", default="")
    confirmed_interest: float = Field(description="调解书确认的利息金额（元）", default=0)
    attorney_fee: float = Field(description="律师代理费（元）", default=0)
    guarantee_fee: float = Field(description="财产保全担保费（元）", default=0)
    litigation_fee: float = Field(description="受理费（元）", default=0)
    preservation_fee: float = Field(description="财产保全费（元）", default=0)
    announcement_fee: float = Field(description="公告费（元）", default=0)
    # 利息计算参数
    interest_start_date: str | None = Field(description="利息起算日（YYYY-MM-DD格式）", default=None)
    rate_type: str = Field(description="利率类型: lpr 或 fixed", default="lpr")
    lpr_multiplier: float | None = Field(description="LPR 倍数（如 1.3、4 倍）", default=None)
    fixed_rate: float | None = Field(description="固定年利率（%，如 4.5）", default=None)
    interest_cap: float | None = Field(description="利息上限（元），如有", default=None)
    interest_cap_desc: str = Field(description="利息上限描述，如'以不超过 XXX 元为限'", default="")
