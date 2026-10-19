"""build_sync_payload（OA 案件详情 → 新建合同表单回填 JSON）纯函数单测。

覆盖：全量字段整形、合同类型「案件类别优先 / 业务种类兜底」口径、收案日期多格式
归一为 ISO、case_info 缺失时的降级、名单去重保序与空名丢弃、keyid 规范化与详情 URL。
"""

from __future__ import annotations

import pytest

from apps.contracts.services.contract.integrations.oa_project_sync_service import build_sync_payload
from apps.oa_filing.services.oa_data_models import OACaseCustomerData, OACaseData, OACaseInfoData, OAConflictData

_GUID = "b0219b56-3968-48a8-8e12-3ca86bf160ce"
_DETAIL_URL = f"https://ims.jtn.com/project/projectView.aspx?keyid={_GUID}&FirstModel=PROJECT&SecondModel=PROJECT002"


def _info(**overrides: object) -> OACaseInfoData:
    base: dict[str, object] = {
        "case_no": "CASE-2026-0001",
        "case_name": "甲公司诉乙某合同纠纷案",
        "case_stage": "一审",
        "acceptance_date": "2026/10/19",
        "case_category": "民商事",
        "case_type": "合同纠纷",
        "responsible_lawyer": "测试律师",
        "client_side": "原告",
    }
    base.update(overrides)
    return OACaseInfoData(**base)  # type: ignore[arg-type]


def _data(info: OACaseInfoData | None = None, **overrides: object) -> OACaseData:
    base: dict[str, object] = {
        "case_no": "",
        "keyid": _GUID,
        "customers": [
            OACaseCustomerData(name="甲公司", customer_type="legal"),
            OACaseCustomerData(name="丙某", customer_type="natural"),
        ],
        "case_info": info if info is not None else _info(),
        "conflicts": [OAConflictData(name="乙某", conflict_type="被告")],
    }
    base.update(overrides)
    return OACaseData(**base)  # type: ignore[arg-type]


class TestBuildSyncPayloadFullDetail:
    def test_maps_all_form_fields(self):
        payload = build_sync_payload(_data())

        assert payload["guid"] == _GUID
        assert payload["detail_url"] == _DETAIL_URL
        assert payload["case_number"] == "CASE-2026-0001"
        assert payload["name"] == "甲公司诉乙某合同纠纷案"
        assert payload["case_type"] == "civil"
        assert payload["start_date"] == "2026-10-19"
        assert payload["case_stage"] == "一审"
        assert payload["representation_stages"] == ["first_trial"]
        assert payload["client_side"] == "原告"
        assert payload["responsible_lawyer"] == "测试律师"
        # 夹具未给收费信息：OA 没有的字段一律空，前端跳过不填
        assert payload["fee_mode"] is None
        assert payload["fixed_amount"] is None
        assert payload["custom_terms"] == ""
        assert payload["fee_currency"] == ""
        assert payload["clients"] == [
            {"name": "甲公司", "customer_type": "legal"},
            {"name": "丙某", "customer_type": "natural"},
        ]
        assert payload["opponents"] == [{"name": "乙某", "conflict_type": "被告"}]

    def test_keyid_normalized_lowercase_in_guid_and_url(self):
        payload = build_sync_payload(_data(keyid=f"  {_GUID.upper()} "))
        assert payload["guid"] == _GUID
        assert payload["detail_url"] == _DETAIL_URL

    def test_case_number_falls_back_to_top_level_case_no(self):
        """详情页没解析到「案件编号」时用调用方传入的顶层 case_no。"""
        payload = build_sync_payload(_data(_info(case_no=""), case_no="FALLBACK-01"))
        assert payload["case_number"] == "FALLBACK-01"


class TestCaseTypeResolution:
    @pytest.mark.parametrize(
        ("category", "business_type", "expected"),
        [
            ("民商事", "合同纠纷", "civil"),
            ("01", "合同纠纷", "advisor"),  # 案件类别优先于业务种类
            ("", "劳动争议仲裁", "labor"),  # 类别空则业务种类兜底
            (None, "刑事辩护", "criminal"),
            ("专项法律服务", None, "special"),
            ("未知类别", "未知种类", None),  # 两者都映射不到 → None，前端不动已有值
            ("", "", None),
        ],
    )
    def test_category_first_then_business_type(self, category, business_type, expected):
        payload = build_sync_payload(_data(_info(case_category=category, case_type=business_type)))
        assert payload["case_type"] == expected
        # 必须是纯 str（map_oa_case_type_from_text 返回的是 CaseType 枚举成员），保证 JSON 稳定输出 value
        assert payload["case_type"] is None or type(payload["case_type"]) is str


class TestStartDateNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026/10/19", "2026-10-19"),
            ("2026-10-19", "2026-10-19"),
            ("2026年10月19日", "2026-10-19"),
            ("10/19/2026", "2026-10-19"),
            ("2026/10/19 09:30:00", "2026-10-19"),  # 带时间部分只取日期
            ("19日", None),
            ("", None),
            (None, None),
        ],
    )
    def test_iso_or_none(self, raw, expected):
        payload = build_sync_payload(_data(_info(acceptance_date=raw)))
        assert payload["start_date"] == expected


