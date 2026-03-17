"""天眼查响应结构标准化适配器。"""

from __future__ import annotations

import re
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
    _MARKDOWN_TABLE_ROW_RE = re.compile(r"^\|\s*\*\*(?P<key>[^*]+)\*\*\s*\|\s*(?P<value>.*?)\s*\|\s*$")
    _MARKDOWN_COMPANY_HEADER_RE = re.compile(r"^##\s+\d+\.\s+(?P<name>.+?)\s*$")
    _MARKDOWN_PROFILE_HEADER_RE = re.compile(r"^#\s+🏢\s+(?P<name>.+?)\s*$")

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

    def parse_search_companies_markdown(self, payload: Any) -> list[dict[str, str]]:
        markdown = self._extract_markdown_result(payload)
        if not markdown or "企业搜索结果" not in markdown:
            return []

        results: list[dict[str, str]] = []
        current: dict[str, str] | None = None

        for raw_line in markdown.splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue

            header_match = self._MARKDOWN_COMPANY_HEADER_RE.match(line)
            if header_match:
                if current and (current.get("company_id") or current.get("company_name")):
                    results.append(current)
                current = {
                    "company_id": "",
                    "company_name": self._clean_markdown_value(header_match.group("name")),
                    "legal_person": "",
                    "status": "",
                    "establish_date": "",
                    "registered_capital": "",
                    "phone": "",
                }
                continue

            if current is None:
                continue

            row_match = self._MARKDOWN_TABLE_ROW_RE.match(line)
            if not row_match:
                continue
            key = self._clean_markdown_value(row_match.group("key"))
            value = self._clean_markdown_value(row_match.group("value"))
            if not value:
                continue

            if "企业ID" in key:
                current["company_id"] = value
            elif "法定代表人" in key:
                current["legal_person"] = value
            elif "经营状态" in key:
                current["status"] = value
            elif "成立时间" in key or "成立日期" in key:
                current["establish_date"] = value
            elif "注册资本" in key:
                current["registered_capital"] = value
            elif "联系电话" in key:
                current["phone"] = value

        if current and (current.get("company_id") or current.get("company_name")):
            results.append(current)
        return results

    def parse_company_profile_markdown(self, payload: Any) -> dict[str, str]:
        markdown = self._extract_markdown_result(payload)
        if not markdown:
            return {}

        profile = {
            "company_id": "",
            "company_name": "",
            "unified_social_credit_code": "",
            "legal_person": "",
            "status": "",
            "establish_date": "",
            "registered_capital": "",
            "address": "",
            "business_scope": "",
            "phone": "",
        }

        for raw_line in markdown.splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue

            header_match = self._MARKDOWN_PROFILE_HEADER_RE.match(line)
            if header_match and not profile["company_name"]:
                profile["company_name"] = self._clean_markdown_value(header_match.group("name"))
                continue

            row_match = self._MARKDOWN_TABLE_ROW_RE.match(line)
            if not row_match:
                continue
            key = self._clean_markdown_value(row_match.group("key"))
            value = self._clean_markdown_value(row_match.group("value"))
            if not value:
                continue

            if key == "企业ID":
                profile["company_id"] = value
            elif key == "法定代表人":
                profile["legal_person"] = value
            elif key == "经营状态":
                profile["status"] = value
            elif key in ("成立日期", "成立时间"):
                profile["establish_date"] = value
            elif key == "注册资本":
                profile["registered_capital"] = value
            elif key == "统一社会信用代码":
                profile["unified_social_credit_code"] = value
            elif key == "注册地址":
                profile["address"] = value
            elif key == "联系电话":
                profile["phone"] = value

        scope_match = re.search(
            r"##\s*📄\s*经营范围\s*\n(?P<scope>.*?)(?:\n\*\*关于企业更多信息|$)",
            markdown,
            re.DOTALL,
        )
        if scope_match:
            scope = self._clean_markdown_value(scope_match.group("scope"))
            profile["business_scope"] = scope

        has_meaningful_fields = any(
            profile.get(field) for field in ("company_name", "unified_social_credit_code", "legal_person", "address")
        )
        return profile if has_meaningful_fields else {}

    def _extract_markdown_result(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("result", "text", "message"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    @staticmethod
    def _clean_markdown_value(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.replace("**", "").replace("`", "")
        text = text.replace("\t", " ").replace("\r", " ").strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def normalize_company_summary(self, item: dict[str, Any]) -> dict[str, str]:
        return {
            "company_id": self.pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")),
            "company_name": self.pick_str(item, ("company_name", "companyName", "name", "company")),
            "legal_person": self.pick_str(item, ("legalPersonName", "legal_person", "legalRepresentative")),
            "status": self.pick_str(item, ("regStatus", "status", "operatingStatus")),
            "establish_date": self.pick_str(item, ("estiblishTime", "establishDate", "foundedDate")),
            "registered_capital": self.pick_str(item, ("regCapital", "registeredCapital", "capital")),
            "phone": self.pick_str(item, ("phone", "phoneNumber", "contactPhone", "tel", "联系电话")),
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
            "phone": self.pick_str(item, ("phone", "phoneNumber", "contactPhone", "tel", "联系电话")),
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
