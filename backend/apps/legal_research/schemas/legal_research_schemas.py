from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SearchModeLiteral = Literal["expanded", "single"]
CapabilityIntentLiteral = Literal[
    "similar_case",
    "same_court_precedent",
    "claim_style",
    "reasoning_style",
    "defense_risk",
]
CapabilityStatusLiteral = Literal["ok", "partial", "failed"]
CapabilityDecisionLiteral = Literal["accept", "review", "reject"]


class LegalResearchTaskCreateIn(BaseModel):
    credential_id: int = Field(..., gt=0, description="wkxx账号凭证ID")
    keyword: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="检索关键词；支持空格、逗号、分号、换行分隔多个关键词",
    )
    case_summary: str = Field(..., min_length=10, max_length=8000, description="案情简述")
    search_mode: SearchModeLiteral = Field(
        default="expanded", description="检索模式：expanded(扩展检索) 或 single(单检索)"
    )
    target_count: int = Field(default=3, ge=1, le=20, description="目标相似案例数量")
    max_candidates: int = Field(default=100, ge=5, le=200, description="最大扫描案例数")
    min_similarity_score: float = Field(default=0.9, ge=0.0, le=1.0, description="最低相似度阈值")
    llm_model: str | None = Field(default=None, min_length=1, max_length=128, description="硅基流动模型ID")


class LegalResearchTaskOut(BaseModel):
    id: int
    credential_id: int
    keyword: str
    case_summary: str
    search_mode: SearchModeLiteral
    target_count: int
    max_candidates: int
    min_similarity_score: float
    status: str
    progress: int
    scanned_count: int
    matched_count: int
    candidate_count: int
    message: str
    error: str
    llm_backend: str
    llm_model: str
    q_task_id: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LegalResearchResultOut(BaseModel):
    id: int
    task_id: int
    rank: int
    source_doc_id: str
    source_url: str
    title: str
    court_text: str
    document_number: str
    judgment_date: str
    case_digest: str
    similarity_score: float
    match_reason: str
    has_pdf: bool
    created_at: datetime


class LegalResearchCreateOut(BaseModel):
    task_id: int
    status: str


class AgentSearchCourtScopeIn(BaseModel):
    mode: Literal["same_court", "same_level", "region"] = Field(default="same_court", description="法院范围模式")
    court_name: str = Field(default="", max_length=255, description="法院名称")
    region_code: str = Field(default="", max_length=64, description="行政区划编码")


class AgentSearchYearRangeIn(BaseModel):
    from_year: int | None = Field(default=None, alias="from", ge=1980, le=2100, description="起始年份")
    to: int | None = Field(default=None, ge=1980, le=2100, description="结束年份")


class AgentSearchFiltersIn(BaseModel):
    doc_types: list[str] = Field(default_factory=lambda: ["judgment"], description="文书类型过滤")
    case_stage: list[str] = Field(default_factory=list, description="审级过滤")


class AgentSearchBudgetIn(BaseModel):
    timeout_ms: int = Field(default=20000, ge=3000, le=120000, description="总超时预算（毫秒）")
    max_candidates: int = Field(default=160, ge=5, le=200, description="最大候选扫描数")


class AgentSearchRequestV1(BaseModel):
    version: Literal["v1"] = "v1"
    credential_id: int = Field(..., gt=0, description="账号凭证ID")
    intent: CapabilityIntentLiteral = Field(default="similar_case", description="检索意图")
    facts: str = Field(..., min_length=5, max_length=8000, description="事实摘要")
    legal_issue: str = Field(default="", max_length=2000, description="争点摘要")
    cause_type: str = Field(default="", max_length=255, description="案由")
    court_scope: AgentSearchCourtScopeIn = Field(default_factory=AgentSearchCourtScopeIn, description="法院范围约束")
    year_range: AgentSearchYearRangeIn = Field(default_factory=AgentSearchYearRangeIn, description="年份约束")
    filters: AgentSearchFiltersIn = Field(default_factory=AgentSearchFiltersIn, description="扩展过滤项")
    target_count: int = Field(default=5, ge=1, le=20, description="目标返回数量")
    budget: AgentSearchBudgetIn = Field(default_factory=AgentSearchBudgetIn, description="调用预算")
    search_mode: SearchModeLiteral = Field(default="expanded", description="检索模式：expanded 或 single")


class AgentSearchSubscoresOut(BaseModel):
    facts_match: float = Field(default=0.0)
    legal_relation_match: float = Field(default=0.0)
    dispute_match: float = Field(default=0.0)
    damage_match: float = Field(default=0.0)


class AgentSearchSnippetsOut(BaseModel):
    claims: str = ""
    findings: str = ""
    reasoning: str = ""
    holdings: str = ""


class RetrievalHitV1(BaseModel):
    doc_id: str
    title: str
    court: str
    judgment_date: str
    score: float
    decision: CapabilityDecisionLiteral
    subscores: AgentSearchSubscoresOut
    conflicts: list[str] = Field(default_factory=list)
    snippets: AgentSearchSnippetsOut = Field(default_factory=AgentSearchSnippetsOut)
    why_selected: str
    source_url: str


class AgentSearchQueryTraceOut(BaseModel):
    class QueryTypeMetric(BaseModel):
        scanned: int = 0
        matched: int = 0
        contribution_rate: float = 0.0

    primary_queries: list[str] = Field(default_factory=list)
    expansion_queries: list[str] = Field(default_factory=list)
    feedback_queries: list[str] = Field(default_factory=list)
    query_type_metrics: dict[str, QueryTypeMetric] = Field(default_factory=dict)
    budget_used_ms: int = 0
    candidates_scanned: int = 0


class AgentSearchResponseV1(BaseModel):
    version: Literal["v1"] = "v1"
    request_id: str
    status: CapabilityStatusLiteral
    degradation_flags: list[str] = Field(default_factory=list)
    query_trace: AgentSearchQueryTraceOut = Field(default_factory=AgentSearchQueryTraceOut)
    results: list[RetrievalHitV1] = Field(default_factory=list)
