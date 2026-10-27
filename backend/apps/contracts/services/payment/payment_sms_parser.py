"""银行到账短信 / 转账截图文字 → 收款草稿。

律师记收款的真实输入是**银行 App 的到账通知**，不是结构化表单：

    【建设银行】张三10月26日13时32分向贵公司4501账户存入人民币9000元。
    （代付甲方农业咨询有限公司(2026）诉讼案件代理律师费）

硬需求是「粘一段话 → 出金额/日期/付款人/摘要」四件事，其余字段留空让人补。
刻意**不做成 LLM 调用**：到账短信格式高度模板化，正则可离线、可单测、可解释，
而金额字段错一位是财务事故，不该交给概率模型猜。识别不出的字段一律留空
（前端展示「未识别，请手填」），绝不填默认值——默认值在财务场景等于错账。

解析口径的取舍（由真实建设银行短信校准）：

- **金额**优先取「人民币/¥/￥/元」紧邻的数字。金额必须带货币标记，否则
  `4501`（账号尾号）会被当成收款额。
- **日期**按月日解析并补年份；落在未来（1 月 2 日收到「12 月 31 日」的短信）
  视为去年，避免把去年 12 月的到账记成今年。
- **付款人/备注**：真实行文里信息量最大的是「4501账户**律师费**存入」中间的
  费用用途词，其次是括号里的「代九泰公司付律师服务费」。整句模板话术
  （"10月14日14时17分向贵公司…存入人民币30000元"）对记账零价值，不进备注。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

__all__ = ["PaymentTextParse", "PaymentSmsParser"]


@dataclass(frozen=True)
class PaymentTextParse:
    """解析结果。`amount` 为 None 表示没找到带货币标记的金额（调用方须让人手填）。"""

    amount: Decimal | None = None
    received_at: date | None = None
    payer: str = ""
    note: str = ""
    #: 识别依据（前端原样展示，让人一眼判断「它凭什么这么填」）
    hints: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.amount is not None and self.amount > 0


# 金额：人民币 9000 元 / ¥9,000.00 / 存入 9000.00 元 / RMB 9000
_AMOUNT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:人民币|RMB)\s*([0-9][0-9,，]*(?:\.[0-9]{1,2})?)"),
    re.compile(r"[¥￥]\s*([0-9][0-9,，]*(?:\.[0-9]{1,2})?)"),
    re.compile(r"(?:存入|转入|汇款|到账|收款|金额)[^0-9]{0,8}([0-9][0-9,，]*(?:\.[0-9]{1,2})?)\s*元"),
    re.compile(r"([0-9][0-9,，]*(?:\.[0-9]{1,2})?)\s*元(?![\u4e00-\u9fa5]{0,2}(?:账户|帐号))"),
)

# 带年份：2026年10月26日 / 2026-10-26 / 2026/10/26
_DATE_FULL = re.compile(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})")
# 无年份：「10月26日」与「10-26」是二选一的分支（分两个 group 取值）
_DATE_MD = re.compile(r"(?<![\d:])(\d{1,2})\s*(?:月\s*(\d{1,2})\s*日?|[-/](\d{1,2})(?!\d))")


def _md_groups(m: re.Match[str]) -> tuple[int, int]:
    day = m.group(2) or m.group(3)
    return int(m.group(1)), int(day)


# ── 模块级工具函数（原类内 @staticmethod，遵循 Service 层禁用 @staticmethod 约定）──


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").replace("，", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _extract_fee_label(text: str) -> str:
    m = _FEE_LABEL.search(text)
    if not m:
        return ""
    fee = m.group("fee").strip()
    return "" if _CHANNEL_WORD.match(fee) else fee


def _strip_transaction_boilerplate(text: str, *, payer: str) -> str:
    """把「【行】付款人10月15日17时5分向贵公司4501账户XXX存入人民币9000元」剥成 XXX。

    只对**前缀**做剥除、不动尾部：反过来做会把金额拆成 `人民币元` 这种碎片
    （`人民币12,500.00` 先被数字规则搞成 `人民币,.`）。
    """
    out = _BANK_PREFIX.sub("", re.sub(r"\s+", " ", text)).strip()
    if payer and out.startswith(payer):
        out = out[len(payer) :]
    # 前缀剥离：至「日 + 时间」为止
    out = re.sub(
        r"^(?:于|在)?\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*(?:\d{1,2}\s*[时:：]\s*\d{1,2}\s*分?)?",
        "",
        out,
    )
    out = re.sub(r"^(?:于|在)?\s*\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*日?\s*", "", out)
    out = re.sub(r"^.{0,6}?(?:向|给)(?:贵公司|我司|本公司|您|本单位)", "", out)
    out = re.sub(
        r"^(?:\d{2,}(?:账户|帐号|卡号)?)?\s*"
        r"(?:电子汇入|行内转账|跨行转账|转账|汇款|汇入|到账|存入|转入)?\s*(?:存入|转入|汇款)?",
        "",
        out,
    )
    out = re.sub(r"^\d{2,}(?:账户|帐号|卡号)?", "", out)
    out = re.sub(r"^(?:人民币|RMB|[¥￥])?\s*[0-9][0-9,，]*(?:\.[0-9]{1,2})?\s*元?", "", out)
    out = re.sub(r"^(?:存入|转入|汇款|到账|入账|电子汇入|汇入|转账)", "", out)
    out = out.strip(" 　，,。.；;（）()、：【】[]")
    # 剩下的若仍是「备注：xxx」这种命名摘要，取冒号后的内容
    labeled = re.match(r"^(?:备注|用途|摘要|附言|留言)\s*[:：]\s*(?P<x>.+)$", out)
    if labeled:
        out = labeled.group("x").strip(" 　，,。.；;")
    return "" if len(out) <= 1 else out


def _clean_party(raw: str) -> str:
    return raw.strip(" 　，,。.、：:；;【】[]()（）")


# 付款人：A向贵公司/我司…存入；收到 A 转入；显式「付款人：A」
_PAYER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(?P<payer>[^\s，,。（(]{2,30}?)\s*(?:于|在)?\s*\d{1,2}\s*月?\s*\d{0,2}\s*日?.{0,20}?向.{0,12}?(?:存入|转入|汇款)"
    ),
    re.compile(r"^(?P<payer>[^\s，,。（(]{2,30}?)\s*(?:向|给).{0,12}?(?:存入|转入|支付|汇款)"),
    re.compile(r"(?:付款人|汇款人|付款方|汇款方)[：:]\s*(?P<payer>[^\s，,。]{2,30})"),
    re.compile(r"(?:收到|来自)\s*(?P<payer>[\u4e00-\u9fa5A-Za-z·]{2,30}?)\s*(?:转入|汇款|存入)"),
)

# 括号摘要。真实行文有「（代某房地产公司付律师服务费）」「（某某甲第二轮的律师费）」
# 以及「（代付XX公司顾问费）」——前缀动词可有可无，不能用必选 group。
_MEMO_PARENS = re.compile(
    r"[（(]\s*(?:代付|代收|委托付款|付款用途|用途|摘要)?\s*[:：]?\s*(?P<memo>[^（）]{2,160})\s*[）)]"
)

# 交易描述中夹带的**费用用途词**：`4501账户律师费存入人民币9000元` 里的「律师费」。
# 真实短信里信息量最大的一段——直接说明这笔钱是什么费，比整句模板有用得多。
_FEE_LABEL = re.compile(
    r"(?:账户|帐号|卡|尾号\s*\d{0,8}|电子汇入|汇入|存入|转入)"
    r"\s*(?P<fee>"
    r"(?:诉讼|仲裁|顾问|服务|代理|辩护|执行|专项|常年|法律|律师|公证|咨询)"
    r"[\u4e00-\u9fa5]{0,6}?费"
    r"|代理费|律师费|服务费|顾问费|公证费|咨询费|诉讼费\s*)"
)
# 「电子汇入 / 行内转账」等渠道词：只说钱怎么来的，不说明为什么付，不是摘要
_CHANNEL_WORD = re.compile(
    r"^(?:电子汇入|汇入|行内转账|跨行转账|网上转账|网上银行|手机银行|转账|汇款|存入|转入|入账|收款)$"
)

# 银行名（仅作提示展示，不落库）
_BANK = re.compile(r"[【\[]\s*(?P<bank>[\u4e00-\u9fa5]{2,12}银行[\u4e00-\u9fa5]{0,6})\s*[】\]]")
# 开头的银行名/括号标记（认付款人前先剥掉，否则「【建设银行】张三」会被整段当付款人）
_BANK_PREFIX = re.compile(
    r"^\s*(?:[【\[]\s*[\u4e00-\u9fa5]{2,16}(?:银行|信用社)[\u4e00-\u9fa5]{0,6}\s*[】\]]\s*[:：]?"
    r"|[\u4e00-\u9fa5]{2,16}(?:银行|信用社)\s*[:：]\s*)"
)
# 句首常见的非主体词，不当付款人
_NON_PARTY_WORDS = frozenset(
    {"您账户", "您的账户", "您尾号", "收款确认", "到账通知", "入账通知", "账户", "贵公司", "尊敬"}
)


class PaymentSmsParser:
    """把一段到账短信/截图文字解析成收款草稿（纯函数，无 IO）。"""

    #: 无年份日期落在「今天之后多少天内」仍算今年（容忍银行延迟 / 当天稍后）
    _FUTURE_TOLERANCE_DAYS = 3
    #: 备注/付款人长度上限（对齐 ContractPayment.note = 255）
    _NOTE_MAX = 255
    _PAYER_MAX = 60

    def parse(self, text: str, *, today: date | None = None) -> PaymentTextParse:
        raw = (text or "").strip()
        if not raw:
            return PaymentTextParse()

        ref_day = today or date.today()
        hints: list[str] = []

        amount = self._parse_amount(raw)
        if amount is not None:
            hints.append(f"金额 {amount:,.2f}")

        received_at = self._parse_date(raw, ref_day)
        if received_at is not None:
            hints.append(f"日期 {received_at.isoformat()}")

        bank_m = _BANK.search(raw)
        if bank_m:
            hints.append(f"开户行 {bank_m.group('bank')}")

        payer = self._parse_payer(raw)
        note = self._parse_note(raw, payer=payer)
        if payer:
            hints.append(f"付款人 {payer}")
        if note:
            hints.append(f"备注 {note[:20]}{'…' if len(note) > 20 else ''}")

        return PaymentTextParse(
            amount=amount,
            received_at=received_at,
            payer=payer,
            note=note[: self._NOTE_MAX],
            hints=hints,
        )

    # ------------------------------------------------------------------ 字段

    def _parse_amount(self, text: str) -> Decimal | None:
        for pattern in _AMOUNT_PATTERNS:
            for m in pattern.finditer(text):
                value = _to_decimal(m.group(1))
                # 0 元与上百亿的值只可能是误命中（账号、流水号）
                if value is not None and 0 < value < Decimal("1e10"):
                    return value
        return None

    def _parse_date(self, text: str, today: date) -> date | None:
        m = _DATE_FULL.search(text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y, mo, d)
            except ValueError:
                pass  # 落到月日分支

        m = _DATE_MD.search(text)
        if not m:
            return None
        mo, d = _md_groups(m)
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return None
        try:
            candidate = date(today.year, mo, d)
        except ValueError:
            return None
        # 短信不写年份：**落在未来**的月日只可能是去年（1 月 2 日收到「12 月 31 日」）。
        # 小容差是刻意的——当天稍后 / 银行延迟不该跳到一年前。
        if (candidate - today) > timedelta(days=self._FUTURE_TOLERANCE_DAYS):
            try:
                candidate = date(today.year - 1, mo, d)
            except ValueError:
                return None
        return candidate

    def _parse_payer(self, text: str) -> str:
        body = _BANK_PREFIX.sub("", text)
        for pattern in _PAYER_PATTERNS:
            m = pattern.search(body)
            if not m:
                continue
            payer = _clean_party(m.group("payer"))
            if payer and not payer.startswith(("贵公司", "您", "我")) and not payer[0].isdigit():
                return payer[: self._PAYER_MAX]

        # 句式不认识时兜底：去掉银行名后**开头**的第一个 token 视为付款人。
        # 只认开头——正文中段的公司名多半是备注里的关联主体，认错人比认不出伤害大。
        head = re.match(r"^(?P<name>[\u4e00-\u9fa5A-Za-z·]{2,20}?)(?=于|在|向|：|:|\s|\d)", body)
        if head:
            name = head.group("name")
            if name not in _NON_PARTY_WORDS and not name.endswith("银行"):
                return name[: self._PAYER_MAX]
        return ""

    def _parse_note(self, text: str, *, payer: str) -> str:
        """备注优先级：括号摘要 > 交易描述里的费用用途词 > 去模板后的残留。

        不把「电子汇入 / 行内转账」这类渠道词当摘要——对律所记账它们是噪声，
        宁可备注留空让人手填。
        """
        m = _MEMO_PARENS.search(text)
        if m:
            memo = re.sub(r"\s+", " ", m.group("memo")).strip(" 　，,。.、；;（()）")
            if memo:
                return self._strip_payer(memo, payer)

        fee = _extract_fee_label(text)
        if fee:
            return fee

        return _strip_transaction_boilerplate(text, payer=payer)

    def _strip_payer(self, note: str, payer: str) -> str:
        """备注里去掉重复的付款人名（事后读备注不需要再念一遍汇款人）。"""
        if not payer or not note.startswith(payer):
            return note
        rest = note[len(payer) :].lstrip(" 　，,、：:")
        return rest or note
