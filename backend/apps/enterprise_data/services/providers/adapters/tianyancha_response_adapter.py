"""天眼查响应结构标准化适配器。"""

from __future__ import annotations

from typing import Any


class TianyanchaResponseAdapter:
    _ITEM_KEYS = (
        "items",
        "list",
        "rows",
        "records",
        "companies",
        "data",
        "result",
    )

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
            "company_id": self.pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")),
            "company_name": self.pick_str(item, ("company_name", "companyName", "name", "company")),
            "legal_person": self.pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative")),
            "status": self.pick_str(item, ("regStatus", "status", "operatingStatus")),
            "establish_date": self.pick_str(item, ("estiblishTime", "establishDate", "foundedDate")),
            "registered_capital": self.pick_str(item, ("regCapital", "registeredCapital", "capital")),
        }

    def normalize_company_profile(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "company_id": self.pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")),
            "company_name": self.pick_str(item, ("company_name", "companyName", "name", "company")),
            "unified_social_credit_code": self.pick_str(
                item,
                ("creditCode", "unifiedSocialCreditCode", "socialCreditCode", "unified_social_credit_code"),
            ),
            "legal_person": self.pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative")),
            "status": self.pick_str(item, ("regStatus", "status", "operatingStatus")),
            "establish_date": self.pick_str(item, ("estiblishTime", "establishDate", "foundedDate")),
            "registered_capital": self.pick_str(item, ("regCapital", "registeredCapital", "capital")),
            "address": self.pick_str(item, ("regLocation", "address", "registeredAddress")),
            "business_scope": self.pick_str(item, ("businessScope", "scope")),
        }

    def normalize_risk_item(self, item: dict[str, Any], *, fallback_risk_type: str) -> dict[str, str]:
        return {
            "risk_type": self.pick_str(item, ("riskType", "type")) or fallback_risk_type,
            "title": self.pick_str(item, ("title", "riskTitle", "event", "name")),
            "level": self.pick_str(item, ("level", "riskLevel", "degree")),
            "amount": self.pick_str(item, ("amount", "amountStr", "money")),
            "publish_date": self.pick_str(item, ("date", "publishDate", "eventTime", "filingDate")),
            "source": self.pick_str(item, ("source", "court", "channel")),
        }

    def normalize_shareholder_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "name": self.pick_str(item, ("name", "shareholderName", "holderName")),
            "amount": self.pick_str(item, ("subConAm", "capital", "amount", "contribution")),
            "ratio": self.pick_str(item, ("holdRatio", "ratio", "sharePercent")),
            "contribution_date": self.pick_str(item, ("conDate", "date", "subscribeDate")),
            "source": self.pick_str(item, ("source", "type")),
        }

    def normalize_personnel_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "hcgid": self.pick_str(item, ("hcgid", "id", "personCompanyId")),
            "name": self.pick_str(item, ("name", "personName")),
            "position": self.pick_str(item, ("position", "jobTitle", "post")),
            "education": self.pick_str(item, ("education", "academicDegree")),
            "source": self.pick_str(item, ("source", "type")),
        }

    def normalize_person_profile(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "hcgid": self.pick_str(item, ("hcgid", "id", "personCompanyId")),
            "name": self.pick_str(item, ("name", "personName")),
            "position": self.pick_str(item, ("position", "jobTitle", "post")),
            "intro": self.pick_str(item, ("intro", "introduction", "profile")),
            "resume": self.pick_str(item, ("resume", "experience", "workExperience")),
        }

    def normalize_bidding_item(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "title": self.pick_str(item, ("title", "announceTitle", "name")),
            "project_name": self.pick_str(item, ("projectName", "project", "bidName")),
            "role": self.pick_str(item, ("role", "identity", "bidRole")),
            "amount": self.pick_str(item, ("amount", "amountStr", "money")),
            "date": self.pick_str(item, ("date", "publishDate", "bidDate", "winningDate")),
            "region": self.pick_str(item, ("region", "province", "city", "area")),
            "source": self.pick_str(item, ("source", "type", "noticeType")),
            "link": self.pick_str(item, ("url", "link", "detailUrl")),
        }
