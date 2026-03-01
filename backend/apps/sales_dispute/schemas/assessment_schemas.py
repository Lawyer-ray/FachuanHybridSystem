"""
案件评估 Schema 定义

API 层的请求/响应数据结构
"""

from __future__ import annotations

from datetime import date

from ninja import Schema


class EvidenceItemSchema(Schema):
    """证据条目"""

    evidence_type: str
    has_evidence: bool
    quality_score: int


class InterruptionEventSchema(Schema):
    """时效中断事由"""

    event_type: str
    event_date: date


class AssessmentRequest(Schema):
    """综合评估请求"""

    case_id: int
    contract_basis: str
    principal_amount: float
    evidence_items: list[EvidenceItemSchema]
    last_claim_date: date
    interruptions: list[InterruptionEventSchema]
    solvency_rating: str = "unknown"
    has_agreed_jurisdiction: bool = False
    agreed_court: str = ""
    is_agreed_valid: bool | None = None
    invalid_reason: str = ""
    plaintiff_location: str = ""
    defendant_location: str = ""
    local_avg_salary: float | None = None
    willing_to_mediate: bool = False
    guarantee_debtor: bool = False
    principal_due_date: date | None = None
    remarks: str = ""


class EvidenceItemResponse(Schema):
    """证据评分明细响应"""

    evidence_type: str
    has_evidence: bool
    quality_score: int
    weight: float
    weighted_score: float


class JurisdictionResponseSchema(Schema):
    """管辖权分析响应"""

    has_agreed_jurisdiction: bool
    agreed_court: str
    is_agreed_valid: bool | None
    invalid_reason: str
    plaintiff_location: str
    defendant_location: str
    recommended_court: str
    recommendation_reason: str
    alternative_court: str
    legal_basis: str


class StrategyResponseSchema(Schema):
    """策略推荐响应"""

    strategy_type: str
    recommendation_reason: str
    estimated_duration: str
    applicable_conditions: str
    suggest_preservation: bool
    preservation_reason: str


class LimitationResponse(Schema):
    """时效计算响应"""

    status: str
    expiry_date: date
    remaining_days: int
    base_date: date
    risk_warning: str
    guarantee_expiry_date: date | None = None


class AssessmentResponse(Schema):
    """综合评估响应"""

    assessment_id: int
    case_id: int
    contract_basis: str
    principal_amount: float
    evidence_total_score: float
    evidence_grade: str
    evidence_details: list[EvidenceItemResponse]
    limitation_status: str
    limitation_expiry_date: date | None
    remaining_days: int
    risk_warning: str
    guarantee_expiry_date: date | None = None
    solvency_rating: str
    assessment_grade: str
    jurisdiction: JurisdictionResponseSchema
    strategy: StrategyResponseSchema
    remarks: str


class LimitationRequest(Schema):
    """时效计算请求"""

    last_claim_date: date
    interruptions: list[InterruptionEventSchema]
    guarantee_debtor: bool = False
    principal_due_date: date | None = None


class JurisdictionRequest(Schema):
    """管辖权分析请求"""

    has_agreed_jurisdiction: bool = False
    agreed_court: str = ""
    is_agreed_valid: bool | None = None
    invalid_reason: str = ""
    plaintiff_location: str = ""
    defendant_location: str = ""


class StrategyRequest(Schema):
    """策略推荐请求"""

    principal_amount: float
    evidence_score: float
    solvency_rating: str = "unknown"
    local_avg_salary: float | None = None
    willing_to_mediate: bool = False
