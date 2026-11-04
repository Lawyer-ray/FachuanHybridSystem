"""法院一张网申请担保 API 辅助函数测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from apps.core.dto.client import PropertyClueDTO
from plugins.court_automation.guarantee import helpers


class _FakeClientService:
    def __init__(self, clues_by_client_id: dict[int, list[PropertyClueDTO]]) -> None:
        self._clues_by_client_id = clues_by_client_id

    def get_property_clues_by_client_internal(self, client_id: int) -> list[PropertyClueDTO]:
        return list(self._clues_by_client_id.get(client_id, []))


def _build_case_party(*, party_id: int, client_id: int, client_name: str, address: str = "") -> SimpleNamespace:
    client = SimpleNamespace(id=client_id, name=client_name, address=address)
    return SimpleNamespace(id=party_id, client=client)


def test_build_selected_respondent_property_clues_returns_all_clues(monkeypatch) -> None:
    client_service = _FakeClientService(
        {
            101: [
                PropertyClueDTO(
                    id=1, client_id=101, clue_type="bank", content="户名: 测试户名A\n银行账号: 6222", description=None
                ),
                PropertyClueDTO(
                    id=2, client_id=101, clue_type="wechat", content="微信号: test_wechat_123", description=None
                ),
            ],
            202: [
                PropertyClueDTO(id=3, client_id=202, clue_type="other", content="测试设备线索一批", description=None),
            ],
        }
    )
    monkeypatch.setattr(helpers, "_get_client_service", lambda: client_service)

    case_parties = [
        _build_case_party(party_id=11, client_id=101, client_name="测试企业A", address="测试地址A"),
        _build_case_party(party_id=22, client_id=202, client_name="测试企业B", address="测试地址B"),
    ]
    selected_respondents = [
        {"party_id": 11, "name": "测试企业A"},
        {"party_id": 22, "name": "测试企业B"},
    ]

    result = helpers._build_selected_respondent_property_clues(
        case_parties=case_parties,
        selected_respondents=selected_respondents,
        preserve_amount="206135.6400",
    )

    assert len(result) == 3
    assert [item["owner_name"] for item in result] == ["测试企业A", "测试企业A", "测试企业B"]
    assert [item["property_type"] for item in result] == ["其他", "其他", "其他"]
    assert result[0]["property_info"] == "银行账户：户名: 测试户名A；银行账号: 6222"
    assert result[1]["property_info"] == "微信账户：微信号: test_wechat_123"
    assert result[2]["property_info"] == "其他：测试设备线索一批"
    # 财产线索价值平均分配保全金额（commit b580df3），206135.64 // 3 = 68711（向下取整）
    assert [item["property_value"] for item in result] == ["68711", "68711", "68711"]


def test_build_selected_respondent_property_clues_falls_back_when_no_clues(monkeypatch) -> None:
    monkeypatch.setattr(helpers, "_get_client_service", lambda: _FakeClientService({}))

    case_parties = [
        _build_case_party(party_id=11, client_id=101, client_name="测试企业A", address="测试地址A"),
    ]
    selected_respondents = [{"party_id": 11, "name": "测试企业A"}]

    result = helpers._build_selected_respondent_property_clues(
        case_parties=case_parties,
        selected_respondents=selected_respondents,
        preserve_amount=500000,
    )

    assert result == [
        {
            "owner_name": "测试企业A",
            "property_type": "其他",
            "property_info": "测试企业A名下财产线索",
            "property_location": "测试地址A",
            "property_province": "",
            "property_cert_no": "",
            "property_value": "500000",
        }
    ]


def test_build_primary_respondent_property_clue_returns_first_item(monkeypatch) -> None:
    client_service = _FakeClientService(
        {
            101: [
                PropertyClueDTO(
                    id=1, client_id=101, clue_type="alipay", content="支付宝账号: test_alipay_001", description=None
                ),
                PropertyClueDTO(id=2, client_id=101, clue_type="other", content="测试车辆线索", description=None),
            ]
        }
    )
    monkeypatch.setattr(helpers, "_get_client_service", lambda: client_service)

    result = helpers._build_primary_respondent_property_clue(
        case_parties=[_build_case_party(party_id=11, client_id=101, client_name="测试企业A")],
        selected_respondents=[{"party_id": 11, "name": "测试企业A"}],
        preserve_amount=None,
    )

    assert result["owner_name"] == "测试企业A"
    assert result["property_type"] == "其他"
    assert result["property_info"] == "支付宝账户：支付宝账号: test_alipay_001"


# 案号拆分回归用例的假数据：纯格式样例（粤01/民初/100），非真实案号
_CASE_NO_FULL_WIDTH = "（2024）粤01民初100号"  # privacy-allow
_CASE_NO_HALF_WIDTH = "(2023)粤01财保12号"  # privacy-allow
_CASE_NO_SPACED = "（2024）粤01 民初 100 号"  # privacy-allow
_CASE_NO_WITH_SUFFIX = "（2024）粤01民初100号之一"  # privacy-allow


class TestParseCaseNumber:
    """案号拆分回归：API 层曾调用已下沉的 Service 静态方法导致 500，改为插件内模块级函数。"""

    def test_full_width_parentheses(self) -> None:
        assert helpers._parse_case_number(_CASE_NO_FULL_WIDTH) == ("2024", "粤01", "民初", "100")

    def test_half_width_parentheses_and_hao_removed(self) -> None:
        assert helpers._parse_case_number(_CASE_NO_HALF_WIDTH) == ("2023", "粤01", "财保", "12")

    def test_spaces_between_segments_tolerated(self) -> None:
        assert helpers._parse_case_number(_CASE_NO_SPACED) == ("2024", "粤01", "民初", "100")

    def test_seq_suffix_after_hao_is_tolerated(self) -> None:
        # 「之一」这类后缀不影响序号提取
        assert helpers._parse_case_number(_CASE_NO_WITH_SUFFIX) == ("2024", "粤01", "民初", "100")

    def test_no_match_returns_empty_tuple(self) -> None:
        assert helpers._parse_case_number("没有案号的文本") == ("", "", "", "")
        assert helpers._parse_case_number("") == ("", "", "", "")
        assert helpers._parse_case_number(None) == ("", "", "", "")

    def test_matches_apps_side_implementation(self) -> None:
        from apps.automation.services.scraper.sites.guarantee.data_mixin import parse_case_number

        for raw in (_CASE_NO_FULL_WIDTH, _CASE_NO_HALF_WIDTH, _CASE_NO_SPACED, "", "无案号"):
            assert helpers._parse_case_number(raw) == parse_case_number(raw)
