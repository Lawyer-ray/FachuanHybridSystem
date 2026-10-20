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

    def test_customer_contact_fields_forwarded_for_auto_create(self):
        """客户 tab 解析到的证件号 / 电话 / 地址 / 法定代表人随名单带出，供本地自动建库。"""
        payload = build_sync_payload(
            _data(
                customers=[
                    OACaseCustomerData(
                        name="甲公司",
                        customer_type="legal",
                        id_number="91440000TEST000003",
                        phone="020-00000000",  # privacy-allow
                        address="某市某区",
                        legal_representative="张某某",
                    )
                ]
            )
        )
        assert payload["clients"] == [
            {
                "name": "甲公司",
                "customer_type": "legal",
                "id_number": "91440000TEST000003",
                "phone": "020-00000000",  # privacy-allow
                "address": "某市某区",
                "legal_representative": "张某某",
            }
        ]

    def test_natural_customer_drops_legal_representative(self):
        """自然人客户的「姓名」会被提取器当法定代表人，不能写进建库字段。"""
        payload = build_sync_payload(
            _data(customers=[OACaseCustomerData(name="丙某", customer_type="natural", legal_representative="丙某")])
        )
        assert "legal_representative" not in payload["clients"][0]

    def test_oa_blank_placeholder_fields_are_dropped(self):
        """OA 用「/」表示未填，电话 / 地址 / 证件号不能把占位符带进建库字段。"""
        payload = build_sync_payload(
            _data(
                customers=[
                    OACaseCustomerData(name="甲公司", customer_type="legal", phone="/", address="/", id_number="/")
                ]
            )
        )
        assert payload["clients"] == [{"name": "甲公司", "customer_type": "legal"}]


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
            # 真实 OA 样本：类别「仲裁案件」同时覆盖商事仲裁和劳动仲裁，业务种类明确劳动仲裁时特判落 labor
            ("[诉讼]仲裁案件", "劳动人事争议仲裁", "labor"),
            ("[诉讼]仲裁案件", "国际商事仲裁", "intl"),
            ("[诉讼]民商事案件", "合同、无因管理、不当得利纠纷", "civil"),
            ("[非诉]常年法律顾问", "企业法律顾问", "advisor"),
            ("[诉讼]刑事案件", "破坏社会主义市场经济秩序罪", "criminal"),
            ("[诉讼]行政（复议）案件", "行政处罚", "administrative"),
        ],
    )
    def test_category_first_then_business_type(self, category, business_type, expected):
        payload = build_sync_payload(_data(_info(case_category=category, case_type=business_type)))
        assert payload["case_type"] == expected
        # 必须是纯 str（map_oa_case_type_from_text 返回的是 CaseType 枚举成员），保证 JSON 稳定输出 value
        assert payload["case_type"] is None or type(payload["case_type"]) is str


