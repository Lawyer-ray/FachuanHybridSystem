"""guarantee data_mixin 单元测试 — 当事人数据归一化与案号解析。"""

from __future__ import annotations

from typing import Any

from apps.automation.services.scraper.sites.guarantee.data_mixin import GuaranteeDataMixin, parse_case_number


class _Svc(GuaranteeDataMixin):
    pass


def _svc() -> _Svc:
    return _Svc()


class TestNormalizePartyType:
    def test_natural_aliases(self) -> None:
        svc = _svc()
        for raw in ("natural", "person", "individual", " Natural "):
            assert svc._normalize_party_type(raw) == "natural"

    def test_legal_aliases(self) -> None:
        svc = _svc()
        for raw in ("legal", "corp", "company", "enterprise", "organization", "org", "LEGAL"):
            assert svc._normalize_party_type(raw) == "legal"

    def test_non_legal_org_aliases(self) -> None:
        svc = _svc()
        for raw in ("non_legal_org", "nonlegal", "non_legal", "other_org"):
            assert svc._normalize_party_type(raw) == "non_legal_org"

    def test_whitespace_and_case_normalized(self) -> None:
        assert _svc()._normalize_party_type("  LEGAL  ") == "legal"

    def test_unknown_defaults_to_natural(self) -> None:
        svc = _svc()
        assert svc._normalize_party_type("alien") == "natural"
        assert svc._normalize_party_type(None) == "natural"
        assert svc._normalize_party_type("") == "natural"


class TestBuildPartyDialogDefaults:
    def test_natural_without_id_number_leaves_id_empty(self) -> None:
        defaults = _svc()._build_party_dialog_defaults(
            {"name": "张三", "party_type": "natural", "phone": "13800000000"}
        )
        assert defaults["party_type"] == "natural"
        assert defaults["name"] == "张三"
        assert defaults["id_number"] == ""
        assert defaults["license_number"] == ""
        assert defaults["phone"] == "13800000000"
        assert defaults["gender"] == ""

    def test_empty_party_leaves_identity_fields_empty(self) -> None:
        defaults = _svc()._build_party_dialog_defaults({})
        assert defaults["party_type"] == "natural"
        assert defaults["name"] == ""
        assert defaults["id_number"] == ""
        assert defaults["license_number"] == ""
        assert defaults["legal_representative"] == ""
        assert defaults["legal_representative_id_number"] == ""
        assert defaults["address"] == ""
        assert defaults["unit_address"] == ""
        assert defaults["gender"] == ""
        assert defaults["birth_date"] == ""
        assert defaults["age"] == ""

    def test_provided_personal_fields_kept(self) -> None:
        defaults = _svc()._build_party_dialog_defaults(
            {
                "name": "李四",
                "id_number": "ID123",
                "address": "广州市天河区某路1号",
                "gender": "女性",
                "birth_date": "1985-06-01",
                "age": "40",
            }
        )
        assert defaults["address"] == "广州市天河区某路1号"
        assert defaults["unit_address"] == "广州市天河区某路1号"
        assert defaults["gender"] == "女性"
        assert defaults["birth_date"] == "1985-06-01"
        assert defaults["age"] == "40"

    def test_legal_party_without_id_number_leaves_license_empty(self) -> None:
        defaults = _svc()._build_party_dialog_defaults({"name": "某公司", "party_type": "legal"})
        assert defaults["party_type"] == "legal"
        assert defaults["unit_name"] == "某公司"
        assert defaults["id_number"] == ""
        assert defaults["license_number"] == ""
        assert defaults["unit_nature"] == "企业"

    def test_provided_legal_representative_fields_kept(self) -> None:
        defaults = _svc()._build_party_dialog_defaults(
            {
                "name": "某公司",
                "party_type": "legal",
                "id_number": "91440101MA5TEST0X",
                "legal_representative": "王五",
                "legal_representative_id_number": "440102199001010000",
            }
        )
        assert defaults["id_number"] == "91440101MA5TEST0X"
        assert defaults["license_number"] == "91440101MA5TEST0X"
        assert defaults["legal_representative"] == "王五"
        assert defaults["legal_representative_id_number"] == "440102199001010000"
        assert defaults["principal"] == "王五"

    def test_provided_id_number_wins(self) -> None:
        defaults = _svc()._build_party_dialog_defaults({"name": "李四", "id_number": "ID123"})
        assert defaults["id_number"] == "ID123"

    def test_property_clue_overrides(self) -> None:
        clue: dict[str, Any] = {
            "owner_name": "王五",
            "property_type": "房产",
            "property_info": "天河区某房",
            "property_location": "广州市天河区",
            "property_province": "广东省",
            "property_cert_no": "粤(2026)广州市不动产权第1号",
            "property_value": "500000",
        }
        defaults = _svc()._build_party_dialog_defaults({"name": "张三"}, is_property_clue=True, property_clue_data=clue)
        assert defaults["party_type"] == "property"
        assert defaults["owner_name"] == "王五"
        assert defaults["property_type"] == "房产"
        assert defaults["property_info"] == "天河区某房"
        assert defaults["property_location"] == "广州市天河区"
        assert defaults["property_province"] == "广东省"
        assert defaults["property_cert_no"] == "粤(2026)广州市不动产权第1号"
        assert defaults["property_value"] == "500000"

    def test_property_clue_without_data_uses_fallbacks(self) -> None:
        defaults = _svc()._build_party_dialog_defaults({"name": "张三"}, is_property_clue=True, property_clue_data=None)
        assert defaults["party_type"] == "property"
        assert defaults["owner_name"] == "张三"
        assert defaults["property_type"] == "其他"
        assert "张三" in defaults["property_info"]
        assert defaults["property_value"] == "300000"


class TestBuildAgentDialogDefaults:
    def test_full_source(self) -> None:
        defaults = _svc()._build_agent_dialog_defaults(
            {
                "name": "赵律师",
                "id_number": "ID998",
                "phone": "13900000000",
                "law_firm": "某律所",
                "license_number": "LIC1",
            }
        )
        assert defaults["party_type"] == "agent"
        assert defaults["name"] == "赵律师"
        assert defaults["id_number"] == "ID998"
        assert defaults["law_firm"] == "某律所"
        assert defaults["license_number"] == "LIC1"
        assert defaults["agent_type"] == "执业律师"
        assert defaults["principal_party_name"] == "赵律师"

    def test_empty_source_leaves_identity_fields_empty(self) -> None:
        defaults = _svc()._build_agent_dialog_defaults({})
        assert defaults["name"] == ""
        assert defaults["id_number"] == ""
        assert defaults["phone"] == ""
        assert defaults["principal_party_name"] == ""


class TestParseCaseNumber:
    def test_full_width_parentheses(self) -> None:
        assert parse_case_number("（2024）粤0604民初100号") == ("2024", "粤0604", "民初", "100")

    def test_half_width_parentheses_and_hao_removed(self) -> None:
        assert parse_case_number("(2023)粤0604财保12号") == ("2023", "粤0604", "财保", "12")

    def test_spaces_between_segments_tolerated(self) -> None:
        assert parse_case_number("（2024）粤0604 民初 100 号") == ("2024", "粤0604", "民初", "100")

    def test_no_match_returns_empty_tuple(self) -> None:
        assert parse_case_number("没有案号的文本") == ("", "", "", "")
        assert parse_case_number("") == ("", "", "", "")
