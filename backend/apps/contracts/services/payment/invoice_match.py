"""发票待认领 → 项目 / 收款 的候选匹配（v1）。

## 与到账匹配（``contract_match_v2``）的关系

同构但不共享代码：到账通知的强信号是「付款人 + 银行备注」，发票的强信号是
**备注/文件名里印着的律所项目号**——发票备注栏由律师自己填，项目号一旦印上去
就是确定命中，比到账那边任何信号都硬。所以这里另立四级信号，不复用到账的权重。

## 四级信号（按优先级）

    S1  项目号命中      ``Contract.law_firm_oa_case_number == project_code``   score 1.0
    S2  案由文字命中    备注/文件名里的文字 vs 合同名（归一化后包含或高相似）  score 0.7
    S3  购买方命中委托人 ``ContractParty.client.name``（归一化后相等/包含）    score 0.5
    S4  金额 + 日期     只在 S1–S3 已定合同后，用来选**具体那笔收款**

**S4 不单独构成候选**：仅金额撞上「恰好 2400」的真实命中率高得可怕（任何一笔
2400 元的收款都会撞），若让它独立拉候选，候选列表会被纯巧合污染。它的位置是
``choose_payment``——合同已由人/S1–S3 定下之后，再帮人挑那笔收款。

## 多形态项目号

真实样本只见过 ``2025GZM0001``（年份 + GZ + 1 位字母 + 4 位序号），但项目号样式  # privacy-allow 虚构样例，非真实项目号
会随律所编号规则变化，**不写死单一形态**：``_PROJECT_CODE_PATTERNS`` 按优先级列出
主形态与备选形态，``extract_project_code_candidates`` 把所有命中都返回。主形态
先匹配、命中的区间会被备选形态跳过，避免 ``2025GZM0001`` 同时被备选形态切成  # privacy-allow 虚构样例，非真实项目号
``2025GZM034``。  # privacy-allow 虚构样例，非真实项目号

## 本模块不做的事

**不写任何数据。** 输出只是「建议 + 依据 + 被排除的线索」，最终归属由人在
待认领页确认（同 ``PaymentIntake``：每一笔都要人工确认）。
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.contracts.services.payment.intake_eligibility import (
    eligible_contract_qs,
    excluded_note,
    ineligible_reason,
    with_paid_total,
)
from apps.contracts.services.payment.invoice_filename import mask_personal_name

if TYPE_CHECKING:
    from apps.contracts.models import Contract

logger = logging.getLogger("apps.contracts")

MATCHER_VERSION = "v1"

# ── 信号类别与分数 ─────────────────────────────────────────
KIND_PROJECT_CODE = "project_code"
KIND_CASE_TEXT = "case_text"
KIND_PARTY_NAME = "party_name"

SCORE_PROJECT_CODE = 1.0
SCORE_CASE_TEXT = 0.7
SCORE_PARTY_NAME = 0.5

#: 类别排序（同级内按分数降序）。只为排序服务，不参与展示分数。
_KIND_ORDER: dict[str, int] = {KIND_PROJECT_CODE: 0, KIND_CASE_TEXT: 1, KIND_PARTY_NAME: 2}

#: 「金额吻合」的绝对容差：2400 与 2400.00 视为同一笔。
AMOUNT_TOLERANCE = Decimal("0.005")

#: 案由文字相似度下限（difflib 比例）。只有包含关系不够时（备注只写了案由简称），
#: 才靠相似度兜。低于此值说明不是同一件事，不能当 S2 证据。
CASE_TEXT_MIN_RATIO = 0.6

#: S2 比较的最短长度。两三个字的片段互相包含毫无意义（「合同」「纠纷」），
#: 会把几乎所有合同都拉成候选。
CASE_TEXT_MIN_LENGTH = 4

#: 购买方名称参与比较的最短长度。单字姓名（「何」）包含匹配会命中一大片。
PARTY_NAME_MIN_LENGTH = 2

#: 案由文字比较时从备注/文件名里剔除的噪声片段：项目号本身、
#: 律所项目号与对手方之间的分隔词（真实样本 ``2025GZM0001-张三与广东某公司合同纠纷;``  # privacy-allow 虚构样例，非真实项目号
#: 里的「与」不属于案由），以及常见的款项/文书类后缀。
_CASE_TEXT_NOISE = re.compile(r"与|合同纠纷|纠纷|律师费|代理费|服务费|发票|开具|开票|项目号")

#: 项目号形态，**按优先级排列**。每个 pattern 的第 1 组是项目号本体。
#:
#: 主形态 ``2025GZM0001``：年份 4 位 + 律所标识（GZ）+ 1 位业务字母 + 4 位序号。  # privacy-allow 虚构样例，非真实项目号
#: 备选 ``2025GZMB0034``：业务字母可能不止 1 位，序号 3–6 位。  # privacy-allow 虚构样例，非真实项目号
#: 边界一律写「前后不是字母数字」而不是 ``\\b``：项目号在文件名里前后紧贴下划线、
#: 在备注里紧贴 ``-`` 与汉字，``\\b`` 在这些位置不会命中（同 ``invoice_filename`` 的教训）。
_PROJECT_CODE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![0-9A-Za-z])(\d{4}GZ[A-Z]\d{4})(?![0-9A-Za-z])"),
    re.compile(r"(?<![0-9A-Za-z])(\d{4}GZ[A-Z]{1,2}\d{3,6})(?![0-9A-Za-z])"),
)

#: 收款预选置信度（用户已确认的四级规则，不得改）
CONFIDENCE_EXACT = "exact"
CONFIDENCE_AMOUNT_MISMATCH = "amount_mismatch"
CONFIDENCE_AMBIGUOUS = "ambiguous"
CONFIDENCE_NO_PAYMENT = "no_payment"
#: 红票专用两档：红票永远不预选收款，只说明「冲的是哪张票 / 原票不在库里」
CONFIDENCE_RED_OFFSET = "red_offset"
CONFIDENCE_RED_UNMATCHED = "red_unmatched"

NOTE_AMOUNT_MISMATCH = "金额与收款不符"
NOTE_AMBIGUOUS = "多笔收款，请自选"
NOTE_NO_PAYMENT = "先开票后付款"
NOTE_RED_OFFSET = "红字发票（冲 {number}）"
NOTE_RED_UNMATCHED = "红字发票，被冲销的原票不在系统里"

#: 候选上限（待认领详情页够用）
MAX_CANDIDATES = 5

#: ``excluded_hints`` 上限：只保留有人名/项目号证据的，最多 5 条
MAX_EXCLUDED_HINTS = 5


# ── 纯函数：项目号抽取 ─────────────────────────────────────


def extract_project_code_candidates(text: str) -> list[str]:
    """从任意文本（备注、文件名）里抽出所有**项目号样式**的片段。

    纯函数：无 IO、无 DB、不抛异常。按文本出现顺序返回、已去重，保持原文大小写。

    优先级：主形态先扫，命中的区间会被后续（更宽松的）形态跳过。否则
    ``2025GZM0001`` 会同时被备选形态切成 ``2025GZM034`` 一起返回，  # privacy-allow 虚构样例，非真实项目号
    调用方就分不清哪个才是真项目号。
    """
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    taken: list[tuple[int, int]] = []

    for pattern in _PROJECT_CODE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            if any(start < taken_end and taken_start < end for taken_start, taken_end in taken):
                continue
            taken.append((start, end))
            value = match.group(1)
            if value not in seen:
                seen.add(value)
                found.append(value)
    return found


# ── 纯函数：文本归一化与相似度 ─────────────────────────────


def normalize_text(text: str) -> str:
    """归一化供比较：全角转半角、去空白、去标点，只留文字与数字。

    真实样本的差异全在这几类：``2025GZM0001-张三与广东某公司合同纠纷;`` 与合同名  # privacy-allow 虚构样例，非真实项目号
    ``张三与广东某公司合同纠纷案`` 差在破折号/分号/「案」字；发票买方写成
    ``深圳市某某铝业（普通合伙）`` 而客户档案是半角括号。不归一化，S2/S3 全都失效。
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).upper()
    return "".join(ch for ch in folded if ch.isalnum())


