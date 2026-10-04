"""supplementary/signature_service.py 补覆盖测试。

补充协议签名盖章占位符：仅当存在补充协议时生成、自然人/法人签名格式、
指定日期回退今天、wiring 获取客户服务异常时的法人兜底。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.documents.services.placeholders.supplementary.signature_service import SupplementaryAgreementSignatureService

WIRING = "apps.documents.services.infrastructure.wiring"


def _client(name: str, client_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(name=name, id=client_id)


def _agreement_with(principals: list) -> MagicMock:
    parties = [SimpleNamespace(role="PRINCIPAL", client=c) for c in principals]
    parties.append(SimpleNamespace(role="OPPOSING", client=_client("对方", 99)))
    agreement = MagicMock()
    agreement.parties.all.return_value = parties
    return agreement


def _contract(specified_date: date | None = date(2026, 3, 5)) -> SimpleNamespace:
    return SimpleNamespace(id=1, specified_date=specified_date)


def _patch_client_service(natural_ids: set[int]):
    service = MagicMock()
    service.is_natural_person_internal.side_effect = lambda client_id: client_id in natural_ids
    return patch(f"{WIRING}.get_client_service", return_value=service)


class TestGenerate:
    def test_no_context_objects_returns_empty(self):
        svc = SupplementaryAgreementSignatureService()
        assert svc.generate({}) == {}
        assert svc.generate({"contract": _contract()}) == {}
        assert svc.generate({"supplementary_agreement": _agreement_with([])}) == {}

    def test_generates_only_with_both_contract_and_agreement(self):
        svc = SupplementaryAgreementSignatureService()
        with _patch_client_service({1}):
            result = svc.generate(
                {"contract": _contract(), "supplementary_agreement": _agreement_with([_client("张三", 1)])}
            )
        assert "补充协议委托人签名盖章信息" in result
        assert "甲方（签名+指模）：张三" in result["补充协议委托人签名盖章信息"]
        assert "2026年03月05日" in result["补充协议委托人签名盖章信息"]

    def test_specified_date_none_falls_back_to_today(self):
        svc = SupplementaryAgreementSignatureService()
        with (
            _patch_client_service({1}),
            patch("apps.documents.services.placeholders.supplementary.signature_service.date") as mock_date,
        ):
            mock_date.today.return_value = date(2026, 10, 1)
            result = svc.generate(
                {
                    "contract": _contract(specified_date=None),
                    "supplementary_agreement": _agreement_with([_client("张三", 1)]),
                }
            )
        assert "2026年10月01日" in result["补充协议委托人签名盖章信息"]


class TestGetAgreementPrincipals:
    def test_filters_principal_role(self):
        svc = SupplementaryAgreementSignatureService()
        principals = svc._get_agreement_principals(_agreement_with([_client("张三", 1), _client("李四", 2)]))
        assert [c.name for c in principals] == ["张三", "李四"]


class TestFormatSignatureInfo:
    def test_empty_returns_empty(self):
        assert SupplementaryAgreementSignatureService().format_signature_info([], date(2026, 1, 1)) == ""

    def test_single_natural_person(self):
        svc = SupplementaryAgreementSignatureService()
        with _patch_client_service({1}):
            result = svc.format_signature_info([_client("张三", 1)], date(2026, 1, 2))
        assert result == "甲方（签名+指模）：张三\n2026年01月02日"

    def test_single_legal_entity_has_representative_line(self):
        svc = SupplementaryAgreementSignatureService()
        with _patch_client_service(set()):
            result = svc.format_signature_info([_client("某某公司", 1)], date(2026, 1, 2))
        assert result == "甲方（盖章）：某某公司\n代表:\n2026年01月02日"

    def test_multiple_principals_mixed(self):
        svc = SupplementaryAgreementSignatureService()
        with _patch_client_service({1}):
            result = svc.format_signature_info([_client("张三", 1), _client("某某公司", 2)], date(2026, 1, 2))
        blocks = result.split("\n\n")
        assert blocks[0] == "甲方一（签名+指模）：张三\n2026年01月02日"
        assert blocks[1] == "甲方二（盖章）：某某公司\n代表:\n2026年01月02日"

    def test_more_than_ten_principals_falls_back_to_arabic(self):
        svc = SupplementaryAgreementSignatureService()
        clients = [_client(f"委托人{i}", i + 1) for i in range(11)]
        with _patch_client_service(set(range(1, 12))):
            result = svc.format_signature_info(clients, date(2026, 1, 2))
        assert "甲方十（签名+指模）：委托人9" in result
        assert "甲方11（签名+指模）：委托人10" in result


class TestIsNaturalPerson:
    def test_delegates_to_client_service(self):
        svc = SupplementaryAgreementSignatureService()
        with _patch_client_service({7}):
            assert svc._is_natural_person(_client("甲", 7)) is True
            assert svc._is_natural_person(_client("乙", 8)) is False

    def test_service_error_defaults_to_legal_entity(self):
        svc = SupplementaryAgreementSignatureService()
        with patch(f"{WIRING}.get_client_service", side_effect=RuntimeError("wiring down")):
            assert svc._is_natural_person(_client("甲", 1)) is False


class TestGetSignatureFormat:
    def test_natural_and_legal_formats(self):
        svc = SupplementaryAgreementSignatureService()
        with _patch_client_service({1}):
            assert svc._get_signature_format(_client("甲", 1)) == "（签名+指模）"
            assert svc._get_signature_format(_client("乙", 2)) == "（盖章）"


class TestFormatDate:
    def test_pads_month_and_day(self):
        svc = SupplementaryAgreementSignatureService()
        assert svc._format_date(date(2026, 1, 9)) == "2026年01月09日"
        assert svc._format_date(date(2026, 12, 31)) == "2026年12月31日"


class TestServiceMetadata:
    def test_placeholder_keys(self):
        assert SupplementaryAgreementSignatureService.placeholder_keys == ["补充协议委托人签名盖章信息"]
        assert SupplementaryAgreementSignatureService.category == "supplementary_agreement"
