"""红字发票（冲销票）解析回归。

## 为什么这个文件存在

修复前 `_TOTAL_PATTERN` / `_AMOUNT_PATTERN` 的字符类是 `[\\d,]+`，**不认负号**：
一张真实的红票（`-¥40,000.00`）三个金额全部抽成 `None`，下游 `_amounts_match(None)`
恒为 False，界面就报「金额与收款不符」——方向完全错了，真实情况是「没识别出来」。

## fixture 来源

`RED_INVOICE_TEXT` 的**版式**取自真实红票 PDF 的 `extract_text()` 输出（两页拼一段），
但**全部内容已替换为虚构样例**——真实票号、身份证号、地址、开户行、人名一律不入库。
保留的是解析器真正依赖的结构特征：负号金额、「（负数）」大写提示、两页重复票头、
备注栏里两个 20 位号码同行。只存文本、不存 PDF 二进制：这是解析器的唯一输入形态，
锚点稳定且不引入 pdf 解析依赖。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.invoice_recognition.services.invoice_parser import InvoiceParser, ParsedInvoice

pytestmark = pytest.mark.unit

#: 红票 PDF 的 pdfplumber 文本（两页版式）。**全部数据为虚构样例**，
#: 但保留真实样本的结构特征：带负号金额、两页重复票头、备注栏里两个 20 位号码同行、
#: 「（负数）」大写提示。这些都是解析器真正要吃住的东西，不随数据虚构而改变。
RED_INVOICE_TEXT = """电子发票（普通发票）
发票号码：12345678901234567890
开票日期：2099年3月11日
共2页 第1页
购 名称：某甲（个人） 销 名称：某某律师事务所
买 售
方 方
信 统一社会信用代码/纳税人识别号：000000000000000000 信 统一社会信用代码/纳税人识别号：0000000000000000000
息 息
项目名称 规格型号 单 位 数 量 单 价 金 额 税率/征收率 税 额
*生产生活服务*法律咨询 项 -1 9433.9622641509 -9433.96 6% -566.04
服务
合 计 ¥-9433.96 ¥-566.04
价税合计（大写） （负数）壹万圆整 （小写）¥-10000.00
购买方地址:-; 电话:-;
购方开户银行:-; 银行账号:-;
备
销售方地址:某某路1号; 电话:00000000;
注 销方开户银行:某某银行某某支行; 银行账号:00000000000000000000;
被红冲蓝字数电发票号码：11111111111111111111 红字发票信息确认单编号：22222222222222222222;
复核人:某乙;
开票人：某丙
某丙
电子发票（普通发票）
发票号码：12345678901234567890
开票日期：2099年3月11日
共2页 第2页
购 名称：某甲（个人） 销 名称：某某律师事务所
买 售
方 方
信 统一社会信用代码/纳税人识别号：000000000000000000 信 统一社会信用代码/纳税人识别号：0000000000000000000
息 息
0000GZF0001-某甲非诉专项  # privacy-allow 虚构项目号样例
备
注
开票人：某丙
某丙"""

#: 同一客户当天重开的**蓝票**（正数），用来证明负号支持没有把正票改坏
BLUE_INVOICE_TEXT = """电子发票（普通发票）
发票号码：99999999999999999999
开票日期：2099年3月11日
购 名称：某甲（个人） 销 名称：某某律师事务所
买 售
方 方
*生产生活服务*法律咨询 项 1 9433.9622641509 9433.96 6% 566.04
合 计 ¥9433.96 ¥566.04
价税合计（大写） 壹万圆整 （小写）¥10000.00
备
注
0000GZF0001-某甲非诉专项  # privacy-allow 虚构项目号样例
开票人：某丙"""

#: 解析器抽取结果的期望值（与上面文本一一对应）
RED_AMOUNT = Decimal("-9433.96")
RED_TAX = Decimal("-566.04")
RED_TOTAL = Decimal("-10000.00")
RED_AGAINST_NUMBER = "11111111111111111111"
RED_CONFIRM_NO = "22222222222222222222"
OWN_NUMBER = "12345678901234567890"
BLUE_AMOUNT = Decimal("9433.96")
BLUE_TAX = Decimal("566.04")
BLUE_TOTAL = Decimal("10000.00")

@pytest.fixture
def red_invoice() -> ParsedInvoice:
    return InvoiceParser().parse(RED_INVOICE_TEXT)


class TestRedInvoiceAmounts:
    """D1：负号必须被认出来，否则红票全链路都拿不到金额。"""

    def test_amount_is_negative(self, red_invoice) -> None:
        assert red_invoice.amount == RED_AMOUNT

    def test_tax_amount_is_negative(self, red_invoice) -> None:
        assert red_invoice.tax_amount == RED_TAX

    def test_total_amount_is_negative(self, red_invoice) -> None:
        assert red_invoice.total_amount == RED_TOTAL

    def test_amounts_are_consistent(self, red_invoice) -> None:
        assert red_invoice.amount + red_invoice.tax_amount == red_invoice.total_amount


class TestRedInvoiceFacts:
    """红票身份：备注栏「被红冲蓝字数电发票号码」「红字发票信息确认单编号」。"""

    def test_red_against_number(self, red_invoice) -> None:
        assert red_invoice.red_against_number == RED_AGAINST_NUMBER

    def test_red_confirmation_no(self, red_invoice) -> None:
        assert red_invoice.red_confirmation_no == RED_CONFIRM_NO

    def test_own_invoice_number_is_not_the_offset_one(self, red_invoice) -> None:
        # 两个 20 位号码在同一行里，抽错会把自己标成「冲自己」
        assert red_invoice.invoice_number == OWN_NUMBER

    def test_other_fields_still_parsed(self, red_invoice) -> None:
        assert red_invoice.invoice_date == date(2099, 3, 11)
        assert red_invoice.project_code == "0000GZF0001"
        assert red_invoice.buyer_name == "某甲（个人）"


class TestBlueInvoiceRegression:
    """蓝票回归：支持负号不能改变正票的任何字段。"""

    def test_amounts_stay_positive(self) -> None:
        parsed = InvoiceParser().parse(BLUE_INVOICE_TEXT)

        assert parsed.amount == BLUE_AMOUNT
        assert parsed.tax_amount == BLUE_TAX
        assert parsed.total_amount == BLUE_TOTAL

    def test_no_red_facts_on_blue_invoice(self) -> None:
        parsed = InvoiceParser().parse(BLUE_INVOICE_TEXT)

        assert parsed.red_against_number == ""
        assert parsed.red_confirmation_no == ""


class TestRedFactsDefaults:
    """解析器对非红票/空文本必须给空串，不能抛、不能给 None。"""

    def test_empty_text(self) -> None:
        parsed = InvoiceParser().parse("")

        assert parsed.red_against_number == ""
        assert parsed.red_confirmation_no == ""

    def test_defaults_on_dataclass(self) -> None:
        parsed = ParsedInvoice()
        assert parsed.red_against_number == ""
        assert parsed.red_confirmation_no == ""

    @pytest.mark.parametrize("colon", ["：", ":"])
    def test_half_and_full_width_colon(self, colon: str) -> None:
        text = f"被红冲蓝字数电发票号码{colon}11111111111111111111"
        parsed = InvoiceParser().parse(text)

        assert parsed.red_against_number == RED_AGAINST_NUMBER

    def test_label_without_colon_is_not_taken(self) -> None:
        # 没有冒号说明不是「标签：值」的版式，宁可不抽也不要抽错
        parsed = InvoiceParser().parse("被红冲蓝字数电发票号码11111111111111111111")

        assert parsed.red_against_number == ""

    def test_too_short_number_is_rejected(self) -> None:
        # 8 位起才认：更短的数字不是发票号码，收进来只会污染配对
        parsed = InvoiceParser().parse("被红冲蓝字数电发票号码：1234567")

        assert parsed.red_against_number == ""