def case_text_similarity(left: str, right: str) -> float:
    """两段文字（通常是备注/文件名里的案由 与 合同名）的相似度，0.0–1.0。

    先做归一化与噪声剔除，再按「互相包含」或 ``difflib`` 比例给出分数。
    纯函数，空输入返回 0.0（空串之间的相似度没有意义，不能给 1.0）。
    """
    a = _case_text_key(left)
    b = _case_text_key(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= CASE_TEXT_MIN_LENGTH and shorter in longer:
        return 1.0

    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    # 短片段撞长文本时 difflib 会给出虚高的比例（分母是两者长度和），
    # 用长度占比压一下，避免「三个字恰好都出现」就够到 0.6。
    coverage = len(shorter) / len(longer)
    return ratio * min(1.0, coverage * 2)


def names_match(left: str, right: str) -> bool:
    """购买方名称是否命中委托人姓名/公司名（归一化后相等或互相包含）。

    纯函数。过短的名字不参与包含匹配：真实数据里有单字/两字客户名，
    包含匹配会把它们撞到一大片合同上。
    """
    a = normalize_text(mask_personal_name(left or ""))
    b = normalize_text(mask_personal_name(right or ""))
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= PARTY_NAME_MIN_LENGTH and shorter in longer


def _case_text_key(text: str) -> str:
    """S2 比较用的文字：归一化 + 剔除项目号与分隔噪声后的剩余文字。"""
    if not text:
        return ""
    stripped = unicodedata.normalize("NFKC", text).upper()
    for code in extract_project_code_candidates(text):
        stripped = stripped.replace(unicodedata.normalize("NFKC", code).upper(), "")
    stripped = _CASE_TEXT_NOISE.sub("", stripped)
    return "".join(ch for ch in stripped if ch.isalnum())


# ── 纯函数：收款预选（四级规则，用户已确认） ────────────────


def choose_payment(
    contract_id: int,
    total_amount: Decimal | None,
    invoice_date: date | None,
    is_red: bool = False,
    red_against_number: str = "",
    red_offset_found: bool | None = None,
) -> dict[str, Any]:
    """在**已定合同**下预选那笔收款。四个分支是用户确认过的规则，不得改。

    ① 恰好 1 笔且金额吻合        → 选它，``exact``
    ② 恰好 1 笔但金额不符        → 仍选它，``amount_mismatch``（提醒人核金额）
    ③ 多笔                        → 不猜，``ambiguous``，让人自选
    ④ 无收款                      → ``no_payment``（先开票后付款是常见顺序）

    分支②之所以"明知不符还选"，是因为开票金额与收款金额经常不相等（含税/分期/
    多笔合并开票），让人从零开始选比「选好再改」更费事；``confidence`` 负责把
    这层不确定说清楚。

    ``is_red``：红票**永远不预选收款**。冲销不是一个新的记账动作，它只是把原票
    抵掉；预选一笔收款会诱导人把红票当新票挂上去（帐上就多一笔支出）。红票也
    不会报 ``amount_mismatch``——金额没识别或本来就为负，说「金额与收款不符」
    指错了方向，真实信息是「这是红票」。

    ``red_against_number`` / ``red_offset_found`` 是**扫描层才能知道的两个事实**：
    红票备注栏里印着的被冲票号，以及该票号是否已在 ``Invoice`` 里命中。
    本函数是纯判定、不查这两件事（扫一次库只为拼文案不值得，且会让纯函数带 IO）。

    ⚠️ 这两个参数必须由调用方传真实值。历史实现曾试图用「该合同唯一那笔收款
    已挂的发票号」兜底推导被冲票号，结果**恒为空**（收款上的票号是收款自己的票，
    不是红票要冲的票），于是所有红票都被判成 ``red_unmatched``，
    「原票在库、可一键冲红」被误报成「需人工处理」。已改为显式传入。

    ``invoice_date`` **不参与判定**：发票日期与到账日期没有可靠的先后关系
    （先开票后付款 / 先付款后补票都真实存在），拿它拉候选只会制造误导。
    参数保留是因为调用方（待认领扫描）手里就有这个事实，且后续若真人拍定了
    「开票日期 ≤ 到账日」之类规则可直接用；当前实现不读它。
    """
    from apps.contracts.models import ContractPayment

    payments = list(
        ContractPayment.objects.filter(contract_id=contract_id)
        .order_by("received_at", "id")
        .values("id", "amount", "received_at", "note")
    )
    options = [
        {
            "id": int(row["id"]),
            "amount": str(row["amount"]),
            "received_at": row["received_at"].isoformat() if row["received_at"] else None,
            "note": str(row["note"] or ""),
        }
        for row in payments
    ]

    if is_red:
        # 调用方没给「原票是否命中」时，退化为按票号有无判：有票号但无法确认命中，
        # 仍给 unmatched（宁可让人确认一次，也不要谎称「原票在库」）。
        found = bool(red_offset_found) if red_offset_found is not None else False
        return _red_pick(
            red_against_number=red_against_number.strip() if found else "",
            payment_options=options,
            unmatched_number=red_against_number.strip(),
        )

    if not options:
        return {
            "suggested_payment_id": None,
            "confidence": CONFIDENCE_NO_PAYMENT,
            "note": NOTE_NO_PAYMENT,
            "payment_options": [],
        }

    if len(options) > 1:
        return {
            "suggested_payment_id": None,
            "confidence": CONFIDENCE_AMBIGUOUS,
            "note": NOTE_AMBIGUOUS,
            "payment_options": options,
        }

    only = options[0]
    same_amount = _amounts_match(only["amount"], total_amount)
    # 分支①②都选中这唯一一笔，差别只在 confidence / note：金额不符**不是不选它**，
    # 而是把这层不确定显式说出来（开票额与收款额经常不等：含税、分期、合并开票）。
    return {
        "suggested_payment_id": only["id"],
        "confidence": CONFIDENCE_EXACT if same_amount else CONFIDENCE_AMOUNT_MISMATCH,
        "note": "" if same_amount else NOTE_AMOUNT_MISMATCH,
        "payment_options": options,
    }


def _red_pick(
    *, red_against_number: str, payment_options: list[dict[str, Any]], unmatched_number: str = ""
) -> dict[str, Any]:
    """红票的预选结果：收款恒为 None，置信度按「原票是否在库」分两档。

    ``red_against_number`` 仅在**原票已在本库命中**时才由调用方给出；
    未命中时即便票面印了票号，也只是 `red_unmatched`——
    「票面写着冲 XXX」与「XXX 真的在系统里」是两件事，混淆会让人以为可以一键冲红。
    未命中时仍把票号写进文案（`unmatched_number`），人能据此去补录原票。
    """
    if red_against_number:
        return {
            "suggested_payment_id": None,
            "confidence": CONFIDENCE_RED_OFFSET,
            "note": NOTE_RED_OFFSET.format(number=red_against_number),
            "payment_options": payment_options,
        }
    return {
        "suggested_payment_id": None,
        "confidence": CONFIDENCE_RED_UNMATCHED,
        "note": (f"红字发票，冲 {unmatched_number}（原票不在系统里）" if unmatched_number else NOTE_RED_UNMATCHED),
        "payment_options": payment_options,
    }


def _amounts_match(left: Any, right: Decimal | None) -> bool:
    """金额是否吻合（绝对容差 0.005）。任一侧缺失视为不吻合——缺金额不是证据。"""
    if right is None:
        return False
    try:
        return abs(Decimal(str(left)) - Decimal(str(right))) < AMOUNT_TOLERANCE
    except (InvalidOperation, TypeError, ValueError):
        return False


# ── 候选打分（纯函数，只读传入的合同对象） ─────────────────


@dataclass
class InvoiceCandidate:
    contract_id: int
    contract_name: str
    kind: str
    score: float
    reasons: list[str] = field(default_factory=list)
    caveat: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_name": self.contract_name,
            "kind": self.kind,
            "score": self.score,
            "reasons": self.reasons,
            "caveat": self.caveat,
        }


