"""到账通知解析（HTML → 文本 + 字段抽取）的纯函数测试。

锁定的核心行为：
1. **数字不被标签切碎** —— 旧实现靠"剥标签顺便插空格"，换成 ``2,400.00``
   或数字间夹行内标签就会静默丢失金额，而金额是认领流程的根本。
2. ``<style>``/``<head>`` 噪声不进入待匹配文本（Word 导出邮件有上千字符 CSS）。
3. 付款人 / 代付方 / 到账日 的结构化抽取。
4. **抽不到金额必须显式失败**（``ok=False``），不能造 amount=0 的记录。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.message_hub.services.transfer_notice import html_to_text, parse_transfer_notice

# 真实邮件正文形态（Word 导出，数字被逐个包进 <span lang="EN-US">）  # privacy-allow
REAL_HTML_HEHUO = """<html xmlns:v="urn:schemas-microsoft-com:vml"><head>
<meta http-equiv="Content-Type" content="text/html; charset=gb2312">
<style><!--
@font-face {font-family:"等线"; panose-1:2 1 6 0 3 1 1 1 1 1;}
p.MsoNormal, li.MsoNormal, div.MsoNormal {margin:0cm; font-size:10.5pt;}
--></style></head>
<body lang="ZH-CN"><div class="WordSection1">
<p class="MsoNormal">【建设银行】李某<span lang="EN-US">11</span>月<span lang="EN-US">4</span>日<span
lang="EN-US">17</span>时<span lang="EN-US">30</span>分向贵公司<span lang="EN-US">4501</span>账户电子汇入存入人民币<span
lang="EN-US">2400</span>元。<span lang="EN-US"><o:p></o:p></span></p>
</div></body></html>"""

REAL_HTML_ONBEHALF = """<html><head><style>@font-face{font-family:"等线"}</style></head>
<body><div><p class="MsoNormal">【建设银行】张某<span>11</span>月<span>8</span>日<span>10</span>时<span>31</span>分向贵公司<span>4501</span>账户存入人民币<span>10000</span>元。（代某供应链公司付律师费）</p></div></body></html>"""  # privacy-allow


class TestHtmlToText:
    def test_inline_tags_do_not_split_numbers(self):
        """核心：行内标签不插任何字符，数字保持完整。"""
        assert "2400" in html_to_text("<p>人民币<span>2</span><span>400</span>元</p>")

    def test_thousands_separator_split_across_tags(self):
        text = html_to_text("<p>人民币<span>2,</span><span>400.00</span>元</p>")
        assert "2,400.00" in text

    def test_style_and_head_content_dropped(self):
        html = "<html><head><style>@font-face{x:y} .MsoNormal{margin:0}</style></head><body><p>正文</p></body></html>"
        text = html_to_text(html)
        assert "正文" in text
        assert "@font-face" not in text
        assert "MsoNormal" not in text

    def test_block_tags_become_newlines(self):
        text = html_to_text("<div>第一行</div><div>第二行</div>")
        assert "第一行" in text and "第二行" in text
        assert "第一行第二行" not in text

    def test_empty(self):
        assert html_to_text("") == ""

    def test_malformed_html_does_not_raise(self):
        assert "内容" in html_to_text("<p>内容<span>未闭合")


class TestRealEmailRegression:
    """真实邮件回归——这两封是本功能的需求来源。"""

    def test_hehuo_2400(self):
        n = parse_transfer_notice(subject="【到账通知】请申请开票", body_html=REAL_HTML_HEHUO)
        assert n.amount == Decimal("2400")
        assert n.payer_name == "李某"  # privacy-allow
        assert n.on_behalf_of == ""
        assert n.received_at == date(n.received_at.year, 11, 4) if n.received_at else False
        assert n.ok

    def test_liulide_10000_on_behalf(self):
        n = parse_transfer_notice(subject="【到账通知】请申请开票并准备代付文件", body_html=REAL_HTML_ONBEHALF)
        assert n.amount == Decimal("10000")
        assert n.payer_name == "张某"  # privacy-allow
        assert n.on_behalf_of == "某供应链公司"  # privacy-allow
        assert n.ok


class TestParseAmount:
    def test_full_width_yen(self):
        assert parse_transfer_notice(body_html="<p>汇入￥3500元</p>").amount == Decimal("3500")

    def test_thousands_separator(self):
        assert parse_transfer_notice(body_html="<p>人民币 12,345.67 元</p>").amount == Decimal("12345.67")

    def test_empty_body_fails_loudly(self):
        """抽不到金额必须 ok=False，调用方据此跳过建单。"""
        n = parse_transfer_notice(body_html="<p>提示消息，请查收</p>")
        assert n.amount is None
        assert not n.ok

    def test_empty_everything(self):
        assert not parse_transfer_notice().ok

    def test_account_number_not_taken_as_amount(self):
        """「账户4501」没有「元」后缀，不应被当成金额。"""
        n = parse_transfer_notice(body_html="<p>向贵公司4501账户存入人民币12000元</p>")
        assert n.amount == Decimal("12000")


class TestParsePayer:
    def test_payer_after_bank_bracket(self):
        n = parse_transfer_notice(body_html="<p>【建设银行】王小明11月4日存入人民币100元</p>")
        assert n.payer_name == "王小明"  # privacy-allow

    def test_payer_does_not_swallow_time_word(self):
        """「张伟昨日向…」里的「昨日」不能被吞进姓名。"""
        n = parse_transfer_notice(body_html="<p>【农业银行】张伟昨日向贵公司账户汇入￥3500元</p>")
        assert n.payer_name == "张伟"  # privacy-allow

    def test_payer_label_form(self):
        n = parse_transfer_notice(body_html="<p>付款人：陈大文；汇款金额：人民币8800元</p>")
        assert n.payer_name == "陈大文"  # privacy-allow

    def test_no_payer_leaves_empty(self):
        assert parse_transfer_notice(body_html="<p>存入人民币100元</p>").payer_name == ""


class TestParseOnBehalf:
    def test_dai_xxx_fu(self):
        n = parse_transfer_notice(body_html="<p>【建行】张某存入人民币100元（代某公司付律师费）</p>")
        assert n.on_behalf_of == "某公司"

    def test_absent(self):
        n = parse_transfer_notice(body_html="<p>【建行】张某存入人民币100元</p>")
        assert n.on_behalf_of == ""


class TestEvidence:
    def test_evidence_records_raw_fragments(self):
        """evidence 是给人复核「系统从哪句读出来的」，必须留原文。"""
        n = parse_transfer_notice(body_html=REAL_HTML_ONBEHALF)
        joined = " ".join(n.evidence)
        assert "10000" in joined
        assert "张某" in joined  # privacy-allow
