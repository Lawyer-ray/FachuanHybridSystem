"""当事人创建页企业信息预填服务。"""

from __future__ import annotations

from typing import Any

from apps.client.models import Client
from apps.core.exceptions import ValidationException
from apps.enterprise_data.services import EnterpriseDataService


class ClientEnterprisePrefillService:
    """基于 enterprise_data 的企业信息预填聚合服务。"""

    def __init__(self, *, enterprise_data_service: EnterpriseDataService | None = None) -> None:
        self._enterprise_data_service = enterprise_data_service or EnterpriseDataService()

    def search_companies(self, *, keyword: str, provider: str | None = None, limit: int = 8) -> dict[str, Any]:
        normalized_keyword = str(keyword or "").strip()
        if not normalized_keyword:
            raise ValidationException(message="keyword 不能为空", code="INVALID_KEYWORD")

        normalized_limit = max(1, min(20, int(limit or 8)))
        result = self._enterprise_data_service.search_companies(
            keyword=normalized_keyword,
            provider=provider,
            include_raw=False,
        )
        provider_name = self._pick_str(result.get("meta"), ("provider",)) or str(provider or "").strip()
        items = self._normalize_company_candidates(result.get("data"))[:normalized_limit]
        return {
            "keyword": normalized_keyword,
            "provider": provider_name,
            "items": items,
            "total": len(items),
        }

    def build_prefill(self, *, company_id: str, provider: str | None = None) -> dict[str, Any]:
        normalized_company_id = str(company_id or "").strip()
        if not normalized_company_id:
            raise ValidationException(message="company_id 不能为空", code="INVALID_COMPANY_ID")

        result = self._enterprise_data_service.get_company_profile(
            company_id=normalized_company_id,
            provider=provider,
            include_raw=False,
        )
        provider_name = self._pick_str(result.get("meta"), ("provider",)) or str(provider or "").strip()
        profile = self._normalize_company_profile(result.get("data"), fallback_company_id=normalized_company_id)
        prefill = {
            "client_type": Client.LEGAL,
            "name": profile["company_name"],
            "id_number": profile["unified_social_credit_code"],
            "legal_representative": profile["legal_person"],
            "address": profile["address"],
            "phone": "",
        }

        existing_client = self._find_existing_client_by_credit_code(prefill["id_number"])
        return {
            "provider": provider_name,
            "prefill": prefill,
            "profile": profile,
            "existing_client": existing_client,
        }

    def _normalize_company_candidates(self, payload: Any) -> list[dict[str, str]]:
        if isinstance(payload, dict):
            raw_items = payload.get("items")
        elif isinstance(payload, list):
            raw_items = payload
        else:
            raw_items = []

        if not isinstance(raw_items, list):
            return []

        items: list[dict[str, str]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized = {
                "company_id": self._pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")),
                "company_name": self._pick_str(item, ("company_name", "companyName", "name", "company")),
                "legal_person": self._pick_str(item, ("legal_person", "legalPersonName", "legalRepresentative")),
                "status": self._pick_str(item, ("status", "regStatus", "operatingStatus")),
                "establish_date": self._pick_str(item, ("establish_date", "estiblishTime", "establishDate", "foundedDate")),
                "registered_capital": self._pick_str(item, ("registered_capital", "regCapital", "registeredCapital", "capital")),
            }
            if not normalized["company_id"] and not normalized["company_name"]:
                continue
            items.append(normalized)
        return items

    def _normalize_company_profile(self, payload: Any, *, fallback_company_id: str) -> dict[str, str]:
        item = payload if isinstance(payload, dict) else {}
        profile = {
            "company_id": self._pick_str(item, ("company_id", "companyId", "id", "cid", "tycId")) or fallback_company_id,
            "company_name": self._pick_str(item, ("company_name", "companyName", "name", "company")),
            "unified_social_credit_code": self._pick_str(
                item,
                ("unified_social_credit_code", "creditCode", "unifiedSocialCreditCode", "socialCreditCode"),
            ),
            "legal_person": self._pick_str(item, ("legal_person", "legalPersonName", "legalRepresentative")),
            "status": self._pick_str(item, ("status", "regStatus", "operatingStatus")),
            "establish_date": self._pick_str(item, ("establish_date", "estiblishTime", "establishDate", "foundedDate")),
            "registered_capital": self._pick_str(item, ("registered_capital", "regCapital", "registeredCapital", "capital")),
            "address": self._pick_str(item, ("address", "regLocation", "registeredAddress")),
            "business_scope": self._pick_str(item, ("business_scope", "businessScope", "scope")),
        }
        return profile

    @staticmethod
    def _pick_str(obj: Any, keys: tuple[str, ...]) -> str:
        if not isinstance(obj, dict):
            return ""
        for key in keys:
            value = obj.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _find_existing_client_by_credit_code(credit_code: str) -> dict[str, Any] | None:
        normalized_credit_code = str(credit_code or "").strip()
        if not normalized_credit_code:
            return None
        existing = Client.objects.filter(id_number=normalized_credit_code).only("id", "name").first()
        if existing is None:
            return None
        return {"id": existing.id, "name": existing.name}
