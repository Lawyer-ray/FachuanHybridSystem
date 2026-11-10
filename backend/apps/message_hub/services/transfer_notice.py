"""银行到账通知解析：HTML → 文本，再抽出金额 / 付款人 / 代付方。

## 为什么要重写 HTML → 文本

旧实现（``contract_match.build_mail_text``）用 ``re.sub(r"<[^>]+>", " ")`` 剥标签，
靠**插入的空格**把被 ``<span>`` 切碎的数字拼回来。真实邮件长这样
（Word 导出，数字被逐个包进 ``<span lang="EN-US">``）::

    【建设银行】李某<span lang="EN-US">11</span>月<span lang="EN-US">4</span>日
    ...存入人民币<span lang="EN-US">2400</span>元。

剥标签后 ``2400`` 恰好仍是连续字符，所以"碰巧能跑"。但只要银行换成
``2,400.00`` 或数字中间夹了别的行内标签，就会静默丢失金额——而金额是
认领流程的根本，丢了就没有任何可用信息。所以这里改成结构化转换：

- 块级标签 → 换行
- 行内标签 → **不插任何字符**（数字不会被拆开）
- ``<style>`` / ``<script>`` / ``<head>`` 整段跳过（Word 导出的 ``@font-face``
  噪声有一两千字符，塞进待匹配文本会让"合同名是否出现在正文里"这类判断失真）

## 解析失败要显式失败

抽不到金额 → 返回 ``None``，调用方跳过、不生成待认领记录。宁可什么都不出，
也不要造一条 ``amount=0`` 污染首页。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

# 整段跳过的标签（内容不是可见文本）
_SKIP_TAGS = {"style", "script", "head", "title", "xml"}

# 块级标签 → 换行
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "tr",
    "li",
    "ul",
    "ol",
    "table",
    "tbody",
    "thead",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "section",
    "article",
    "header",
    "footer",
}


class _TextExtractor(HTMLParser):
    """极薄的 HTML → 文本转换器（标准库，不引新依赖）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        # 行内标签不插东西：数字/日期不会被拆开
        self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        # 压掉连续空白，但保留换行结构（付款人/金额常在不同行）
        raw = re.sub(r"[ \t\u00a0]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def html_to_text(html: str) -> str:
    """把 HTML 转成保留换行的纯文本；非法 HTML 不抛错（解析器容错）。"""
    if not html:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # 标准库 HTMLParser 对畸形输入本应容错，兜一层防极端情况
        return re.sub(r"<[^>]+>", " ", html).strip()
    return parser.text()


# ── 金额 ──────────────────────────────────────────────────
# 真实邮件写法：「人民币2400元」「人民币 2,400.00 元」「¥2400」「10000.00元」
_AMOUNT_RES = (
    re.compile(r"(?:人民币|¥|￥)\s*([\d,]+(?:\.\d{1,2})?)\s*元?"),
    re.compile(r"([\d,]+(?:\.\d{1,2})?)\s*元"),
)
# 「账户4501」这类账号会被 元 正则误抽吗？不会——它后面没有「元」。
# 但「人民币2400元」里 2400 前面可能紧跟数字（如日期），所以抓取要求词边界。

# ── 代付：「（代某供应链公司付律师费）」 ──────────
_ON_BEHALF_RE = re.compile(r"代\s*([\u4e00-\u9fa5A-Za-z0-9（）()·]{2,60}?)\s*(?:付|付款|支付)")

# ── 付款人 ────────────────────────────────────────────────
# 真实格式：【建设银行】李某11月4日17时30分... / 【建设银行】张某11月8日10时31分...
# 即「【银行名】」紧跟「姓名」，姓名后接「N月N日」或数字。
# 姓名后面可能接的「时间词 / 动词」：昨日、今日、N月、N日、存入、汇入…
# 不把它们列进后向断言，就会把「张伟昨日向…」里的「昨日」吞进姓名。
_PAYER_AFTER_BANK_RE = re.compile(
    r"】\s*([\u4e00-\u9fa5]{2,20}?|[A-Za-z][A-Za-z\s.]{1,30}?)\s*(?:"
    r"昨日|前日|今日|今天|昨天|"
    r"\d{1,2}\s*月|\d{1,2}\s*[日号]|\d{4}|于|向|在|"
    r"存入|汇入|转入|付款|支付)"
)
# 兜底：正文里「付款人：XXX」
_PAYER_LABEL_RE = re.compile(r"付款人[:：]\s*([^\n;；,，]{2,40})")

# ── 到账日期：「11月4日17时30分」 ───────────────────────────
_MONTH_DAY_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


@dataclass
class TransferNotice:
    """一封到账通知的解析结果。"""

    amount: Decimal | None = None
    payer_name: str = ""
    on_behalf_of: str = ""
    received_at: date | None = None
    # 解析时命中的原文片段，便于人工复核「系统是从哪句读出来的」
    evidence: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """金额是认领的根本，抽不到即视为解析失败。"""
        return self.amount is not None and self.amount > 0


def _parse_amount(text: str) -> tuple[Decimal | None, str]:
    """抽金额。返回 (金额, 命中的原文片段)。

    多笔命中时取**最大值**：到账通知里最大的那个数通常就是本次转账额
    （较小数字常是账号尾号、时间、手续费）。多笔流水邮件不在一期范围。
    """
    found: list[tuple[Decimal, str]] = []
    for pattern in _AMOUNT_RES:
        for m in pattern.finditer(text or ""):
            raw = m.group(1).replace(",", "")
            try:
                value = Decimal(raw)
            except (InvalidOperation, ValueError):
                continue
            if value > 0:
                found.append((value, m.group(0)))
    if not found:
        return None, ""
    found.sort(key=lambda x: x[0], reverse=True)
    return found[0][0], found[0][1]


def parse_transfer_notice(*, subject: str = "", body_text: str = "", body_html: str = "") -> TransferNotice:
    """解析一封到账通知。

    优先用纯文本正文；为空时从 HTML 转换（真实 IMAP 邮件 ``body_text`` 常为空，
    正文只在 ``body_html`` 里）。主题并入搜索范围——银行常把关键信息写在标题。
    """
    text = (body_text or "").strip()
    if not text and body_html:
        text = html_to_text(body_html)
    # 主题也参与，但排在正文之后（正文的付款人格式更可靠）
    haystack = f"{subject or ''}\n{text}".strip()

    notice = TransferNotice()

    amount, amount_evidence = _parse_amount(text or haystack)
    notice.amount = amount
    if amount_evidence:
        notice.evidence.append(f"金额：{amount_evidence}")

    m = _ON_BEHALF_RE.search(haystack)
    if m:
        notice.on_behalf_of = m.group(1).strip()
        notice.evidence.append(f"代付：{m.group(0)}")

    payer = ""
    m = _PAYER_AFTER_BANK_RE.search(haystack)
    if m:
        payer = m.group(1).strip()
    if not payer:
        m = _PAYER_LABEL_RE.search(haystack)
        if m:
            payer = m.group(1).strip()
    notice.payer_name = payer
    if payer:
        notice.evidence.append(f"付款人：{payer}")

    m = _MONTH_DAY_RE.search(haystack)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            today = datetime.now().date()
            try:
                candidate = date(today.year, month, day)
            except ValueError:
                candidate = None
            if candidate is not None:
                # 跨年：邮件是 1 月发的但写「12月20日」→ 应归到上一年
                if candidate > today:
                    try:
                        candidate = date(today.year - 1, month, day)
                    except ValueError:
                        candidate = None
            if candidate is not None:
                notice.received_at = candidate
                notice.evidence.append(f"到账日：{m.group(0)}")

    return notice
