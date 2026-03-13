from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LegalResearchTaskCreateIn(BaseModel):
    credential_id: int = Field(..., gt=0, description="wkxx账号凭证ID")
    keyword: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="检索关键词；支持空格、逗号、分号、换行分隔多个关键词",
    )
    case_summary: str = Field(..., min_length=10, max_length=8000, description="案情简述")
    target_count: int = Field(default=3, ge=1, le=20, description="目标相似案例数量")
    max_candidates: int = Field(default=100, ge=5, le=200, description="最大扫描案例数")
    min_similarity_score: float = Field(default=0.9, ge=0.0, le=1.0, description="最低相似度阈值")
    llm_model: str | None = Field(default=None, min_length=1, max_length=128, description="硅基流动模型ID")


class LegalResearchTaskOut(BaseModel):
    id: int
    credential_id: int
    keyword: str
    case_summary: str
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
