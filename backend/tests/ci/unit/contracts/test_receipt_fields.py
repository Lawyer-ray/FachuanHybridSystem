"""银行回单字段补全的单测（纯函数，无 DB / 无 IO）。

输入的样本按**真实网银电子回单**的版式构造：分栏「付款人 / 收款人」两栏都叫
「户名」、金额同时有小写与大写、日期带完整时分。这些正是短信解析拿不到的字段，
也是记账时最容易录错的地方。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.contracts.services.payment.receipt_fields import ReceiptTextParser, chinese_amount_to_decimal

# 真实回单版式（结构照抄，主体名脱敏）。OCR 出来的文本通常没有表格框线，
# 靠栏位词（户名/转出账号/转入账号）串在一行里。
RECEIPT = (
    "南海农商银行 网上银行交易电子凭证 "
    "交易时间:2026-11-02 14:17:07 交易状态:交易成功 网银流水:88880001 "
    "付款人 户名:佛山市某某铝业有限公司 转出账号:6222XXXXXXXXXXXX 转账:普通跨行汇款 "
    "收款人 户名:北京某某(广州)律师事务所 转入账号:6228XXXXXXXXXXXX "
    "开户银行:中国建设银行股份有限公司广州海珠广场支行 "
    "金额: 25,000.00 大写:贰万伍仟元正整 手续费: 0.00 币种:人民币 用途:往来款 "
    "打印时间: 2026-11-02 14:17:10"
)


class TestChineseAmount:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("贰万伍仟元正整", "25000.00"),
            ("贰万伍仟元整", "25000.00"),
            ("壹拾万元整", "100000.00"),
            ("玖仟元整", "9000.00"),
            ("壹佰贰拾叁元肆角伍分", "123.45"),
            ("叁万元整", "30000.00"),
            # 圆 = 元的异体写法（财务凭证常见）
            ("壹万元圆整", "10000.00"),
        ],
    )
    def test_parses_standard_forms(self, text: str, expected: str) -> None:
        assert chinese_amount_to_decimal(text) == Decimal(expected)

    @pytest.mark.parametrize("text", ["", "往来款", "伍", "零元整", "贰万X仟元"])
    def test_returns_none_for_unparseable(self, text: str) -> None:
        # 认不出必须给 None：财务场景宁可不填，也不能给一个错的数
        assert chinese_amount_to_decimal(text) is None


class TestReceiptParser:
    def test_extracts_all_key_fields(self) -> None:
        parsed = ReceiptTextParser().parse(RECEIPT)

        assert parsed.is_receipt is True
        assert parsed.amount == Decimal("25000.00")
        assert parsed.upper_amount == Decimal("25000.00")
        assert parsed.amount_mismatch is False
        assert parsed.received_at == date(2026, 11, 2)
        assert parsed.time_text == "14:17"
        assert parsed.payer == "佛山市某某铝业有限公司"
        assert parsed.payee == "北京某某(广州)律师事务所"
        assert parsed.purpose == "往来款"
        assert parsed.hints

    def test_self_entity_is_never_the_payer(self) -> None:
        """两栏都叫「户名」时最容易把自家律所当付款人——这是本模块存在的主因。"""
        parsed = ReceiptTextParser().parse(RECEIPT)
        assert "律师事务所" not in parsed.payer
        assert "律师事务所" in parsed.payee

    def test_swapped_columns_are_corrected(self) -> None:
        """OCR 把两栏顺序搞反时，用「律所=自己」的常识纠正回来。"""
        swapped = (
            "电子回单 交易流水:123 "
            "付款人 户名:北京某某(广州)律师事务所 转出账号:6228XXXXXXXXXXXX "
            "收款人 户名:佛山市某某铝业有限公司 转入账号:6222XXXXXXXXXXXX "
            "金额: 25,000.00 交易时间:2026-11-02 14:17:07"
        )
        parsed = ReceiptTextParser().parse(swapped)
        assert parsed.payer == "佛山市某某铝业有限公司"
        assert "律师事务所" in parsed.payee

    def test_amount_falls_back_to_upper_when_lowercase_missing(self) -> None:
        """小写金额 OCR 糊掉时用大写兜底，并给出提示（不是静默填）。"""
        text = "电子回单 用途:律师费 付款人 户名:佛山市某某铝业有限公司 收款人 户名:北京某某律师事务所 大写:叁万元整"
        parsed = ReceiptTextParser().parse(text)
        assert parsed.amount == Decimal("30000.00")
        assert any("取自大写" in h for h in parsed.hints)

    def test_amount_mismatch_is_flagged(self) -> None:
        text = "电子回单 金额: 25,000.00 大写:贰万陆仟元整 交易时间:2026-11-02 14:17:07"
        parsed = ReceiptTextParser().parse(text)
        assert parsed.amount == Decimal("25000.00")
        assert parsed.upper_amount == Decimal("26000.00")
        assert parsed.amount_mismatch is True

    def test_plain_sms_is_not_mistaken_for_receipt(self) -> None:
        sms = "【建设银行】丙方不锈钢有限公司10月14日14时17分向贵公司4501账户律师费存入人民币30000元。"
        parsed = ReceiptTextParser().parse(sms)
        assert parsed.is_receipt is False

    def test_empty_text_yields_empty_draft(self) -> None:
        parsed = ReceiptTextParser().parse("   ")
        assert parsed.amount is None
        assert parsed.payer == ""
        assert parsed.hints == []

    def test_purpose_stops_at_footer_notice(self) -> None:
        """回单底部的模板告示会被 OCR 粘在用途值后面，不能跟着进备注。

        这条样本直接来自真实回单的 VLM 转写结果（主体名脱敏）：修复前 note 是
        「往来款提示1、已在银行柜台领用业务回单的客户…」，对账时毫无用处。
        """
        text = (
            "南海农商银行网上银行交易电子凭证交易时间:2026-11-0214:17:07付款人户名佛山市某某铝业有限公司"
            "收款人户名北京某某(广州)律师事务所金额25,000.00大写:贰万伍仟元整手续费:0.00币种:人民币"
            "用途:往来款提示1、已在银行柜台领用业务回单的客户，请注意核对，请勿重复记账使用。"
            "电子印章南海农商银行电子回单专用章打印时间:2026-11-0214:17:10"
        )
        parsed = ReceiptTextParser().parse(text)
        assert parsed.purpose == "往来款"
        assert parsed.amount == Decimal("25000.00")
        assert parsed.payer == "佛山市某某铝业有限公司"
        assert parsed.payee == "北京某某(广州)律师事务所"

    def test_respects_explicit_currency_prefixed_amount(self) -> None:
        """账号/流水号是长数字串，不能被当成金额（金额规则必须带小数点或标签）。"""
        text = "电子回单 网银流水:88880001 转出账号:6222XXXXXXXXXXXX 金额: ¥9,000.00"
        parsed = ReceiptTextParser().parse(text)
        assert parsed.amount == Decimal("9000.00")