class TestConflictGrouping:
    """利冲分组以 OA「类别」（委托方 / 委托方关联方 / 对方当事人）为准；
    类别缺失（旧解析形态）才退回「法律地位 vs 代理何方」启发式。"""

    def _conflicts(self, *entries: tuple[str, ...], **extra: object) -> list[OAConflictData]:
        """条目 = (名称, 法律地位) 或 (名称, 法律地位, 类别)；extra 为行级字段（作用于全部条目）。"""

        def _one(entry: tuple[str, ...]) -> OAConflictData:
            item = OAConflictData(
                name=entry[0],
                conflict_type=entry[1],
                category=entry[2] if len(entry) > 2 else None,
            )
            for field in ("customer_type", "id_number", "phone"):
                if field in extra:
                    setattr(item, field, extra[field])  # type: ignore[arg-type]
            return item

        return [_one(entry) for entry in entries]

    def test_defendant_side_separates_plaintiff_codefendants_and_third_party(self):
        """旧形态夹具（无类别）：原告是对方；另两个被告只是同案其他当事人，不能叫「我方共同当事人」。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="被告"),
                customers=[OACaseCustomerData(name="某委托人公司", customer_type="legal")],
                conflicts=self._conflicts(
                    ("某第三方公司", "第三人"), ("某原告公司", "原告"), ("同案被告甲", "被告"), ("同案被告乙", "被告")
                ),
            )
        )
        assert [c["name"] for c in payload["clients"]] == ["某委托人公司"]
        assert payload["opponents"] == [{"name": "某原告公司", "conflict_type": "原告"}]
        assert payload["co_parties"] == [
            {"name": "同案被告甲", "conflict_type": "被告"},
            {"name": "同案被告乙", "conflict_type": "被告"},
        ]
        assert payload["third_parties"] == [{"name": "某第三方公司", "conflict_type": "第三人"}]

    def test_oa_category_opposing_defendants_are_filled_as_opponents(self):
        """真实样本回归（我方被告、利冲带类别形态）：OA 类别「对方当事人·被告」的共同被告必须回填为对方，
        不能因为法律地位与代理何方相同就归入不回填的同案当事人。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="被告"),
                customers=[OACaseCustomerData(name="某委托人公司", customer_type="legal")],
                conflicts=self._conflicts(
                    ("某第三方公司", "第三人", "委托方关联方"),
                    ("某原告公司", "原告", "对方当事人"),
                    ("同案被告甲", "被告", "对方当事人"),
                    ("同案被告乙", "被告", "对方当事人"),
                ),
            )
        )
        assert [c["name"] for c in payload["clients"]] == ["某委托人公司"]
        assert [o["name"] for o in payload["opponents"]] == ["某原告公司", "同案被告甲", "同案被告乙"]
        assert payload["co_parties"] == []
        assert payload["third_parties"] == [
            {"name": "某第三方公司", "conflict_type": "第三人", "category": "委托方关联方"}
        ]

    def test_client_related_category_is_co_party_with_row_fields(self):
        """「委托方关联方·被告」不是我方也不回填；行级客户类型 / 证件号 / 电话随条目带出供建库。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="被告"),
                conflicts=self._conflicts(
                    ("关联被告公司", "被告", "委托方关联方"),  # privacy-allow 虚构名
                    customer_type="legal",
                    id_number="91440000TEST000009",
                    phone="0755-00000000",  # privacy-allow
                ),
            )
        )
        assert payload["co_parties"] == [
            {
                "name": "关联被告公司",  # privacy-allow 虚构名
                "conflict_type": "被告",
                "category": "委托方关联方",
                "customer_type": "legal",
                "id_number": "91440000TEST000009",
                "phone": "0755-00000000",  # privacy-allow
            }
        ]
        assert payload["opponents"] == []

    def test_client_category_merges_into_principals(self):
        """利冲「类别：委托方」（非关联方）是我方当事人：并入委托人名单回填 PRINCIPAL。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="被告"),
                customers=[],
                conflicts=self._conflicts(
                    ("漏列委托人公司", "被告", "委托方"),  # privacy-allow 虚构名
                    ("某原告公司", "原告", "对方当事人"),
                ),
            )
        )
        assert [c["name"] for c in payload["clients"]] == ["漏列委托人公司"]  # privacy-allow 虚构名
        assert [o["name"] for o in payload["opponents"]] == ["某原告公司"]
        assert payload["co_parties"] == [] and payload["third_parties"] == []

    def test_co_parties_never_enter_clients(self):
        """同法律地位的利冲条目即使没有对应的委托人记录，也不能被当成我方当事人。"""
        payload = build_sync_payload(
            _data(_info(client_side="被告"), customers=[], conflicts=self._conflicts(("同案被告甲", "被告")))
        )
        assert payload["clients"] == []
        assert payload["opponents"] == []
        assert [c["name"] for c in payload["co_parties"]] == ["同案被告甲"]

    def test_criminal_co_suspect_is_not_our_client(self):
        """刑事：代理何方「犯罪嫌疑人」；利冲里的同案嫌疑人只是同案其他当事人，不是我们的委托人。"""
        payload = build_sync_payload(
            _data(_info(client_side="犯罪嫌疑人"), conflicts=self._conflicts(("某同案嫌疑人", "犯罪嫌疑人")))
        )
        assert payload["opponents"] == []
        assert payload["co_parties"] == [{"name": "某同案嫌疑人", "conflict_type": "犯罪嫌疑人"}]

    def test_applicant_side_respondent_is_opponent(self):
        """仲裁：我方被申请人 → 申请人是对方；同案被申请人归同案其他，不因包含「申请人」子串误判。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="被申请人"),
                conflicts=self._conflicts(("某申请人", "申请人"), ("同案被申请人", "被申请人"), ("某第三人", "第三人")),
            )
        )
        assert [o["name"] for o in payload["opponents"]] == ["某申请人"]
        assert [a["name"] for a in payload["co_parties"]] == ["同案被申请人"]
        assert [t["name"] for t in payload["third_parties"]] == ["某第三人"]

    @pytest.mark.parametrize("position", ["原审第三人", "利害关系人", "相关利益的潜在第三方"])
    def test_third_party_markers(self, position):
        payload = build_sync_payload(_data(_info(client_side="原告"), conflicts=self._conflicts(("某方", position))))
        assert payload["third_parties"] == [{"name": "某方", "conflict_type": position}]
        assert payload["opponents"] == []

    def test_category_third_party_word_wins_over_opposing_position(self):
        """类别本身含「第三方」（如「相关利益的潜在第三方」）→ 第三人，即使法律地位是被告。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="被告"),
                conflicts=self._conflicts(("某潜在第三方", "被告", "相关利益的潜在第三方")),
            )
        )
        assert payload["opponents"] == []
        assert [t["name"] for t in payload["third_parties"]] == ["某潜在第三方"]

    def test_without_client_side_everything_non_third_is_opponent(self):
        """非诉 / 代理何方为空：无法判阵营，除第三人外一律对方候选（沿用案件导入口径）。"""
        payload = build_sync_payload(
            _data(_info(client_side=""), conflicts=self._conflicts(("甲方", "被告"), ("乙方", ""), ("丙方", "第三人")))
        )
        assert [o["name"] for o in payload["opponents"]] == ["甲方", "乙方"]
        assert payload["co_parties"] == []
        assert [t["name"] for t in payload["third_parties"]] == ["丙方"]

    def test_names_already_in_clients_are_not_repeated(self):
        """委托人本人也出现在利冲表（刑事常见）：不在任何利冲分组里重复列出。"""
        payload = build_sync_payload(
            _data(
                _info(client_side="犯罪嫌疑人"),
                customers=[OACaseCustomerData(name="某嫌疑人", customer_type="natural")],
                conflicts=self._conflicts(("某嫌疑人", "犯罪嫌疑人")),
            )
        )
        assert payload["clients"] == [{"name": "某嫌疑人", "customer_type": "natural"}]
        assert payload["co_parties"] == [] and payload["opponents"] == []

    def test_groups_dedupe_by_name(self):
        payload = build_sync_payload(
            _data(_info(client_side="原告"), conflicts=self._conflicts(("某某公司", "被告"), ("某某公司", "被告")))
        )
        assert payload["opponents"] == [{"name": "某某公司", "conflict_type": "被告"}]


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
