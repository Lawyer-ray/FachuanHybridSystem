"""Ninja API endpoints for POI document generation.

Provides API routes that proxy to the Apache POI service for generating
complaints, due diligence reports, and template rendering.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from ninja import Field, Router, Schema

logger = logging.getLogger("apps.automation")

router = Router(tags=["POI 文档生成"])


# ── Request Schemas ──


class ComplaintSchema(Schema):
    """起诉状请求参数"""

    court_name: str = Field(..., description="法院名称")
    plaintiff_name: str = Field(..., description="原告名称")
    plaintiff_type: str = Field("法人", description="原告类型（自然人/法人）")
    plaintiff_id_number: str = Field("", description="原告证件号")
    plaintiff_address: str = Field("", description="原告地址")
    plaintiff_phone: str = Field("", description="原告电话")
    plaintiff_legal_representative: str = Field("", description="原告法定代表人")
    defendant_name: str = Field(..., description="被告名称")
    defendant_type: str = Field("法人", description="被告类型")
    defendant_id_number: str = Field("", description="被告证件号")
    defendant_address: str = Field("", description="被告地址")
    defendant_phone: str = Field("", description="被告电话")
    lawyer_name: str = Field("", description="律师姓名")
    lawyer_firm: str = Field("", description="律所名称")
    lawyer_license: str = Field("", description="执业证号")
    cause_of_action: str = Field("", description="案由")
    litigation_claims: list[str] = Field(default_factory=list, description="诉讼请求")
    facts_and_reasons: str = Field("", description="事实与理由")
    evidence_list: str = Field("", description="证据清单")
    signature_date: str = Field("", description="签署日期")


class FinancialYearSchema(Schema):
    year: int
    revenue: float
    profit: float
    total_assets: float
    total_liabilities: float


class EquityHolderSchema(Schema):
    name: str
    percentage: float
    type: str = "法人"
    contribution_method: str = "货币"


class RiskItemSchema(Schema):
    category: str
    description: str
    severity: str = "中"
    recommendation: str = ""


class ReportSectionSchema(Schema):
    title: str
    level: int = 2
    content: str = ""
    table_data: list[dict[str, str]] | None = None
    bullet_points: list[str] | None = None


class ReportSchema(Schema):
    """尽调报告请求参数"""

    report_title: str = Field(..., description="报告标题")
    project_name: str = Field(..., description="项目名称")
    report_date: str = Field("", description="报告日期")
    author: str = Field("", description="编制人")
    confidentiality_level: str = Field("保密", description="密级")
    company_name: str = Field("", description="目标公司名称")
    company_registration_number: str = Field("", description="统一社会信用代码")
    registered_capital: str = Field("", description="注册资本")
    established_date: str = Field("", description="成立日期")
    legal_representative: str = Field("", description="法定代表人")
    business_scope: str = Field("", description="经营范围")
    financial_data: list[FinancialYearSchema] = Field(default_factory=list)
    equity_structure: list[EquityHolderSchema] = Field(default_factory=list)
    risk_items: list[RiskItemSchema] = Field(default_factory=list)
    sections: list[ReportSectionSchema] = Field(default_factory=list)


# ── Endpoints ──


@router.get("/health", summary="POI 服务健康检查")
async def poi_health(request: Any) -> dict[str, Any]:  # pragma: no cover
    """检查 POI 服务是否可用"""
    from apps.core.services.poi_client import get_poi_client

    try:
        client = get_poi_client()
        result = await client.ahealth_check()
        return {"status": "ok", "poi_service": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/complaint", summary="生成起诉状")
async def generate_complaint(request: Any, payload: ComplaintSchema) -> HttpResponse:  # pragma: no cover
    """通过 POI 服务生成起诉状 DOCX 文件"""
    from apps.core.services.poi_client import get_poi_client

    data = payload.dict()
    # Convert snake_case to camelCase for Java
    camel_data = {
        "".join(word.capitalize() if i else word for i, word in enumerate(k.split("_"))): v for k, v in data.items()
    }

    try:
        client = get_poi_client()
        docx_bytes = await client.agenerate_complaint(camel_data)
        response = HttpResponse(
            docx_bytes, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response["Content-Disposition"] = 'attachment; filename="complaint.docx"'
        return response
    except Exception as e:
        logger.error("POI 起诉状生成失败: %s", e)
        return HttpResponse(f'{{"error": "{e}"}}', status=500, content_type="application/json")


@router.post("/report", summary="生成尽调报告")
async def generate_report(request: Any, payload: ReportSchema) -> HttpResponse:  # pragma: no cover
    """通过 POI 服务生成尽调报告 DOCX 文件"""
    from apps.core.services.poi_client import get_poi_client

    data = payload.dict()
    camel_data = {
        "".join(word.capitalize() if i else word for i, word in enumerate(k.split("_"))): v for k, v in data.items()
    }

    try:
        client = get_poi_client()
        docx_bytes = await client.agenerate_report(camel_data)
        response = HttpResponse(
            docx_bytes, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response["Content-Disposition"] = 'attachment; filename="report.docx"'
        return response
    except Exception as e:
        logger.error("POI 尽调报告生成失败: %s", e)
        return HttpResponse(f'{{"error": "{e}"}}', status=500, content_type="application/json")
