"""数电发票文件名解析 + 姓名脱敏单测（纯函数，无 DB / 无 IO）。

样本取自**真实邮件附件名**（仅主体名脱敏，结构未改）。附件名是邮件同步时唯一不用
打开 PDF 就能拿到的元数据，解析错会把发票挂到错案件上，所以每条规则都要有护栏。
"""

from __future__ import annotations

import pytest

from apps.contracts.services.payment.invoice_filename import mask_personal_name, parse_invoice_filename

#: 真实附件名：`dzfp_<20位号码>_<购买方>_<项目号>-<开票人>.pdf`
REAL_DZFP_FILENAME = "dzfp_26442000012915552076_张三（个人）_2025GZM0001-某某律师.pdf"  # privacy-allow 虚构样例，非真实项目号


class TestParseInvoiceFilename:
    def test_parses_real_dzfp_attachment(self) -> None:
        parsed = parse_invoice_filename(REAL_DZFP_FILENAME)

        assert parsed["invoice_number"] == "26442000012915552076"
        assert parsed["buyer_name"] == "张三"
        assert parsed["project_code"] == "2025GZM0001"  # privacy-allow 虚构样例，非真实项目号

    def test_variant_without_number_or_project_code_does_not_raise(self) -> None:
        """真实变体：`发票_<买方>_<日期>开具.pdf`，既没有 20 位号码也没有项目号。"""
        parsed = parse_invoice_filename("发票_某供应链管理有限公司__20260623开具.pdf")

        assert parsed["buyer_name"] == "某供应链管理有限公司"
        assert parsed["project_code"] == ""
        # `20260623` 是开票日期不是发票号码。当成号码会污染去重键：
        # 同一张票重发一次就多出一条待认领。
        assert parsed["invoice_number"] == ""
        assert set(parsed) == {"invoice_number", "buyer_name", "project_code"}

    def test_date_like_digits_are_never_taken_as_invoice_number(self) -> None:
        """8 位但形如 YYYYMMDD 的片段一律不当发票号码。"""
        for filename in (
            "发票_某某公司_20260623开具.pdf",
            "发票_某某公司_19991231.pdf",
        ):
            assert parse_invoice_filename(filename)["invoice_number"] == ""

    def test_real_8_digit_number_next_to_date_is_still_used(self) -> None:
        """真号码与日期间存时，跳过日期拿到真号码。"""
        parsed = parse_invoice_filename("发票_某某公司_12345678_20260623.pdf")

        assert parsed["invoice_number"] == "12345678"

    def test_company_buyer_is_kept_verbatim(self) -> None:
        parsed = parse_invoice_filename("发票_佛山市某某铝业有限公司_2025GZM0001-张三.pdf")  # privacy-allow 虚构样例，非真实项目号

        assert parsed["buyer_name"] == "佛山市某某铝业有限公司"
        assert parsed["project_code"] == "2025GZM0001"  # privacy-allow 虚构样例，非真实项目号

    def test_project_code_letters_longer_than_one_are_not_matched(self) -> None:
        """严格形态只认 1 位字母：`2025GZMB0034` 是另一种编号，不能当成项目号。"""  # privacy-allow 虚构样例，非真实项目号
        parsed = parse_invoice_filename("dzfp_26442000012915552076_某某公司_2025GZMB0034-张三.pdf")  # privacy-allow 虚构样例，非真实项目号

        assert parsed["invoice_number"] == "26442000012915552076"
        assert parsed["project_code"] == ""

    def test_falls_back_to_legacy_8_to_12_digit_number(self) -> None:
        parsed = parse_invoice_filename("dzfp_12345678_某某公司_2025GZM0001-张三.PDF")  # privacy-allow 虚构样例，非真实项目号

        assert parsed["invoice_number"] == "12345678"
        assert parsed["project_code"] == "2025GZM0001"  # privacy-allow 虚构样例，非真实项目号

    @pytest.mark.parametrize("filename", ["", "   ", "weird", "a.b.pdf", "_.pdf", "发票.pdf"])
    def test_unparseable_names_yield_empty_fields(self, filename: str) -> None:
        # 解析失败必须给空串而不是抛异常：抛了会把整封邮件的附件同步一起废掉
        assert parse_invoice_filename(filename) == {
            "invoice_number": "",
            "buyer_name": "",
            "project_code": "",
        }


class TestMaskPersonalName:
    def test_strips_personal_marker_from_legal_person(self) -> None:
        assert mask_personal_name("张三（个人）") == "张三"

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("张三(个人)", "张三"),
            ("张三（自然人）", "张三"),
            ("张三(自然人)", "张三"),
        ],
    )
    def test_handles_all_marker_forms(self, name: str, expected: str) -> None:
        assert mask_personal_name(name) == expected

    def test_company_name_is_returned_unchanged(self) -> None:
        assert mask_personal_name("某某公司") == "某某公司"

    def test_empty_string_returns_empty_string(self) -> None:
        assert mask_personal_name("") == ""

    def test_actual_person_name_survives(self) -> None:
        """脱敏只去标注，不动人名本身——名字是挂案检索键。"""
        assert mask_personal_name("张三") == "张三"
