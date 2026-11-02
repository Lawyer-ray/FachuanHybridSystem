"""银行回单（转账凭证）字段补全：短信句式解析之外的一层。

`PaymentSmsParser` 是按**到账短信句式**校准的（「【建设银行】张三10月26日13时32分
向贵公司4501账户存入人民币9000元。」）。银行 App / 网银导出的**电子回单**是完全
另一种版式：

    网上银行交易电子凭证
    交易时间:2026-11-02 14:17:07 交易状态：交易成功 网银流水：88880001
    付款人 户名:佛山市某某铝业有限公司 转出账号:6222XXXXXXXXXXXX
    收款人 户名:北京某某（广州）律师事务所 转入账号:6228XXXXXXXXXXXX
    金额: 25,000.00   大写: 贰万伍仟元正整   币种：人民币   用途：往来款

这种版式里有三件短信解析拿不到的东西，正是记账时最容易录错的三件：

1. **大写金额**（贰万伍仟元正整）——中文财务凭证里金额的可信锚点，与小写互为校验；
2. **日期带完整时分**（2026-11-02 14:17:07）——短信只有「14时17分」，且常跨年；
3. **付款人/收款人分栏**——表格里两栏都叫「户名」，不按栏位切就会把**自己律所**
   当成付款人（这正是回单识别最容易出的事故）。

本模块只做**纯文本 → 字段**的推导，不碰 IO、不碰 DB、不碰模型：输入是
`TextExtractionService` 拿到的 OCR/PDF 文本（已去空白），输出给 API 层合成草稿。
金额错一位是财务事故，所以每个字段都宁可留空也不猜（口径同 `PaymentSmsParser`）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

__all__ = [
    "ReceiptParse",
    "ReceiptTextParser",
    "chinese_amount_to_decimal",
]

#: 回单版式的特征词：命中两个以上才认为「这确实是银行回单」，避免把普通短信
#: 文本误判成回单（回单判定直接影响前端要不要提示「已按回单识别」）。
_RECEIPT_MARKERS: tuple[str, ...] = (
    "交易电子凭证",
    "电子回单",
    "电子凭证",
    "回单",
    "交易流水",
    "网银流水",
    "转出账号",
    "转入账号",
    "收款人账号",
    "付款人账号",
    "大写",
    "付方",
    "收方",
    "开户银行",
    "交易状态",
)

#: 分栏标签。回单表格里「户名」出现两次，必须靠这些栏位词定位归属。
_PAYER_LABEL = re.compile(r"(?:付款人|付款方|汇款人|汇款方|转出方|付方|出票人)")
_PAYEE_LABEL = re.compile(r"(?:收款人|收款方|收款单位|转入方|收方|入账方)")
#: 户名值：`户名:XX公司` / `付款人户名：XX公司`。值到下一个栏位词或行尾为止。
_NAME_AFTER_LABEL = re.compile(
    r"(?:户\s*名|名\s*称|全\s*称)\s*[:：]?\s*(?P<name>[^\s:：]{2,60}?)"
    r"(?=(?:转出账号|转入账号|账号|帐号|开户|开户银行|金额|币种|用途|摘要|附言|交易|大写|[，,；;]|$))"
)
#: 「付款人：XX公司」这种标签后直接跟名字（无「户名」二字）
_PARTY_DIRECT = re.compile(
    r"(?:付款人|付款方|汇款人|汇款方|转出方|付方|收款人|收款方|转入方|收方)\s*[:：]\s*(?P<name>[^\s:：]{2,60}?)(?=[\s，,；;]|$)"
)

#: 金额：`金额: 25,000.00` / `交易金额：￥25,000.00`。刻意不吃行里的其它数字
#: （流水号、账号都是长数字串，没有小数点且位数远超金额量级）。
_AMOUNT = re.compile(r"(?:交易金额|金额|发生额|转入金额)\s*[:：]?\s*[¥￥]?\s*(?P<num>[0-9][0-9,，]*(?:\.[0-9]{1,2})?)")
#: 大写金额：`大写:贰万伍仟元正整` / `(大写)贰万伍仟元整`
_UPPER_AMOUNT = re.compile(
    r"(?:大写|人民币大写|金额大写)\s*[:：]?\s*(?P<cn>[〇零壹贰叁肆伍陆柒捌玖拾佰仟万亿元圆角分整正圆]+)"
)

#: 完整日期：`2026-11-02 14:17:07` / `2026年11月2日 14时17分`
_DATETIME = re.compile(
    r"(?P<y>\d{4})\s*[-/年]\s*(?P<mo>\d{1,2})\s*[-/月]\s*(?P<d>\d{1,2})\s*日?"
    r"(?:[\sT]*(?P<h>\d{1,2})\s*[:：时]\s*(?P<mi>\d{1,2}))?"
)

#: 用途/摘要/附言：记账的备注就取这一栏（回单里最有价值的一行）。
#: 回单底部那段「提示1、已在银行柜台领用业务回单的客户…」是模板告示，OCR 出来
#: 会直接粘在用途值后面，所以值遇到「提示N」「电子印章」「打印时间」等后栏位词就截断。
_PURPOSE = re.compile(r"(?:用\s*途|摘\s*要|附\s*言|备\s*注|款项用途)\s*[:：]\s*(?P<v>[^\s，,；;]{1,80})")
_PURPOSE_TAIL = re.compile(
    r"(?:提示\s*\d|注意事项|电子印章|电子回单专用章|打印时间|交易时间|记账时间|经办人?|复核人?|币种|手续费|大写)"
)

#: 我方主体词：带这些词的户名是**自己律所**，绝不能当付款人
_SELF_WORDS = ("律师事务所", "律师所", "律所", "法律服务所")

# ── 中文大写金额表 ──────────────────────────────────────────────────────

_CN_DIGITS: dict[str, int] = {
    "〇": 0,
    "零": 0,
    "壹": 1,
    "贰": 2,
    "叁": 3,
    "肆": 4,
    "伍": 5,
    "陆": 6,
    "柒": 7,
    "捌": 8,
    "玖": 9,
}
_CN_UNITS: dict[str, int] = {"拾": 10, "佰": 100, "仟": 1000}
_CN_SECTIONS: dict[str, int] = {"万": 10_000, "亿": 100_000_000}


@dataclass(frozen=True)
class ReceiptParse:
    """回单推导结果。字段为 None/空表示没认出来（调用方留空让人手填）。"""

    amount: Decimal | None = None
    #: 大写金额换算出的数值（与小写不一致时前端要提示核对）
    upper_amount: Decimal | None = None
    received_at: date | None = None
    #: 交易时间原文（如 `14:17`），只进备注，不参与日期
    time_text: str = ""
    payer: str = ""
    payee: str = ""
    purpose: str = ""
    #: 是否为银行回单版式（命中标记词 ≥2）
    is_receipt: bool = False
    hints: list[str] = field(default_factory=list)

    @property
    def amount_mismatch(self) -> bool:
        """小写与大写金额对不上——财务场景必须让人核对。"""
        if self.amount is None or self.upper_amount is None:
            return False
        return self.amount != self.upper_amount


def chinese_amount_to_decimal(text: str) -> Decimal | None:
    """中文大写金额 → Decimal（`贰万伍仟元正整` → 25000.00）。

    只认财务凭证的标准写法（元/圆为分节符号，角/分在尾部）。整/正/正整是
    「无角分」的收尾词，不影响数值。解析不出或语义矛盾（如「零拾」）返回 None
    ——宁可不给，也不给一个错的数。
    """
    raw = (text or "").strip()
    if not raw:
        return None

    # 尾部收尾词「整 / 正 / 正整」与「元/圆」在数值之外
    body = re.sub(r"(?:整|正)+$", "", raw)
    body = body.replace("圆", "元")

    integer_part, _, fraction_part = body.partition("元")
    if not integer_part:
        return None

    total = 0
    section = 0  # 当前「万/亿」小节累计
    digit: int | None = None
    saw_unit = False

    for ch in integer_part:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
            continue
        if ch in _CN_UNITS:
            # 「拾」前缺省数字 = 1（拾万 / 拾元）
            unit = _CN_UNITS[ch]
            section += (1 if digit is None else digit) * unit
            digit = None
            saw_unit = True
            continue
        if ch in _CN_SECTIONS:
            mult = _CN_SECTIONS[ch]
            section += digit or 0
            total += (section if section else 1) * mult
            section = 0
            digit = None
            saw_unit = True
            continue
        return None  # 出现表外字符（含空格/标点）→ 认不出

    total += section + (digit or 0)

    if not saw_unit and digit is not None:
        # 只有单个数字（「伍」）在财务凭证里不合法
        return None
    if total <= 0:
        return None

    cents = 0
    if fraction_part:
        jiao = re.search(r"(?P<n>[〇零壹贰叁肆伍陆柒捌玖])角", fraction_part)
        fen = re.search(r"(?P<n>[〇零壹贰叁肆伍陆柒捌玖])分", fraction_part)
        if jiao:
            cents += _CN_DIGITS[jiao.group("n")] * 10
        if fen:
            cents += _CN_DIGITS[fen.group("n")]
    elif body != integer_part and re.fullmatch(r"[〇零]", fraction_part or ""):
        cents = 0

    try:
        return (Decimal(total) + Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):  # pragma: no cover - 防御
        return None


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").replace("，", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _clean_name(raw: str) -> str:
    return raw.strip(" 　，,。.、：:；;【】[]()（）")


def _is_self_entity(name: str) -> bool:
    return any(w in name for w in _SELF_WORDS)


class ReceiptTextParser:
    """银行回单文本 → 收款字段（纯函数，无 IO）。"""

    #: 备注长度上限（对齐 ContractPayment.note = 255）
    _NOTE_MAX = 255

    def parse(self, text: str) -> ReceiptParse:
        raw = (text or "").strip()
        if not raw:
            return ReceiptParse()

        # OCR 出来的回单常带全角空格与换行噪声：先归一化空白，保留引号与冒号
        normalized = re.sub(r"[ \u3000\t]+", " ", raw)
        compact = re.sub(r"\s+", "", normalized)

        markers_hit = sum(1 for m in _RECEIPT_MARKERS if m in compact)
        is_receipt = markers_hit >= 2
        hints: list[str] = []

        amount = self._parse_amount(compact)
        upper = self._parse_upper(compact)
        if amount is not None:
            hints.append(f"金额 {amount:,.2f}")
        if upper is not None:
            hints.append(f"大写 {upper:,.2f}")
            # 小写缺失时用大写兜底（回单上大写一定在，小写 OCR 有时糊）
            if amount is None:
                amount = upper
                hints.append("金额取自大写")

        received_at, time_text = self._parse_datetime(compact)
        if received_at is not None:
            label = f"{received_at.isoformat()} {time_text}".strip()
            hints.append(f"交易时间 {label}")

        payer, payee = self._parse_parties(normalized, compact)
        if payer:
            hints.append(f"付款人 {payer}")
        if payee:
            hints.append(f"收款人 {payee}")

        purpose = self._parse_purpose(compact)
        if purpose:
            hints.append(f"用途 {purpose[:20]}")

        return ReceiptParse(
            amount=amount,
            upper_amount=upper,
            received_at=received_at,
            time_text=time_text,
            payer=payer,
            payee=payee,
            purpose=purpose,
            is_receipt=is_receipt,
            hints=hints,
        )

    # ------------------------------------------------------------------ 字段

    def _parse_amount(self, compact: str) -> Decimal | None:
        for m in _AMOUNT.finditer(compact):
            value = _to_decimal(m.group("num"))
            # 0 元与上百亿只可能是误命中（流水号 / 账号）
            if value is not None and 0 < value < Decimal("1e10"):
                return value
        return None

    def _parse_upper(self, compact: str) -> Decimal | None:
        m = _UPPER_AMOUNT.search(compact)
        if not m:
            return None
        return chinese_amount_to_decimal(m.group("cn"))

    def _parse_datetime(self, compact: str) -> tuple[date | None, str]:
        m = _DATETIME.search(compact)
        if not m:
            return None, ""
        try:
            day = date(int(m.group("y")), int(m.group("mo")), int(m.group("d")))
        except ValueError:
            return None, ""
        h, mi = m.group("h"), m.group("mi")
        time_text = f"{int(h):02d}:{int(mi):02d}" if h and mi else ""
        return day, time_text

    def _parse_parties(self, normalized: str, compact: str) -> tuple[str, str]:
        """按栏位词切「付款人 / 收款人」两段，再各自取户名。

        回单表格的 OCR 顺序是「付款人 户名:甲 转出账号:… 收款人 户名:乙 转入账号:…」，
        所以按 **付款人标签出现的下标** 切一刀：刀前是付款人段，刀后是收款人段。
        这一刀是必要的——两栏都叫「户名」，不切就会把收款人（常是自己律所）当付款人。
        """
        payer_seg, payee_seg = self._split_segments(normalized, compact)

        payer = self._name_in(payer_seg)
        payee = self._name_in(payee_seg)

        # 兜底一：只有「付款人：XX」而无「户名」，用 direct 形态再试一次
        if not payer:
            payer = self._direct_name(payer_seg)
        if not payee:
            payee = self._direct_name(payee_seg)

        # 兜底二：切段失败（OCR 顺序乱）时，用「律所=自己」的常识纠正：
        # 若付款人看着是自己，而收款人是别人，说明取反了。
        if payer and _is_self_entity(payer) and payee and not _is_self_entity(payee):
            payer, payee = payee, payer
        elif payer and _is_self_entity(payer) and not payee:
            payer = ""

        return _clean_name(payer), _clean_name(payee)

    def _split_segments(self, normalized: str, compact: str) -> tuple[str, str]:
        """用付款人/收款人标签切两段；标签缺失时退化为「前半 / 后半」。"""
        for text in (compact, normalized):
            payer_m = _PAYER_LABEL.search(text)
            payee_m = _PAYEE_LABEL.search(text)
            if payer_m and payee_m and payer_m.start() < payee_m.start():
                return text[payer_m.start() : payee_m.start()], text[payee_m.start() :]
            if payee_m and not payer_m:
                return text[: payee_m.start()], text[payee_m.start() :]
        return "", ""

    def _name_in(self, segment: str) -> str:
        if not segment:
            return ""
        m = _NAME_AFTER_LABEL.search(segment)
        if not m:
            return ""
        return m.group("name")

    def _direct_name(self, segment: str) -> str:
        if not segment:
            return ""
        m = _PARTY_DIRECT.search(segment)
        return m.group("name") if m else ""

    def _parse_purpose(self, compact: str) -> str:
        m = _PURPOSE.search(compact)
        if not m:
            return ""
        value = m.group("v")
        # OCR 把模板告示粘在用途后面（「往来款提示1、已在银行柜台…」）：
        # 截到下一个后栏位词为止，只留真正的用途
        value = _PURPOSE_TAIL.split(value)[0]
        value = value.strip(" 　，,。.；;、：:")
        # 截断后只剩 1 个字（如「元」）说明本来就是噪声，宁可留空
        return value[:80] if len(value) > 1 else ""
