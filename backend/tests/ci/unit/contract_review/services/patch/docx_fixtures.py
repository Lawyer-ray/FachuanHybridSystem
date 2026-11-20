"""写补丁链路测试共用的 docx 夹具素材（不是测试模块，pytest 不会收集）。

三段互不相交的条款：够用来构造「互补」（各改一段）与「交叠」（两栏改同一段）
两种 patch，且每段原文在全文里只出现一次（区间定位唯一，见 conflict.py 的说明）。
"""

from __future__ import annotations

from io import BytesIO

from docx import Document

#: 绑定根下的相对路径（与 rewrite_folder_file 的 subpath 同口径）
SUBPATH = "1-合同/a.docx"

CLAUSE_PAYMENT = "甲方应于三十日内支付货款。"
CLAUSE_PENALTY = "逾期付款的，每日按未付金额的万分之五支付违约金。"
CLAUSE_COURT = "因本合同产生的争议，由合同签订地人民法院管辖。"


def make_docx(paragraphs: list[str] | None = None) -> bytes:
    """生成一份最小 docx（每段一段正文）。"""
    doc = Document()
    for text in paragraphs if paragraphs is not None else [CLAUSE_PAYMENT, CLAUSE_PENALTY, CLAUSE_COURT]:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
