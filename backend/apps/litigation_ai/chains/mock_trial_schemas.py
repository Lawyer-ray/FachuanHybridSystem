"""模拟庭审结构化输出 Schema."""

from pydantic import BaseModel, Field


class EvidenceExamItem(BaseModel):
    """单个质证维度."""

    opinion: str = Field(description="质证意见")
    challenge_strength: str = Field(description="质疑强度: strong/moderate/weak")


class CrossExamOpinion(BaseModel):
    """对方律师对单份证据的质证意见."""

    evidence_name: str = Field(default="", description="证据名称")
    authenticity: EvidenceExamItem = Field(description="真实性质证")
    legality: EvidenceExamItem = Field(description="合法性质证")
    relevance: EvidenceExamItem = Field(description="关联性质证")
    proof_power: EvidenceExamItem = Field(description="证明力分析")
    suggested_response: str = Field(description="建议的回应策略")
    risk_level: str = Field(description="风险等级: high/medium/low")


class DisputeFocus(BaseModel):
    """争议焦点."""

    description: str = Field(description="焦点描述")
    focus_type: str = Field(description="焦点类型: 事实争议/法律适用争议/程序争议")
    plaintiff_position: str = Field(description="原告立场")
    defendant_position: str = Field(description="被告可能立场")
    key_evidence: list[str] = Field(default_factory=list, description="关键证据")
    burden_of_proof: str = Field(description="举证责任方")


class EvidenceStrengthItem(BaseModel):
    """证据强弱对比项."""

    focus: str = Field(description="对应的争议焦点")
    plaintiff_strength: str = Field(description="原告证据强度: strong/moderate/weak")
    defendant_strength: str = Field(description="被告证据强度: strong/moderate/weak")
    analysis: str = Field(description="分析说明")


class JudgePerspectiveReport(BaseModel):
    """法官视角分析报告."""

    dispute_focuses: list[DisputeFocus] = Field(description="争议焦点列表")
    evidence_strength_comparison: list[EvidenceStrengthItem] = Field(description="证据强弱对比")
    risk_assessment: str = Field(description="整体风险评估")
    judge_questions: list[str] = Field(description="法官可能提出的问题")
    overall_win_probability: str = Field(description="整体胜诉概率评估，如 60%-70%")
    recommended_strategy: str = Field(description="建议的庭审策略")
