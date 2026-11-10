"""把收件箱里的**发票邮件**扫成 ``InvoiceIntake`` 记录。

## 与到账扫描器的分工

到账认领（``intake_scanner``）解决「钱来了，是谁的」——匹配器排序、人在首页裁定。
发票认领解决的是另一件事：**律所财务开好票后用邮件发过来**，律师要知道
「这张票是给哪个案子的」并把它挂进项目（开票金额、合同文件夹副本都靠它）。

两件事的自动化程度不同，因为证据强度差一个量级：

- 到账邮件正文只有付款人姓名 + 银行备注，几乎不含案号 → 只能"排序 + 解释"，绝不预选；
- 发票 PDF 的**备注栏带律所项目号**（``2025GZM0001-张某与某公司合同纠纷``），  # privacy-allow 虚构样例，非真实项目号
  而 ``Contract.law_firm_oa_case_number`` 有唯一约束 → 命中即确定性，可以直接预选。

## 扫描判据（任一命中即入池）

1. 主题含「发票」；
2. 正文含「发票已开具 / 请查收」这类开票通知措辞；
3. 附件文件名以 ``dzfp_`` 开头或以「发票」开头且是 PDF。

法院文书、OA 通知、营销邮件不含上述特征，直接跳过。

## 一封邮件多附件

财务确实会一次发多张票，所以**每个 PDF 附件各建一条**（与到账"一封一条"不同）。
``dedupe_key`` 用 ``sha256(inbox_message_id | part_index | invoice_number)``：同一封邮件
重复扫描不产生第二条；换上 ``invoice_number`` 后，财务把同一张票重发一次也能识别。

## 解析深度：文件名优先，PDF 兜底

附件名里已经带齐了号码/购买方/项目号（``dzfp_2644200..._张三（个人）_2025GZM0001-某某律师.pdf``），  # privacy-allow 虚构样例，非真实项目号
读文件名比打开 PDF 便宜得多。**只在文件名抽不到项目号时才读 PDF**——同步链路里
每张票多花 0.3~1 秒不划算，而真正需要深解析的那几张，点开详情时也已经解析过了。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus
from apps.contracts.services.payment.invoice_filename import mask_personal_name, parse_invoice_filename
from apps.contracts.services.payment.invoice_match import choose_payment, rank_invoice_candidates

if TYPE_CHECKING:
    from apps.message_hub.models import InboxMessage

logger = logging.getLogger("apps.contracts")

#: 发票比到账慢：财务开票、走流程、发件常跨月，回看窗口按 60 天覆盖一个自然账期
DEFAULT_LOOKBACK_DAYS = 60

#: 主题/正文里的开票通知措辞
_INVOICE_KEYWORDS = ("发票", "开票", "已开具", "请查收发票")
_OPEN_NOTICE_KEYWORDS = ("发票已开具", "发票已开", "请查收")

#: 附件名判据
_FILENAME_PREFIXES = ("dzfp_", "dzfp")

#: 单封邮件最多收的附件数（防止一封带 50 个附件的邮件把首页灌满）
MAX_ATTACHMENTS_PER_MAIL = 10


def _is_pdf_attachment(att: dict[str, Any]) -> bool:
    """是不是 PDF 附件（按 content_type 与扩展名双判，任一命中即认）。"""
    content_type = str(att.get("content_type") or "").lower()
    filename = str(att.get("filename") or att.get("original_filename") or "").lower()
    return "pdf" in content_type or filename.endswith(".pdf")


def _looks_like_invoice_attachment(att: dict[str, Any]) -> bool:
    """附件名像不像发票（``dzfp_...`` / ``发票_...``）。"""
    filename = str(att.get("filename") or att.get("original_filename") or "").strip()
    if not filename:
        return False
    lowered = filename.lower()
    if any(lowered.startswith(prefix) for prefix in _FILENAME_PREFIXES):
        return True
    return filename.startswith("发票")


def is_invoice_mail(message: InboxMessage) -> bool:
    """这封邮件要不要扫成待认领发票。

    判据宽松（任一条命中即算）：宁可多建一条让人驳回，也不要漏掉一张真票——
    漏掉的票律师根本不知道它来过。
    """
    subject = str(getattr(message, "subject", "") or "")
    body = str(getattr(message, "body_text", "") or "")
    attachments = getattr(message, "attachments_meta", None) or []

    if any(keyword in subject for keyword in ("发票", "开票")):
        return True
    if any(keyword in body for keyword in _OPEN_NOTICE_KEYWORDS):
        return True
    return any(_looks_like_invoice_attachment(att) for att in attachments if isinstance(att, dict))


def _build_dedupe_key(message_id: int, part_index: int, invoice_number: str) -> str:
    """幂等键：同封邮件同一附件不重复；拿到号码后同一张票重发也能识别。"""
    raw = f"{message_id}|{part_index}|{invoice_number}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _deeper_parse(att: dict[str, Any]) -> dict[str, Any]:
    """读 PDF 补全号码/购买方/项目号/金额/备注。任何失败都返回空 dict，绝不抛。"""
    from apps.message_hub.services.base import resolve_media_attachment_path

    try:
        path = resolve_media_attachment_path(str(att.get("local_path") or ""))
        if path is None:
            return {}
        import pdfplumber

        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        with pdfplumber.open(str(path)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        if not text.strip():
            return {}
        parsed = InvoiceParser().parse(text)
        return {
            "invoice_number": parsed.invoice_number or "",
            "invoice_date": parsed.invoice_date,
            "total_amount": parsed.total_amount,
            "buyer_name": mix_personal(parsed.buyer_name or ""),
            "remark": parsed.remark or "",
            "project_code": parsed.project_code or "",
        }
    except Exception:
        # 解析失败不该影响同步：文件名信息已经够建一条待认领，律师点开详情时还能再试
        # extra 的键不能叫 filename：与 LogRecord 内建字段冲突，logging 会直接报错
        logger.info("invoice_pdf_parse_skipped", extra={"attachment_name": att.get("filename")}, exc_info=True)
        return {}


def mix_personal(name: str) -> str:
    """购买方脱敏（去掉「（个人）」标注，人名本体保留）。"""
    return mask_personal_name(name)


def scan_message(message: InboxMessage) -> list[InvoiceIntake]:
    """把一封邮件里的发票附件各建一条待认领。返回新建的（已存在的跳过）。"""
    attachments = [
        att
        for att in (getattr(message, "attachments_meta", None) or [])
        if isinstance(att, dict) and _is_pdf_attachment(att)
    ]
    if not attachments:
        return []

    created: list[InvoiceIntake] = []
    for att in attachments[:MAX_ATTACHMENTS_PER_MAIL]:
        part_index = int(att.get("part_index") or 0)
        filename = str(att.get("filename") or att.get("original_filename") or "")
        facts = parse_invoice_filename(filename)

        # **总是读 PDF**：文件名能给出项目号，却给不出**金额与收款定位**——
        # 而首页要"默认预选收款"，没有价税合计就无法判断挂哪笔钱。
        # 用户已确认发票邮件基本一封一附件，这个代价可接受（实测约 0.3s/张）。
        pdf_facts = _deeper_parse(att)

        invoice_number = pdf_facts.get("invoice_number") or facts.get("invoice_number") or ""
        project_code = pdf_facts.get("project_code") or facts.get("project_code") or ""
        buyer_name = pdf_facts.get("buyer_name") or facts.get("buyer_name") or ""
        remark = pdf_facts.get("remark") or ""
        invoice_date = pdf_facts.get("invoice_date")
        total_amount = pdf_facts.get("total_amount")

        dedupe_key = _build_dedupe_key(message.pk, part_index, invoice_number)
        if InvoiceIntake.objects.filter(dedupe_key=dedupe_key).exists():
            continue

        ranking = rank_invoice_candidates(
            project_code=project_code,
            buyer_name=buyer_name,
            remark=remark,
            original_filename=filename,
        )
        top_contract_id = ranking.get("top_contract_id")
        # 已定合同才谈得上「预选哪笔收款」：四级规则见 invoice_match.choose_payment
        payment_pick: dict[str, Any] = {}
        if top_contract_id is not None:
            payment_pick = choose_payment(
                contract_id=int(top_contract_id), total_amount=total_amount, invoice_date=invoice_date
            )

        snapshot = {
            "computed_at": timezone.now().isoformat(),
            "parsed": {
                "invoice_number": invoice_number,
                "project_code": project_code,
                "buyer_name": buyer_name,
                "source": "pdf" if pdf_facts else "filename",
            },
            "payment_pick": payment_pick,
            **ranking,
        }
        intake = InvoiceIntake.objects.create(
            inbox_message=message,
            part_index=part_index,
            dedupe_key=dedupe_key,
            attachment_path=str(att.get("local_path") or ""),
            original_filename=filename[:255],
            invoice_number=invoice_number[:32],
            invoice_date=invoice_date,
            total_amount=total_amount,
            buyer_name=buyer_name[:120],
            remark=remark,
            project_code=project_code[:32],
            status=InvoiceIntakeStatus.PENDING,
            suggested_contract_id=top_contract_id,
            suggested_payment_id=payment_pick.get("suggested_payment_id"),
            match_snapshot=snapshot,
        )
        created.append(intake)
        logger.info(
            "invoice_intake_created",
            extra={
                "intake_id": intake.pk,
                "message_id": message.pk,
                "project_code": project_code,
                "suggested_contract_id": top_contract_id,
            },
        )
    return created


def scan_new_messages(message_ids: list[int]) -> int:
    """邮件同步后调用：只扫新入库的那些邮件。返回新建条数。"""
    from apps.message_hub.models import InboxMessage

    total = 0
    for message in InboxMessage.objects.filter(pk__in=message_ids):
        if not is_invoice_mail(message):
            continue
        try:
            total += len(scan_message(message))
        except Exception:
            logger.warning("invoice_intake_scan_failed", extra={"message_id": message.pk}, exc_info=True)
    return total


def scan_since(days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, int]:
    """手动补扫近 N 天（首页「重新扫描」）。幂等：已存在的跳过。"""
    from apps.message_hub.models import InboxMessage

    cutoff = timezone.now() - timedelta(days=max(1, days))
    scanned = created = 0
    for message in InboxMessage.objects.filter(received_at__gte=cutoff).order_by("-received_at"):
        scanned += 1
        if not is_invoice_mail(message):
            continue
        try:
            created += len(scan_message(message))
        except Exception:
            logger.warning("invoice_intake_scan_failed", extra={"message_id": message.pk}, exc_info=True)
    return {"scanned": scanned, "created": created, "days": days}
