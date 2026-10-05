"""party/principal_info_service.py 补覆盖测试。

纯逻辑占位符服务：委托人名称、委托人信息（自然人/法人区分、中文序号）、
客户详情格式化异常兜底。全部用 SimpleNamespace 替身，不触碰数据库。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.documents.services.placeholders.party.principal_info_service import PrincipalInfoService


def _natural_client(name: str = "张三") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        client_type="natural",
        id_number="110101199001011234",
        address="北京市朝阳区",
        phone="13800000000",
        legal_representative="",
        id=1,
    )


def _legal_client(name: str = "某某公司") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        client_type="enterprise",
        id_number="91110000MA01A1B2C3",
        address="北京市海淀区",
        phone="010-88886666",
        legal_representative="李四",
        id=2,
    )


def _contract_with(principals: list) -> SimpleNamespace:
    parties = [SimpleNamespace(role="PRINCIPAL", client=c) for c in principals]
    parties.append(SimpleNamespace(role="OPPOSING", client=_natural_client("对方")))
    return SimpleNamespace(id=1, contract_parties=SimpleNamespace(all=lambda: parties))


class TestGenerate:
    def test_no_contract_returns_empty(self):
        assert PrincipalInfoService().generate({}) == {}

    def test_with_contract_sets_all_keys(self):
        svc = PrincipalInfoService()
        result = svc.generate({"contract": _contract_with([_natural_client("张三")])})
        assert result["委托人名称"] == "张三"
        assert "甲方：张三" in result["委托人信息"]
        assert result["委托人数量"] == 1

    def test_fetch_error_propagates(self):
        def _raise():
            raise RuntimeError("db error")

        contract = SimpleNamespace(id=1, contract_parties=SimpleNamespace(all=_raise))
        with pytest.raises(RuntimeError, match="db error"):
            PrincipalInfoService().generate({"contract": contract})


class TestGetPrincipals:
    def test_filters_principal_role_only(self):
        svc = PrincipalInfoService()
        client = _natural_client("张三")
        principals = svc._get_principals(_contract_with([client]))
        assert principals == [client]


class TestFormatPrincipalNames:
    def test_empty_returns_empty(self):
        assert PrincipalInfoService().format_principal_names([]) == ""

    def test_joins_with_dunhao(self):
        svc = PrincipalInfoService()
        result = svc.format_principal_names([_natural_client("张三"), _legal_client("某某公司")])
        assert result == "张三、某某公司"

    def test_skips_clients_without_name(self):
        svc = PrincipalInfoService()
        result = svc.format_principal_names([_natural_client(""), _natural_client("李四")])
        assert result == "李四"


class TestFormatPrincipalInfo:
    def test_empty_returns_empty(self):
        assert PrincipalInfoService().format_principal_info([]) == ""

    def test_single_natural_person(self):
        svc = PrincipalInfoService()
        info = svc.format_principal_info([_natural_client("张三")])
        lines = info.split("\n")
        assert lines[0] == "甲方：张三"
        assert "身份证号码：110101199001011234" in lines
        assert "地址：北京市朝阳区" in lines
        assert "电话：13800000000" in lines
        assert "统一社会信用代码" not in info

    def test_single_legal_entity(self):
        svc = PrincipalInfoService()
        info = svc.format_principal_info([_legal_client()])
        assert "甲方：某某公司" in info
        assert "统一社会信用代码：91110000MA01A1B2C3" in info
        assert "法定代表人：李四" in info

    def test_multiple_principals_use_chinese_numbers(self):
        svc = PrincipalInfoService()
        info = svc.format_principal_info([_natural_client("张三"), _natural_client("李四")])
        assert "甲方一：张三" in info
        assert "甲方二：李四" in info
        assert "\n\n" in info  # 空行分隔

    def test_more_than_ten_principals_falls_back_to_arabic(self):
        svc = PrincipalInfoService()
        clients = [_natural_client(f"委托人{i}") for i in range(11)]
        info = svc.format_principal_info(clients)
        assert "甲方十：委托人9" in info
        assert "甲方11：委托人10" in info


class TestFormatClientDetails:
    def test_natural_person_uses_id_number(self):
        lines = PrincipalInfoService()._format_client_details(_natural_client())
        assert "身份证号码：110101199001011234" in lines
        assert "统一社会信用代码" not in "\n".join(lines)

    def test_legal_entity_uses_uscc_and_representative(self):
        lines = PrincipalInfoService()._format_client_details(_legal_client())
        assert "统一社会信用代码：91110000MA01A1B2C3" in lines
        assert "法定代表人：李四" in lines

    def test_none_client_type_only_basic_lines(self):
        client = SimpleNamespace(client_type=None, id_number="X", address="地址A", phone="电话B")
        lines = PrincipalInfoService()._format_client_details(client)
        assert lines == ["地址：地址A", "电话：电话B"]

    def test_missing_attributes_coerced_to_empty(self):
        client = SimpleNamespace(client_type="natural")
        lines = PrincipalInfoService()._format_client_details(client)
        assert "身份证号码：" in lines[0]
        assert lines[1] == "地址："
        assert lines[2] == "电话："

    def test_exception_falls_back_to_basic_format(self):
        class Boom:
            @property
            def client_type(self):
                raise RuntimeError("broken")

        client = Boom()
        lines = PrincipalInfoService()._format_client_details(client)
        assert lines == ["地址：", "电话："]


class TestServiceMetadata:
    def test_placeholder_keys(self):
        assert PrincipalInfoService.placeholder_keys == ["委托人名称", "委托人信息", "委托人数量"]
        assert PrincipalInfoService.name == "principal_info_service"
        assert PrincipalInfoService.category == "party"
