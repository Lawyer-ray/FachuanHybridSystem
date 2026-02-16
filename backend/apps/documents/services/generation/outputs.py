"""
Pydantic 输出模型定义

用于 LangChain JsonOutputParser 的结构化输出解析.
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
