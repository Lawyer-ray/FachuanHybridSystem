"""POI Service HTTP client for communicating with the Apache POI microservice.

Provides methods to call the POI service for document generation (complaints,
due diligence reports, template rendering) via REST API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("apps.core")

# Default POI service URL (configurable via Django settings)
_POI_SERVICE_URL = "http://127.0.0.1:8090"


def _get_poi_url() -> str:  # pragma: no cover
    """Get the POI service base URL from Django settings or default."""
    try:
        from django.conf import settings

        return getattr(settings, "POI_SERVICE_URL", _POI_SERVICE_URL)
    except Exception:
        return _POI_SERVICE_URL


class POIServiceClient:  # pragma: no cover
    """HTTP client for the Apache POI document generation service."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):  # pragma: no cover
        self.base_url = (base_url or _get_poi_url()).rstrip("/")
        self.timeout = timeout

    def _post(self, endpoint: str, payload: dict[str, Any]) -> bytes:  # pragma: no cover
        """Send POST request and return raw bytes."""
        url = f"{self.base_url}/api/documents{endpoint}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.content

    def _get(self, endpoint: str) -> dict[str, Any]:  # pragma: no cover
        """Send GET request and return JSON."""
        url = f"{self.base_url}/api/documents{endpoint}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    def health_check(self) -> bool:
        """Check if the POI service is running.

        Returns:
            True if POI service is available, False otherwise
        """
        try:
            result = self._get("/health")
            return result.get("status") == "ok"
        except Exception as e:
            logger.warning("POI服务健康检查失败: %s", e)
            return False

    def generate_complaint(self, data: dict[str, Any]) -> bytes:
        """Generate 起诉状 (complaint) document.

        Args:
            data: Complaint data dict matching ComplaintRequest schema:
                - courtName: 法院名称
                - plaintiffName: 原告名称
                - plaintiffType: 原告类型 ("自然人"/"法人")
                - plaintiffIdNumber: 原告证件号
                - plaintiffAddress: 原告地址
                - plaintiffPhone: 原告电话
                - defendantName: 被告名称
                - defendantType: 被告类型
                - defendantIdNumber: 被告证件号
                - defendantAddress: 被告地址
                - defendantPhone: 被告电话
                - lawyerName: 律师姓名
                - lawyerFirm: 律所名称
                - lawyerLicense: 执业证号
                - causeOfAction: 案由
                - litigationClaims: 诉讼请求 (list of strings)
                - factsAndReasons: 事实与理由
                - evidenceList: 证据清单
                - signatureDate: 签署日期

        Returns:
            DOCX file bytes
        """
        logger.info("POI: 生成起诉状, 原告=%s, 被告=%s", data.get("plaintiffName"), data.get("defendantName"))
        return self._post("/complaint", data)

    def generate_report(self, data: dict[str, Any]) -> bytes:
        """Generate 尽调报告 (due diligence report) document.

        Args:
            data: Report data dict matching ReportRequest schema:
                - reportTitle: 报告标题
                - projectName: 项目名称
                - reportDate: 报告日期
                - author: 编制人
                - confidentialityLevel: 密级
                - companyName: 目标公司名称
                - companyRegistrationNumber: 统一社会信用代码
                - registeredCapital: 注册资本
                - establishedDate: 成立日期
                - legalRepresentative: 法定代表人
                - businessScope: 经营范围
                - financialData: 财务数据 (list of FinancialYear)
                - equityStructure: 股权结构 (list of EquityHolder)
                - riskItems: 风险事项 (list of RiskItem)
                - sections: 自定义章节 (list of ReportSection)

        Returns:
            DOCX file bytes
        """
        logger.info("POI: 生成尽调报告, 项目=%s", data.get("projectName"))
        return self._post("/report", data)

    def render_template(self, template_name: str, context: dict[str, Any]) -> bytes:  # pragma: no cover
        """Render a .docx template with context data.

        Args:
            template_name: Template file name (relative to templates dir)
            context: Placeholder values ({{key}} -> value)

        Returns:
            DOCX file bytes
        """
        logger.info("POI: 渲染模板, template=%s, keys=%s", template_name, list(context.keys()))
        return self._post(
            "/template/render",
            {
                "templateName": template_name,
                "context": context,
            },
        )

    def list_templates(self) -> list[str]:  # pragma: no cover
        """List available templates."""
        result: dict[str, Any] = self._get("/templates")
        templates: list[str] = result.get("templates", [])
        return templates

    def format_contract(  # pragma: no cover
        self,
        docx_bytes: bytes,
        config: dict[str, Any] | None = None,
        output_filename: str = "formatted_contract.docx"
    ) -> bytes:
        """格式化合同文档

        Args:
            docx_bytes: 原始DOCX文件字节
            config: 格式配置（可选）
            output_filename: 输出文件名

        Returns:
            格式化后的DOCX文件字节
        """
        logger.info("POI: 格式化合同, 原始大小=%d bytes", len(docx_bytes))

        payload = {
            "docxBytes": list(docx_bytes),
            "outputFileName": output_filename
        }

        if config:
            payload["config"] = config  # type: ignore[assignment]

        return self._post("/contract/format", payload)


# ── Singleton ──────────────────────────────────────────────────────────────

_default_client: POIServiceClient | None = None


def get_poi_client() -> POIServiceClient:  # pragma: no cover
    """Get or create the default POI service client."""
    global _default_client
    if _default_client is None:
        _default_client = POIServiceClient()
    return _default_client
