"""`CaseOut.resolve_parties` 的诉讼地位必须是**中文标签**，不是代码值。

背景（2026-11-28 实拍）：案件卡的「诉讼地位」整行显示 `plaintiff：张三 /
defendant：李四`。根因不在前端也不在 `CasePartyOut.resolve_legal_status`，而在
两者之间的那一跳：`CaseOut._as_party_dicts` 把 Django 模型转成 dict 时放的是
原始代码值，而 resolver 的 dict 分支是直传（它假设 dict 已是序列化后的形状）。

同一张卡片上的 `status`（在办）、`current_stage`（一审）都有 `get_*_display`，
所以是中文——一张卡上半中半英，正是这条 bug 的外观。

这些用例是纯函数测试：不建库、不碰 ORM，用 stub 对象钉住「转 dict」这一步的口径。
"""

from unittest.mock import MagicMock

from apps.cases.schemas.case_schemas import CaseOut


def _party(legal_status: str, display: str) -> MagicMock:
    party = MagicMock()
    party.id = 1
    party.case_id = 7
    party.client_id = 100
    party.legal_status = legal_status
    party.get_legal_status_display.return_value = display
    return party


class TestPartyDictsCarryChineseLabel:
    def test_returns_display_label_not_code(self):
        dicts = CaseOut._as_party_dicts([_party("plaintiff", "原告"), _party("defendant", "被告")])

        assert [d["legal_status"] for d in dicts] == ["原告", "被告"]

    def test_keeps_empty_status_empty(self):
        party = _party("", "")

        dicts = CaseOut._as_party_dicts([party])

        assert dicts[0]["legal_status"] == ""

    def test_falls_back_to_raw_value_when_no_display_getter(self):
        # 模型字段没有 choices 时 Django 不提供 get_*_display；此时不该抛，落回原值
        party = MagicMock(spec=["id", "case_id", "client_id", "legal_status", "client"])
        party.legal_status = "plaintiff"

        dicts = CaseOut._as_party_dicts([party])

        assert dicts[0]["legal_status"] == "plaintiff"

    def test_dict_input_is_passed_through_untouched(self):
        # 已是序列化形状的 dict（含中文标签）不能再翻一次
        given = [{"id": 1, "case_id": 7, "client_id": 100, "legal_status": "原告"}]

        assert CaseOut._as_party_dicts(given) == given

    def test_existing_dict_keys_are_kept(self):
        dicts = CaseOut._as_party_dicts([_party("third_party", "第三人")])

        assert set(dicts[0]) >= {"id", "case_id", "client_id", "legal_status"}
        assert dicts[0]["id"] == 1
        assert dicts[0]["case_id"] == 7
