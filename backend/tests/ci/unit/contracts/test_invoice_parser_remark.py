"""发票备注栏与律所项目号抽取单测（纯函数，无 DB / 无 IO）。

样本是**真实数电票 PDF 经 pdfplumber 提取的原文**（主体名脱敏，版式与切行未改）。
备注栏在这个版式里的样子很反直觉：表格把「备」「注」两个竖排字切成独立行，
律师真正写的项目号/案由夹在「销售方地址:…」「销方开户银行:…」之间。按行号硬编码
换个版式就静默错位，所以定位必须按内容走。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.invoice_recognition.services.invoice_parser import InvoiceParser

#: 真实数电票 pdfplumber 文本，逐行照抄（含表格切行产生的孤立「备」「注」和页脚姓名）。
REAL_INVOICE_TEXT = """电子发票（普通发票）
发票号码：26442000012915552076
开票日期：2026年11月10日
购 名称：张三（个人） 销 名称：某律师事务所
买 售
方 方
信 统一社会信用代码/纳税人识别号：110101199001011234 信 统一社会信用代码/纳税人识别号：91110000MA0000000X
息 息
项目名称 规格型号 单 位 数 量 单 价 金 额 税率/征收率 税 额
*生产生活服务*法律咨询 项 1 2264.15094339623 2264.15 6% 135.85  # privacy-allow 虚构样例，非真实项目号
服务
合 计 ¥2264.15 ¥135.85
价税合计（大写） 贰仟肆佰圆整 （小写）¥2400.00
购买方地址:-; 电话:-;
购方开户银行:-; 银行账号:-;
备
销售方地址:某省某市某区某路1号; 电话:00000000;  # privacy-allow 虚构样例，非真实项目号
注 销方开户银行:某银行某支行; 银行账号:00000000000000000000;
2025GZM0001-张某与某公司合同纠纷;  # privacy-allow 虚构样例，非真实项目号
复核人:李某
开票人：王某
王某
"""


class TestRealInvoiceRemark:
    def setup_method(self) -> None:
        self.parsed = InvoiceParser().parse(REAL_INVOICE_TEXT)

    def test_extracts_project_code_from_remark(self) -> None:
        assert self.parsed.project_code == "2025GZM0001"  # privacy-allow 虚构样例，非真实项目号

    def test_remark_keeps_case_description(self) -> None:
        assert "张某与某公司合同纠纷" in self.parsed.remark

    def test_remark_does_not_leak_address_or_bank_lines(self) -> None:
        """地址/开户行是固定栏位，不是律师写的备注——进了备注只会污染挂案检索。"""
        assert "销售方地址" not in self.parsed.remark
        assert "销方开户银行" not in self.parsed.remark
        assert "00000000000000000000" not in self.parsed.remark

    def test_remark_stops_before_reviewer_footer(self) -> None:
        assert "李某" not in self.parsed.remark
        assert "王某" not in self.parsed.remark

    def test_existing_fields_are_unchanged(self) -> None:
        """P2 只加字段，不许动既有抽取结果。"""
        assert self.parsed.invoice_number == "26442000012915552076"
        assert self.parsed.invoice_date == date(2026, 11, 10)
        assert self.parsed.amount == Decimal("2264.15")
        assert self.parsed.tax_amount == Decimal("135.85")
        assert self.parsed.total_amount == Decimal("2400.00")
        assert self.parsed.buyer_name == "张三（个人）"
        assert self.parsed.seller_name == "某律师事务所"


class TestRemarkFallbacks:
    def setup_method(self) -> None:
        self.parser = InvoiceParser()

    def test_text_without_remark_yields_empty_fields(self) -> None:
        """没有备注栏的发票不能抛异常，两个新字段都留空。"""
        text = (
            "发票代码：123456789012\n"
            "发票号码：12345678\n"
            "开票日期：2025年01月15日\n"
            "合 计 ¥1,000.00 ¥60.00\n"
            "（小写） ¥1,060.00\n"
            "购买方名称：某某科技有限公司\n"
            "增值税专用发票"
        )
        parsed = self.parser.parse(text)

        assert parsed.remark == ""
        assert parsed.project_code == ""
        assert parsed.invoice_number == "12345678"

    def test_empty_text_does_not_raise(self) -> None:
        parsed = self.parser.parse("")

        assert parsed.remark == ""
        assert parsed.project_code == ""

    def test_project_code_falls_back_to_full_text_when_remark_is_empty(self) -> None:
        """备注抽不到时，全文里出现项目号仍然要认出来（有的版式项目号在页眉）。"""
        text = "电子发票（普通发票）\n项目号: 2025GZM0001\n发票号码：26442000012915552076\n"  # privacy-allow 虚构样例，非真实项目号

        assert self.parser._extract_project_code(text, remark="") == "2025GZM0001"  # privacy-allow 虚构样例，非真实项目号

    def test_project_code_adjacent_to_chinese_text_is_matched(self) -> None:
        """项目号紧贴汉字时也要抽到：`\\b` 把汉字当单词字符，会在这里静默漏抽。"""
        assert self.parser._extract_remark("备\n注\n备注2025GZM0001-某某案;") != ""  # privacy-allow 虚构样例，非真实项目号

    def test_longer_project_code_letters_are_not_taken_as_strict_form(self) -> None:
        """`2025GZMB0034` 是两位字母编号，严格形态不认，由放宽形态兜底。"""  # privacy-allow 虚构样例，非真实项目号
        assert self.parser._extract_project_code("x_2025GZMB0034_y", remark="") == "2025GZMB0034"  # privacy-allow 虚构样例，非真实项目号