def principal_names(contract: Any) -> list[str]:
    """合同的**委托人**名称（``role == PRINCIPAL``）。

    只认委托人：购买方是客户本人或客户公司，对方当事人几乎不可能出现在
    发票购买方一栏，把它们算进来只会制造误命中。
    """
    names: list[str] = []
    manager = getattr(contract, "contract_parties", None)
    if manager is None:
        return names
    for party in manager.all():
        if str(getattr(party, "role", "") or "") != "PRINCIPAL":
            continue
        client = getattr(party, "client", None)
        name = str(getattr(client, "name", "") or "").strip()
        if name:
            names.append(name)
    return names


def score_contract_for_invoice(
    *,
    contract: Any,
    project_codes: list[str],
    case_text: str,
    buyer_name: str,
    today: date | None = None,
) -> InvoiceCandidate | None:
    """给单个**合格**合同打 S1–S3 分。纯函数，不写库、不查库。

    一个信号都没命中返回 ``None``（不进候选）。S4（金额/日期）刻意不在这里——
    它不能单独构成候选，见模块文档。
    """
    contract_id = int(getattr(contract, "id", 0) or 0)
    contract_name = str(getattr(contract, "name", "") or "")

    score = 0.0
    reasons: list[str] = []
    kinds: list[str] = []

    # S1：项目号命中律所 OA 案件编号（该字段唯一，命中即确定）
    oa_number = str(getattr(contract, "law_firm_oa_case_number", "") or "").strip()
    hit_codes = [code for code in project_codes if oa_number and code.upper() == oa_number.upper()]
    if hit_codes:
        score += SCORE_PROJECT_CODE
        reasons.append(f"项目号命中 {hit_codes[0]}")
        kinds.append(KIND_PROJECT_CODE)

    # S2：备注/文件名里的案由文字 vs 合同名
    similarity = case_text_similarity(case_text, contract_name)
    if similarity >= CASE_TEXT_MIN_RATIO:
        score += SCORE_CASE_TEXT
        reasons.append(f"案由文字命中合同名「{contract_name[:16]}」")
        kinds.append(KIND_CASE_TEXT)

    # S3：购买方命中委托人
    if buyer_name:
        hit = [name for name in principal_names(contract) if names_match(buyer_name, name)]
        if hit:
            score += SCORE_PARTY_NAME
            reasons.append(f"购买方命中委托人「{hit[0]}」")
            kinds.append(KIND_PARTY_NAME)

    if not kinds:
        return None

    return InvoiceCandidate(
        contract_id=contract_id,
        contract_name=contract_name,
        # 取命中的最高优先级类别（kinds 是按 S1→S3 追加的，取首个即可）
        kind=kinds[0],
        score=min(score, 1.0),
        reasons=reasons,
        caveat=_contract_caveat(contract, today=today),
    )


