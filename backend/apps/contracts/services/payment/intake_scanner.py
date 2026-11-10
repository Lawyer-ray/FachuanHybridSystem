"""把收件箱里的到账通知扫成 ``PaymentIntake`` 记录。

## 触发方式

1. **邮件同步后**：IMAP 拉完新邮件调用 ``scan_recent_messages``（只扫新入库的）；
2. **手动补扫**：首页/后台的"重新扫描"，调用 ``scan_since``。

## 扫描范围：默认只看近两周

用户明确说明「前两周才和财务说好通过邮件发到账通知」，更早的邮件里没有
到账通知形态的内容。默认 ``DEFAULT_LOOKBACK_DAYS = 14`` 既覆盖真实起点，
又避免把收件箱 300+ 条历史邮件全部拉去做匹配（每封都要跑一次全量合同打分，
成本不低且结果无意义）。

## 什么邮件会被扫成待认领

必须是**到账通知形态**才建单，判据（任一即可）：

- 主题/正文含款项关键词（到账/汇入/存入/转入/收款）
- 且能解析出**金额**

金额解析不出来 → 跳过并记 debug 日志，**绝不建 amount=0 的记录**
（设计文档 §5：宁可什么都不出，也不要污染首页）。

法院文书、OA 通知、营销邮件等没有款项关键词的，直接跳过。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import IntakeStatus, PaymentIntake
from apps.message_hub.services.contract_match_v2 import suggest_contracts_for_transfer
from apps.message_hub.services.transfer_notice import parse_transfer_notice

if TYPE_CHECKING:
    from apps.message_hub.models import InboxMessage

logger = logging.getLogger("apps.contracts")

# 默认回看天数：用户前两周才开始让财务发到账通知
DEFAULT_LOOKBACK_DAYS = 14

# 款项关键词：命中才认为这封邮件可能是到账通知
_TRANSFER_KEYWORDS = (
    "到账",
    "汇入",
    "存入",
    "转入",
    "收款",
    "已汇",
    "汇款",
    "转入贵公司",
)

# 哪些来源参与扫描。法院到账通知（court_inbox）暂不纳入：
# 诉讼费/保全费/案款与律师费收入性质不同，需单独解析规则（设计文档 §8 第 6 条）
_SCAN_SOURCE_TYPES = ("imap",)


def _dedupe_key(message_id: int, amount: Any, received_at: Any) -> str:
    """幂等键：同封邮件 + 同金额 + 同到账日 = 同一条待认领。"""
    raw = f"{message_id}|{amount}|{received_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _looks_like_transfer(message: InboxMessage) -> bool:
    haystack = f"{message.subject or ''}\n{message.body_text or ''}"
    if not haystack.strip() and message.body_html:
        from apps.message_hub.services.transfer_notice import html_to_text

        haystack = f"{message.subject or ''}\n{html_to_text(message.body_html)}"
    return any(k in haystack for k in _TRANSFER_KEYWORDS)


def _build_intake(message: InboxMessage) -> PaymentIntake | None:
    """解析一封邮件并构造（未保存的）待认领记录。不适合建单时返回 None。"""
    notice = parse_transfer_notice(
        subject=message.subject or "",
        body_text=message.body_text or "",
        body_html=message.body_html or "",
    )
    if not notice.ok or notice.amount is None:
        # 有款项关键词但抽不出金额：记日志便于回头补解析规则，但不建单
        logger.debug("到账通知解析不出金额，跳过: message=%s subject=%s", message.pk, (message.subject or "")[:40])
        return None

    # 到账日优先用正文里的日期（真实到账日），取不到退回邮件接收日
    received_at = notice.received_at or timezone.localtime(message.received_at).date()

    snapshot = suggest_contracts_for_transfer(
        subject=message.subject or "",
        body_text=message.body_text or "",
        body_html=message.body_html or "",
    )
    candidates = snapshot.get("candidates") or []
    # 建议项目：只认排第一的候选。没有候选就留空（不硬塞）
    suggested_id = candidates[0].get("contract_id") if candidates else None

    # 有实名证据的候选 = 可信 → pending（等人确认归属）
    # 只有 amount_only 的候选 = 不可信 → 仍是 pending，但不预选建议项目
    #   （避免"系统已经帮你选好了"的暗示员工直接点确认）
    if suggested_id is not None and candidates[0].get("kind") == "amount_only":
        suggested_id = None

    from apps.message_hub.services.transfer_notice import html_to_text

    body_plain = message.body_text or ""

    return PaymentIntake(
        inbox_message=message,
        dedupe_key=_dedupe_key(message.pk, notice.amount, received_at.isoformat()),
        amount=notice.amount,
        received_at=received_at,
        payer_name=notice.payer_name,
        on_behalf_of=notice.on_behalf_of,
        bank_remark=(body_plain or html_to_text(message.body_html or ""))[:2000],
        suggested_contract_id=suggested_id,
        match_snapshot=snapshot,
        status=IntakeStatus.PENDING,
    )


def scan_message(message: InboxMessage) -> PaymentIntake | None:
    """扫描单封邮件；已存在（按 dedupe_key）则返回既有记录。

    幂等：重复扫描不会产生第二条；已确认/已忽略的记录不会被覆盖。
    """
    if not _looks_like_transfer(message):
        return None

    candidate = _build_intake(message)
    if candidate is None:
        return None

    with transaction.atomic():
        existing = PaymentIntake.objects.filter(dedupe_key=candidate.dedupe_key).first()
        if existing is not None:
            return existing
        candidate.save()
    logger.info(
        "生成待认领款项: intake=%s message=%s amount=%s payer=%s",
        candidate.pk,
        message.pk,
        candidate.amount,
        candidate.payer_name or "-",
    )
    return candidate


def scan_since(
    *, days: int = DEFAULT_LOOKBACK_DAYS, source_types: tuple[str, ...] = _SCAN_SOURCE_TYPES
) -> dict[str, Any]:
    """扫描近 ``days`` 天内的消息，把到账通知转成待认领。

    返回统计，供手动补扫的接口回显。
    """
    from apps.message_hub.models import InboxMessage

    since = timezone.now() - timedelta(days=days)
    qs = (
        InboxMessage.objects.filter(source__source_type__in=source_types, received_at__gte=since)
        .select_related("source")
        .order_by("received_at")
    )

    scanned = created = skipped = 0
    for message in qs.iterator(chunk_size=50):
        scanned += 1
        try:
            result = scan_message(message)
        except Exception:  # 单封失败不能中断整轮扫描
            logger.warning("扫描到账通知失败: message=%s", message.pk, exc_info=True)
            skipped += 1
            continue
        if result is None:
            skipped += 1
        else:
            created += 1

    logger.info("到账扫描完成: 近 %s 天, 扫描 %s 封, 命中 %s 封, 跳过 %s 封", days, scanned, created, skipped)
    return {"scanned": scanned, "created": created, "skipped": skipped, "days": days}


def scan_new_messages(message_ids: list[int]) -> int:
    """扫描指定的一批消息（邮件同步钩子用，只处理刚入库的）。"""
    from apps.message_hub.models import InboxMessage

    if not message_ids:
        return 0
    created = 0
    qs = InboxMessage.objects.filter(pk__in=message_ids).select_related("source")
    for message in qs:
        try:
            if scan_message(message) is not None:
                created += 1
        except Exception:
            logger.warning("扫描到账通知失败: message=%s", message.pk, exc_info=True)
    return created