class TestDegradedInputs:
    def test_missing_case_info_keeps_lists_and_blanks_scalars(self):
        payload = build_sync_payload(_data(case_no="TOP-01", case_info=None))

        assert payload["name"] == ""
        assert payload["case_type"] is None
        assert payload["start_date"] is None
        assert payload["case_stage"] == ""
        assert payload["responsible_lawyer"] == ""
        assert payload["case_number"] == "TOP-01"
        assert [c["name"] for c in payload["clients"]] == ["甲公司", "丙某"]
        assert [c["name"] for c in payload["opponents"]] == ["乙某"]

    def test_dedupes_names_keeps_order_and_drops_blank(self):
        customers = [
            OACaseCustomerData(name="甲公司", customer_type="legal"),
            OACaseCustomerData(name="  ", customer_type="legal"),
            OACaseCustomerData(name="乙某", customer_type="natural"),
            OACaseCustomerData(name="甲公司", customer_type="legal"),
        ]
        conflicts = [
            OAConflictData(name="丁公司", conflict_type="被告"),
            OAConflictData(name="丁公司", conflict_type="第三人"),
            OAConflictData(name="", conflict_type=None),
        ]
        payload = build_sync_payload(_data(customers=customers, conflicts=conflicts))

        assert [c["name"] for c in payload["clients"]] == ["甲公司", "乙某"]
        assert payload["opponents"] == [{"name": "丁公司", "conflict_type": "被告"}]

    def test_empty_keyid_gives_empty_url(self):
        payload = build_sync_payload(_data(keyid=""))
        assert payload["guid"] == ""
        assert payload["detail_url"] == ""


class TestFeeMapping:
    @pytest.mark.parametrize(
        ("raw", "expected_mode", "expect_custom_terms"),
        [
            ("定额收费", "FIXED", False),  # 真实 OA 值样本
            ("固定收费", "FIXED", False),
            ("包干收费", "FIXED", False),
            ("半风险收费", "SEMI_RISK", False),  # 「半风险」须先于泛「风险」
            ("风险代理", "FULL_RISK", False),
            ("全风险收费", "FULL_RISK", False),
            ("计时收费", "CUSTOM", True),  # 无命中归 CUSTOM 并把原文放进自定义条款
            ("", None, False),
            (None, None, False),
        ],
    )
    def test_fee_mode_rules(self, raw, expected_mode, expect_custom_terms):
        payload = build_sync_payload(_data(_info(fee_mode_text=raw)))
        assert payload["fee_mode"] == expected_mode
        assert payload["fee_mode"] is None or type(payload["fee_mode"]) is str
        if expect_custom_terms:
            assert payload["custom_terms"] == f"OA 收费方式：{raw}"
        else:
            assert payload["custom_terms"] == ""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("5000.00", "5000.00"),
            ("5,000", "5000.00"),
            ("￥12,345.5", "12345.50"),
            ("0.00", None),  # OA 未填默认 0.00 → 不填
            ("0", None),
            ("abc", None),
            ("", None),
            (None, None),
        ],
    )
    def test_amount_normalized_to_two_decimals_or_none(self, raw, expected):
        payload = build_sync_payload(_data(_info(fee_amount_text=raw)))
        assert payload["fixed_amount"] == expected

    def test_fee_waived_flag_appends_custom_terms(self):
        payload = build_sync_payload(_data(_info(fee_mode_text="定额收费", fee_waived="是")))
        assert payload["fee_mode"] == "FIXED"
        assert payload["custom_terms"] == "OA 标记：免费或减免代理"

    def test_custom_mode_and_waived_join_fragments(self):
        payload = build_sync_payload(_data(_info(fee_mode_text="计时收费", fee_waived="是")))
        assert payload["custom_terms"] == "OA 收费方式：计时收费；OA 标记：免费或减免代理"

    def test_currency_passthrough(self):
        payload = build_sync_payload(_data(_info(fee_currency="人民币")))
        assert payload["fee_currency"] == "人民币"


class TestRepresentationStages:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("行政复议", ["administrative_review"]),  # 真实 OA 值样本
            ("一审", ["first_trial"]),
            ("二审", ["second_trial"]),
            ("重审一审", ["retrial_first"]),  # 最长 label 优先，不被「一审」抢先
            ("一审程序", ["first_trial"]),  # 包含匹配
            ("劳动仲裁", ["labor_arbitration"]),
            ("执行阶段", ["enforcement"]),
            ("未知阶段", []),  # 对不上本地枚举 → 空列表不填
            ("", []),
            (None, []),
        ],
    )
    def test_stage_text_to_case_stage_values(self, raw, expected):
        payload = build_sync_payload(_data(_info(case_stage=raw)))
        assert payload["representation_stages"] == expected

    def test_missing_case_info_gives_empty_stages_and_fee(self):
        payload = build_sync_payload(_data(case_info=None))
        assert payload["representation_stages"] == []
        assert payload["fee_mode"] is None
        assert payload["fixed_amount"] is None
        assert payload["custom_terms"] == ""
