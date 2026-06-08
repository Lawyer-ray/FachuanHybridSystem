"""企查查响应结构标准化适配器。

企查查 MCP 工具返回的数据格式与天眼查不同，需要独立适配。
企查查工具统一接受 searchKey 参数，返回结构化 JSON 或 markdown。
"""

from __future__ import annotations

import re
from typing import Any


class QichachaResponseAdapter:
    """将企查查 MCP 工具响应适配为统一的内部数据格式。"""

    _ITEM_KEYS = (
        "items",
        "list",
        "rows",
        "records",
        "data",
        "result",
        "resultList",
        "companyList",
        "企业信息",
        "搜索结果",
        "股东信息列表",
        "主要人员列表",
        "风险信息",
        "招投标信息列表",
    )
    _MARKDOWN_TABLE_ROW_RE = re.compile(r"^\|\s*(?P<key>[^|]+?)\s*\|\s*(?P<value>.*?)\s*\|\s*$")
    _MARKDOWN_HEADER_RE = re.compile(r"^#{1,3}\s+(?P<name>.+?)\s*$")

    @staticmethod
    def pick_str(obj: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = obj.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        # QCC search result: {"企业信息": {...}} or {"搜索结果": [{...}, ...]}
        for qcc_key in ("企业信息", "搜索结果", "股东信息列表", "主要人员列表", "风险信息", "招投标信息列表"):
            value = payload.get(qcc_key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]

        queue: list[dict[str, Any]] = [payload]
        while queue:
            current = queue.pop(0)
            for key in self._ITEM_KEYS:
                value = current.get(key)
                if isinstance(value, list):
                    normalized = [item for item in value if isinstance(item, dict)]
                    if normalized:
                        return normalized
                if isinstance(value, dict):
                    queue.append(value)
        return [payload]

    def extract_primary_dict(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            # QCC: {"企业信息": {...}} or {"工商信息": {...}}
            for qcc_key in ("企业信息", "工商信息", "股东信息", "主要人员信息", "风险详情"):
                value = payload.get(qcc_key)
                if isinstance(value, dict):
                    return value
            for key in self._ITEM_KEYS:
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    return item
        return {}

    def normalize_company_summary(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "company_id": self.pick_str(item, ("company_id", "companyId", "id", "creditCode", "keyNo", "统一社会信用代码")),
            "company_name": self.pick_str(item, ("company_name", "companyName", "name", "entName", "企业名称")),
            "legal_person": self.pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative", "operName", "法定代表人")),
            "status": self.pick_str(item, ("regStatus", "status", "openStatus", "operatingStatus", "经营状态")),
            "establish_date": self.pick_str(item, ("startDate", "estiblishTime", "establishDate", "foundedDate", "成立日期")),
            "registered_capital": self.pick_str(item, ("regCapital", "registeredCapital", "regCapCur", "注册资本")),
            "phone": self.pick_str(item, ("phone", "phoneNumber", "contactPhone", "tel", "联系电话")),
        }

    def normalize_company_profile(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "company_id": self.pick_str(item, ("company_id", "companyId", "id", "creditCode", "keyNo", "统一社会信用代码")),
            "company_name": self.pick_str(item, ("company_name", "companyName", "name", "entName", "企业名称")),
            "unified_social_credit_code": self.pick_str(
                item,
                ("creditCode", "unifiedSocialCreditCode", "socialCreditCode", "unified_social_credit_code", "统一社会信用代码"),
            ),
            "legal_person": self.pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative", "operName", "法定代表人")),
            "status": self.pick_str(item, ("regStatus", "status", "openStatus", "operatingStatus", "经营状态")),
            "establish_date": self.pick_str(item, ("startDate", "estiblishTime", "establishDate", "foundedDate", "成立日期")),
            "registered_capital": self.pick_str(item, ("regCapital", "registeredCapital", "regCapCur", "注册资本")),
            "address": self.pick_str(item, ("regLocation", "address", "registeredAddress", "domicile", "注册地址")),
            "business_scope": self.pick_str(item, ("businessScope", "scope", "operatingScope", "经营范围")),
            "phone": self.pick_str(item, ("phone", "phoneNumber", "contactPhone", "tel", "联系电话")),
        }

    def normalize_risk_item(self, item: dict[str, Any], *, fallback_risk_type: str) -> dict[str, str]:
        return {
            "risk_type": self.pick_str(item, ("riskType", "type", "category")) or fallback_risk_type,
            "title": self.pick_str(item, ("title", "riskTitle", "event", "name", "caseTitle")),
            "level": self.pick_str(item, ("level", "riskLevel", "degree")),
            "amount": self.pick_str(item, ("amount", "amountStr", "money", "标的金额")),
            "publish_date": self.pick_str(item, ("date", "publishDate", "eventTime", "filingDate", "judgeDate")),
            "source": self.pick_str(item, ("source", "court", "channel", "judgeCourt")),
        }

    def normalize_shareholder_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "name": self.pick_str(item, ("name", "shareholderName", "holderName", "stockholderName")),
            "amount": self.pick_str(item, ("subConAm", "capital", "amount", "contribution", "subscribedAmount")),
            "ratio": self.pick_str(item, ("holdRatio", "ratio", "sharePercent", "stockPercent")),
            "contribution_date": self.pick_str(item, ("conDate", "date", "subscribeDate")),
            "source": self.pick_str(item, ("source", "type", "stockholderType")),
        }

    def normalize_personnel_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "hcgid": self.pick_str(item, ("hcgid", "id", "personCompanyId", "keyNo")),
            "name": self.pick_str(item, ("name", "personName", "staffName")),
            "position": self.pick_str(item, ("position", "jobTitle", "post", "staffTitle")),
            "education": self.pick_str(item, ("education", "academicDegree")),
            "source": self.pick_str(item, ("source", "type")),
        }

    def normalize_person_profile(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "hcgid": self.pick_str(item, ("hcgid", "id", "personCompanyId", "keyNo")),
            "name": self.pick_str(item, ("name", "personName", "staffName")),
            "position": self.pick_str(item, ("position", "jobTitle", "post", "staffTitle")),
            "intro": self.pick_str(item, ("intro", "introduction", "profile")),
            "resume": self.pick_str(item, ("resume", "experience", "workExperience")),
        }

    def normalize_bidding_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "title": self.pick_str(item, ("title", "announceTitle", "name", "bidTitle")),
            "project_name": self.pick_str(item, ("projectName", "project", "bidName", "projectCode")),
            "role": self.pick_str(item, ("role", "identity", "bidRole")),
            "amount": self.pick_str(item, ("amount", "amountStr", "money", "bidAmount")),
            "date": self.pick_str(item, ("date", "publishDate", "bidDate", "winningDate", "noticeDate")),
            "region": self.pick_str(item, ("region", "province", "city", "area", "district")),
            "source": self.pick_str(item, ("source", "type", "noticeType")),
            "link": self.pick_str(item, ("url", "link", "detailUrl", "noticeUrl")),
        }
