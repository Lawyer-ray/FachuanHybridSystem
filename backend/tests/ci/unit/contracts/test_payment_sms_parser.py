"""到账短信解析单测（付款人 / 金额 / 日期 / 备注）。

样本取自**真实建设银行到账短信**（仅脱敏，未改动结构）。财务字段错一位就是
错账，这些样例是「解析器不许退化」的护栏。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.contracts.services.payment.payment_sms_parser import PaymentSmsParser

TODAY = date(2026, 10, 26)

#: (原文, 金额, 日期, 付款人, 备注)
REAL_SAMPLES: list[tuple[str, str, date, str, str]] = [
    (
        "【建设银行】张三10月26日13时32分向贵公司4501账户存入人民币9000元。"
        "（代付甲方农业咨询有限公司(2026）诉讼案件代理律师费）",
        "9000",
        date(2026, 10, 26),
        "张三",
        "甲方农业咨询有限公司(2026",
    ),
    (
        "【建设银行】乙方电器有限公司10月15日17时5分向贵公司4501账户服务费存入人民币9000元。",
        "9000",
        date(2026, 10, 15),
        "乙方电器有限公司",
        "服务费",
    ),
    (
        "【建设银行】丙方不锈钢有限公司10月14日14时17分向贵公司4501账户律师费存入人民币30000元。",
        "30000",
        date(2026, 10, 14),
        "丙方不锈钢有限公司",
        "律师费",
    ),
    (
        "【建设银行】李四9月30日15时31分向贵公司4501账户存入人民币50000元"
        "（代某房地产公司付律师服务费）。",
        "50000",
        date(2026, 9, 30),
        "李四",
        "代某房地产公司付律师服务费",
    ),
    (
        "【建设银行】某市某公证处9月24日15时12分向贵公司4501账户律师费存入人民币100000元。",
        "100000",
        date(2026, 9, 24),
        "某市某公证处",
        "律师费",
    ),
    (
        # 「电子汇入」是渠道词不是用途：备注留空让人手填，不把渠道当摘要
        "【建设银行】王五9月1日22时9分向贵公司4501账户电子汇入存入人民币2400元。",
        "2400",
        date(2026, 9, 1),
        "王五",
        "",
    ),
    (
        "【建设银行】赵六8月24日16时6分向贵公司4501账户律师费存入人民币9000元。",
        "9000",
        date(2026, 8, 24),
        "赵六",
        "律师费",
    ),
    (
        "【建设银行】乙方电器有限公司8月21日17时3分向贵公司4501账户顾问费存入人民币20000元。",
        "20000",
        date(2026, 8, 21),
        "乙方电器有限公司",
        "顾问费",
    ),
    (
        "【建设银行】孙七8月21日10时40分向贵公司4501账户存入人民币100000元。"
        "（某某甲第二轮的律师费）",
        "100000",
        date(2026, 8, 21),
        "孙七",
        "某某甲第二轮的律师费",
    ),
    (
        "【建设银行】丁方餐饮管理服务有限公司8月10日17时49分"
        "向贵公司4501账户法律顾问费存入人民币30000元。",
        "30000",
        date(2026, 8, 10),
        "丁方餐饮管理服务有限公司",
        "法律顾问费",
    ),
]


@pytest.mark.parametrize(("text", "amount", "day", "payer", "note"), REAL_SAMPLES)
def test_real_bank_sms(text: str, amount: str, day: date, payer: str, note: str) -> None:
    parse = PaymentSmsParser().parse(text, today=TODAY)
    assert parse.amount == Decimal(amount)
    assert parse.received_at == day
    assert parse.payer == payer
    assert parse.note == note


class TestAmount:
    def test_currency_marker_required(self) -> None:
        """没有货币标记的数字不当作金额（账号尾号 4501 不能被认成收款）。"""
        assert PaymentSmsParser().parse("向贵公司4501账户存入款项", today=TODAY).amount is None

    @pytest.mark.parametrize(
        "text",
        ["收到人民币12,500.00元", "收到 ¥12500 元", "到账金额 12500.00 元", "转入12500元"],
    )
    def test_common_shapes(self, text: str) -> None:
        assert PaymentSmsParser().parse(text, today=TODAY).amount == Decimal("12500.00")


class TestDate:
    def test_full_year_format(self) -> None:
        assert PaymentSmsParser().parse("2026-03-05 收到人民币100元", today=TODAY).received_at == date(2026, 3, 5)

    def test_future_month_day_rolls_back_to_previous_year(self) -> None:
        """1 月 2 日收到「12 月 31 日」的短信：那笔到账是去年 12 月 31 日的。"""
        parse = PaymentSmsParser().parse("12月31日向贵公司账户存入人民币100元", today=date(2026, 1, 2))
        assert parse.received_at == date(2025, 12, 31)

    def test_past_month_day_stays_this_year(self) -> None:
        """已过的月日不能跳到去年（否则会把本月到账记成去年）。"""
        parse = PaymentSmsParser().parse("1月5日向贵公司账户存入人民币100元", today=date(2026, 12, 20))
        assert parse.received_at == date(2026, 1, 5)

    def test_invalid_date_ignored(self) -> None:
        parse = PaymentSmsParser().parse("13月45日 存入人民币100元", today=TODAY)
        assert parse.received_at is None
        assert parse.amount == Decimal("100.00")

    def test_missing_date_kept_none(self) -> None:
        assert PaymentSmsParser().parse("李四转入人民币3000元", today=TODAY).received_at is None


class TestDegradation:
    def test_empty_input(self) -> None:
        parse = PaymentSmsParser().parse("   ", today=TODAY)
        assert parse.amount is None
        assert not parse.ok

    def test_unrecognized_text_keeps_amount_only(self) -> None:
        parse = PaymentSmsParser().parse("这是一段看不懂的话，金额 800 元", today=TODAY)
        assert parse.amount == Decimal("800.00")
        assert parse.payer == ""
        assert parse.ok

    def test_note_truncated_to_model_limit(self) -> None:
        long_note = "长" * 400
        parse = PaymentSmsParser().parse(f"张三向贵公司账户转入人民币100元（{long_note}）", today=TODAY)
        assert len(parse.note) <= 255

    def test_hints_are_human_readable(self) -> None:
        parse = PaymentSmsParser().parse(REAL_SAMPLES[0][0], today=TODAY)
        assert any("金额" in h for h in parse.hints)
        assert any("付款人" in h for h in parse.hints)