def rank_candidates(candidates: list[InvoiceCandidate], *, limit: int = MAX_CANDIDATES) -> list[InvoiceCandidate]:
    """按类别优先级排序，同类内分数降序，最后按 contract_id 稳定。

    类别优先而不是纯分数：S1 单独命中（1.0）必然压过 S2+S3（1.2 的算术和）——
    所以分数先按类别封顶，排序键用 (类别, -分数)，避免"两个弱信号叠加"盖过
    一个确定信号。
    """
    ranked = list(candidates)
    ranked.sort(key=lambda c: (_KIND_ORDER.get(c.kind, 9), -c.score, c.contract_id))
    return ranked[:limit]


def _contract_caveat(contract: Any, *, today: date | None = None) -> str:
    """到期合同降权不排除（同到账匹配）：顾问合同到期后续费打款是真实场景。"""
    end_date = getattr(contract, "end_date", None)
    if not end_date:
        return ""
    current = today or timezone.localdate()
    if end_date < current:
        return f"合同已于 {end_date.isoformat()} 到期"
    return ""


# ── 对外入口 ───────────────────────────────────────────────


def rank_invoice_candidates(
    *,
    project_code: str,
    buyer_name: str,
    remark: str,
    original_filename: str = "",
    limit: int = MAX_CANDIDATES,
) -> dict[str, Any]:
    """给一张待认领发票算出候选项目 + 被排除线索。

    返回结构对应 ``InvoiceIntake.match_snapshot``：不可变快照，便于事后追责与调参。
    **不写任何数据**，纯只读。

    资格过滤一律走 ``intake_eligibility.eligible_contract_qs()``——与前端
    「换个项目」下拉共用同一份口径，禁止在这里再写一遍过滤条件。

    注意传的是 ``exclude_fully_paid=False``：发票与到账对「已收满」的判断相反
    （发票在钱收齐后开是正常顺序），详见该参数的文档。

    Args:
        project_code: 已抽取的律所项目号（可能为空）。
        buyer_name: 发票购买方名称。
        remark: 发票备注栏原文。
        original_filename: 附件原始文件名（项目号也常印在这里）。
        limit: 候选上限。
    """
    codes: list[str] = []
    for value in extract_project_code_candidates(project_code):
        codes.append(value)
    # 备注与文件名里的项目号同样有效：律师常把项目号写在备注栏，税务平台
    # 又把项目号印在附件名里，两处都抽、统一去重。
    for source in (remark, original_filename):
        for value in extract_project_code_candidates(source or ""):
            if value not in codes:
                codes.append(value)

    # 案由文字 = 备注 + 文件名去掉项目号后的剩余文字
    case_text = "\n".join(part for part in (remark or "", original_filename or "") if part).strip()

    eligible = list(
        # exclude_fully_paid=False：发票场景里「已收满」不是排除理由而是**强信号**
        # ——钱收齐了就该开票。沿用到账口径会把「收满且未开票」的项目全部误杀。
        eligible_contract_qs(exclude_fully_paid=False)
        .prefetch_related("contract_parties__client")
        .only(
            "id",
            "name",
            "status",
            "fixed_amount",
            "fee_mode",
            "end_date",
            "law_firm_oa_case_number",
        )
    )
    eligible_ids = {int(contract.id) for contract in eligible}

    candidates: list[InvoiceCandidate] = []
    for contract in eligible:
        candidate = score_contract_for_invoice(
            contract=contract,
            project_codes=codes,
            case_text=case_text,
            buyer_name=buyer_name or "",
        )
        if candidate is not None:
            candidates.append(candidate)

    ranked = rank_candidates(candidates, limit=limit)

    # 只有“证据不够硬”时才需要线索来解释。已拿到项目号确定性命中时，
    # 再罗列同名的归档/结案项目只是噪声（实测：项目号命中某买卖合同案，
    # 旁边却挂着同一客户的三份已归档案——律师一眼就知道无关，白占地方）。
    # 款项侧保留线索是因为那边证据本来就弱（只有姓名+金额）；发票侧证据
    # 强到 1.0 时，多余的解释反而干扰。
    has_deterministic = any(c.kind == "project_code" for c in ranked)
    excluded_hints = (
        []
        if has_deterministic
        else collect_excluded_hints(project_codes=codes, buyer_name=buyer_name or "", eligible_ids=eligible_ids)
    )

    return {
        "matcher_version": MATCHER_VERSION,
        "computed_at": timezone.localtime().isoformat(),
        "candidates": [c.as_dict() for c in ranked],
        "excluded_hints": excluded_hints,
        "top_contract_id": ranked[0].contract_id if ranked else None,
        "project_codes": codes,
    }


