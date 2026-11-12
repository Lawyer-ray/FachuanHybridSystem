"""当事人数据归一化与 case number 解析。"""

from __future__ import annotations

import re
from typing import Any


class GuaranteeDataMixin:
    """当事人数据归一化与 case number 解析。"""

    def _normalize_party_type(self, raw_party_type: Any) -> str:
        value = str(raw_party_type or "").strip().lower()
        if value in {"natural", "person", "individual"}:
            return "natural"
        if value in {"legal", "corp", "company", "enterprise", "organization", "org"}:
            return "legal"
        if value in {"non_legal_org", "nonlegal", "non_legal", "other_org"}:
            return "non_legal_org"
        return "natural"

    def _build_party_dialog_defaults(
        self,
        party: dict[str, Any],
        *,
        is_property_clue: bool = False,
        property_clue_data: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        # 缺姓名/证件号/地址一律留空，不填占位值；
        # 空值由法院表单自身的必填校验暴露（errors_after_next），由人工补全后重跑。
        name = str(party.get("name") or "").strip()
        party_type = self._normalize_party_type(party.get("party_type") or "natural")

        id_number = str(party.get("id_number") or "").strip()
        address = str(party.get("address") or "").strip()

        legal_representative = str(party.get("legal_representative") or "").strip()
        legal_representative_id_number = str(party.get("legal_representative_id_number") or "").strip()

        defaults = {
            "party_type": party_type,
            "name": name,
            "unit_name": name,
            "owner_name": name,
            "id_number": id_number,
            "license_number": id_number,
            "phone": str(party.get("phone") or "").strip(),
            "telephone_area_code": "",
            "telephone_number": "",
            "telephone_extension": "",
            "birth_date": str(party.get("birth_date") or "").strip(),
            "age": str(party.get("age") or "").strip(),
            "gender": str(party.get("gender") or "").strip(),
            "address": address,
            "unit_address": address,
            "legal_representative": legal_representative,
            "legal_representative_id_number": legal_representative_id_number,
            "principal": legal_representative,
            "unit_nature": "企业",
            "property_type": "其他",
            "property_info": "",
            "property_location": "",
            "property_province": "",
            "property_cert_no": "",
            "property_value": "",
        }
        if is_property_clue:
            clue_data = property_clue_data or {}
            defaults["party_type"] = "property"
            defaults["owner_name"] = str(clue_data.get("owner_name") or name).strip() or name
            defaults["property_type"] = str(clue_data.get("property_type") or "其他").strip() or "其他"
            defaults["property_info"] = (
                str(clue_data.get("property_info") or "").strip() or f"{defaults['owner_name']}名下财产线索"
            )
            defaults["property_location"] = str(
                clue_data.get("property_location") or defaults.get("address") or ""
            ).strip()
            defaults["property_province"] = str(clue_data.get("property_province") or "").strip()
            defaults["property_cert_no"] = str(clue_data.get("property_cert_no") or "").strip()
            defaults["property_value"] = str(clue_data.get("property_value") or "").strip() or "300000"
        return defaults

    def _build_agent_dialog_defaults(self, source: dict[str, Any]) -> dict[str, str]:
        name = str(source.get("name") or "").strip()
        id_number = str(source.get("id_number") or "").strip()
        phone = str(source.get("phone") or "").strip()
        return {
            "party_type": "agent",
            "name": name,
            "id_number": id_number,
            "phone": phone,
            "telephone_area_code": "",
            "telephone_number": "",
            "telephone_extension": "",
            "law_firm": str(source.get("law_firm") or "").strip(),
            "license_number": str(source.get("license_number") or "").strip(),
            "agent_type": "执业律师",
            "principal_party_name": str(source.get("name") or "").strip() or name,
            "gender": str(source.get("gender") or "").strip(),
        }


# ↓↓ 由 GuaranteeDataMixin 下沉的模块级纯函数（四层架构静态方法棘轮）
def parse_case_number(number: str) -> tuple[str, str, str, str]:
    cleaned = str(number or "").replace("（", "(").replace("）", ")").replace("号", "").strip()
    match = re.search(r"\((\d{4})\)([^\d\s]+\d+)\s*([^\d\s]+)\s*(\d+)", cleaned)
    if not match:
        return "", "", "", ""
    return match.group(1), match.group(2), match.group(3), match.group(4)