def collect_excluded_hints(
    *, project_codes: list[str], buyer_name: str, eligible_ids: set[int]
) -> list[dict[str, Any]]:
    """收集被资格规则排除、但**有项目号或购买方证据**的项目。

    与到账匹配的 ``excluded_hints`` 同结构（``contract_id/contract_name/excluded_by/note``）：
    既执行「收满/结案/归档不匹配」，又不丢线索——人需要知道"系统想到过这个项目，
    因为 X 排除了"，否则会以为功能没在跑。

    无任何证据的已归档项目一律不收：库里有几十份归档合同，全列出来就是噪声。

    ❗ 只在**没有确定性匹配**时才有意义（调用方控制，见 `rank_invoice_candidates`）。
    项目号已经精确命中时，再挂一堆同名归档案只是干扰。
    """
    if not project_codes and not buyer_name:
        return []

    from apps.contracts.models import Contract

    hints: list[dict[str, Any]] = []
    # 走 with_paid_total：excluded_note 要显示「已收 X / 应收 Y」，没有注解得再打 N+1 聚合。
    qs = (
        with_paid_total(Contract.objects.exclude(id__in=eligible_ids))
        .prefetch_related("contract_parties__client")
        .only("id", "name", "status", "fixed_amount", "law_firm_oa_case_number")
    )
    for contract in qs:
        reason = ineligible_reason(contract)
        if not reason:
            continue

        oa_number = str(getattr(contract, "law_firm_oa_case_number", "") or "").strip()
        code_hit = any(oa_number and code.upper() == oa_number.upper() for code in project_codes)
        name_hit = bool(buyer_name) and any(names_match(buyer_name, n) for n in principal_names(contract))
        if not code_hit and not name_hit:
            continue

        hints.append(
            {
                "contract_id": int(contract.id),
                "contract_name": str(contract.name or ""),
                "excluded_by": reason,
                "note": excluded_note(reason, contract, paid_total=getattr(contract, "paid_total", None)),
            }
        )

    # 项目号命中的排前面（比购买方撞名可靠）
    hints.sort(key=lambda h: (h["excluded_by"] != "fully_paid", h["contract_id"]))
    return hints[:MAX_EXCLUDED_HINTS]
