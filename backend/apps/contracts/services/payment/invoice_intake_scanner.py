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

1. 主题含「发票」/「开票」；
2. 正文含「发票已开具 / 发票已开 / 发票请查收 / 红字发票」**且邮件带 PDF 附件**；
3. 附件文件名以 ``dzfp_`` 开头或以「发票」开头且是 PDF。

法院文书、OA 通知、营销邮件不含上述特征，直接跳过。

### 为什么不认裸「请查收」

「请查收」是中文邮件最通用的客套话，实测把「广东某公司品质异常联络函」（正文「请查收」
+ 附件《产品检验报告.pdf》《燃烧测试报告.pdf》）判成了发票邮件，首页多出两条永远
"金额未识别"的待办。判据必须落在**开票动作**上（「发票已开具」而不是「请查收」）。

### 非发票附件的否决（只在「全部 PDF 都被否决」时生效）

检验报告 / 测试报告 / 联络函 / 对账单 这类附件名是**否决**而不是减分：一封带
「1 张发票 + 1 份报告」的邮件里发票必须进来，所以只有**所有** PDF 附件名都命中
否决模式时整封才不入池。主题命中但被否决时记 ``logger.info``，留痕可查。

## 红票（冲红）

红票的票面事实（被红冲的原蓝票号、确认单编号）随解析落库；解析出的原蓝票号
命中本库已有 ``Invoice`` 时写 ``offset_invoice``。随后统一跑一次
``_refresh_red_links``——它同时负责「红票 → 原票」与「重开蓝票 → 被替代的 intake」
两侧配对（红票先到、蓝票后到时也要能配上），幂等，只写这两个 FK。

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
from decimal import Decimal
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
#: 开票通知措辞必须指向**开票动作**。裸「请查收」是最通用的客套话，见模块文档。
_OPEN_NOTICE_KEYWORDS = ("发票已开具", "发票已开", "发票请查收", "红字发票")

#: 附件名判据
_FILENAME_PREFIXES = ("dzfp_", "dzfp")

#: 非发票附件名的否决模式：检验报告 / 测试报告 / 联络函 / 对账单 / 质检 / 检测报告。
#: 只在「全部 PDF 附件都命中」时否决整封邮件（一封带票带报告时票必须进来）。
_NON_INVOICE_FILENAME_PATTERNS = ("检验报告", "测试报告", "联络函", "对账单", "质检", "检测报告")

#: 重开蓝票与原票配对的金额容差（与 matching 层同口径）
_RED_AMOUNT_TOLERANCE = Decimal("0.005")

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


def _pdf_attachments(message: InboxMessage) -> list[dict[str, Any]]:
    raw = getattr(message, "attachments_meta", None) or []
    return [att for att in raw if isinstance(att, dict) and _is_pdf_attachment(att)]


def _attachment_filename(att: dict[str, Any]) -> str:
    return str(att.get("filename") or att.get("original_filename") or "").strip()


def _looks_non_invoice(filename: str) -> bool:
    """附件名是否命中非发票否决模式（检验报告 / 联络函 / 对账单…）。"""
    return any(pattern in filename for pattern in _NON_INVOICE_FILENAME_PATTERNS)


def _all_pdf_attachments_vetoed(attachments: list[dict[str, Any]]) -> bool:
    """**所有** PDF 附件名都命中否决模式才算整封否决。

    一封邮件带「1 张发票 + 1 份检验报告」时票必须进来，所以不能用 any()。
    """
    if not attachments:
        return False
    return all(_looks_non_invoice(_attachment_filename(att)) for att in attachments)


def is_invoice_mail(message: InboxMessage) -> bool:
    """这封邮件要不要扫成待认领发票。

    判据：主题含开票字样 / 附件名像发票（且带 PDF）/ 正文含开票通知措辞且带 PDF。
    否决（只有全部 PDF 附件都命中非发票模式时）先于入池判据生效——检验报告类附件
    即使主题写了「发票」也不该变成待办。
    """
    subject = str(getattr(message, "subject", "") or "")
    body = str(getattr(message, "body_text", "") or "")
    attachments = _pdf_attachments(message)

    if _all_pdf_attachments_vetoed(attachments):
        logger.info(
            "invoice_intake_skip_non_invoice_attachments",
            extra={"message_id": message.pk, "subject": subject[:60]},
        )
        return False

    if any(keyword in subject for keyword in ("发票", "开票")):
        return True
    if any(_looks_like_invoice_attachment(att) for att in attachments):
        return True
    return bool(attachments) and any(keyword in body for keyword in _OPEN_NOTICE_KEYWORDS)


def _already_recorded(invoice_number: str) -> bool:
    """这张票号是不是已经有落账的 Invoice 记录（已绑到收款或合同）。"""
    from apps.contracts.models import Invoice

    return Invoice.objects.filter(invoice_number=invoice_number).exists()


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
            # 红票事实透传：扫描层要据此写 offset_invoice 并跑配对
            "red_against_number": parsed.red_against_number or "",
            "red_confirmation_no": parsed.red_confirmation_no or "",
        }
    except Exception:
        # 解析失败不该影响同步：文件名信息已经够建一条待认领，律师点开详情时还能再试
        # extra 的键不能叫 filename：与 LogRecord 内建字段冲突，logging 会直接报错
        logger.info("invoice_pdf_parse_skipped", extra={"attachment_name": att.get("filename")}, exc_info=True)
        return {}


def mix_personal(name: str) -> str:
    """购买方脱敏（去掉「（个人）」标注，人名本体保留）。"""
    return mask_personal_name(name)


def _lookup_offset_invoice(red_against_number: str) -> Any | None:
    """红票冲的原票在本库里的记录（按号码）。没有则 None。"""
    if not red_against_number:
        return None
    from apps.contracts.models import Invoice

    return Invoice.objects.filter(invoice_number=red_against_number).select_related("payment").first()


def _red_pick_without_contract(*, red_against_number: str, offset_found: bool) -> dict[str, Any]:
    """红票没匹配到合同时的预选快照（无收款可选项，只表「红票」这件事）。

    走 ``_red_pick`` 同一份判定，避免「有合同」与「无合同」两条路径对
    「原票是否在库」说出两种话——同一张票在首页不应因为匹配结果不同而语义不同。
    """
    from apps.contracts.services.payment.invoice_match import _red_pick

    return _red_pick(
        red_against_number=red_against_number if offset_found else "",
        payment_options=[],
        unmatched_number=red_against_number,
    )


def scan_message(message: InboxMessage) -> list[InvoiceIntake]:
    """把一封邮件里的发票附件各建一条待认领。返回新建的（已存在的跳过）。"""
    attachments = _pdf_attachments(message)
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
        red_against_number = str(pdf_facts.get("red_against_number") or "")
        red_confirmation_no = str(pdf_facts.get("red_confirmation_no") or "")

        dedupe_key = _build_dedupe_key(message.pk, part_index, invoice_number)
        if InvoiceIntake.objects.filter(dedupe_key=dedupe_key).exists():
            continue

        # 跨表去重：这张票如果**已经落账**（Invoice 里有同号记录），就不再入池。
        #
        # 只看 intake 表是不够的：intake 记录可能在确认后被清理（拓数据、改来源、
        # 手滑删除），而 Invoice 是真正的财务凭证。不查 Invoice 的话，重扫会把
        # 一张早就处理完的票又变回“待认领”，用户看到的就是“明明确认过了又冒出来”。
        if invoice_number and _already_recorded(invoice_number):
            logger.info(
                "invoice_intake_skip_already_recorded",
                extra={"invoice_number": invoice_number, "message_id": message.pk},
            )
            continue

        ranking = rank_invoice_candidates(
            project_code=project_code,
            buyer_name=buyer_name,
            remark=remark,
            original_filename=filename,
        )
        top_contract_id = ranking.get("top_contract_id")
        # 先查原票：红票的置信度（能否一键冲红）取决于**原票是否真的在本库**，
        # 而这个事实不能由 choose_payment 自己推导（它只拿到合同，拿不到票号）。
        offset_invoice = _lookup_offset_invoice(red_against_number)
        is_red = bool(red_against_number) or (total_amount is not None and total_amount < 0)
        # 红票不预选收款：冲销不是新的记账动作，预选一笔收款会诱导人把红票当新票挂上去
        payment_pick: dict[str, Any] = {}
        if top_contract_id is not None:
            payment_pick = choose_payment(
                contract_id=int(top_contract_id),
                total_amount=total_amount,
                invoice_date=invoice_date,
                is_red=is_red,
                # 两个事实显式传入：票面印的票号 + 该票号是否命中本库 Invoice
                red_against_number=red_against_number,
                red_offset_found=offset_invoice is not None,
            )
        elif is_red:
            # 红票但没匹配到合同（项目号缺失/项目不在办）：仍要说清「这是红票、
            # 冲的是哪张票」，否则前端只剩「无可匹配的在办项目」，把「红票」
            # 这个最关键的事实吃掉。这里不查合同收款，故 options 为空。
            payment_pick = _red_pick_without_contract(
                red_against_number=red_against_number,
                offset_found=offset_invoice is not None,
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
            red_against_number=red_against_number[:32],
            red_confirmation_no=red_confirmation_no[:64],
            offset_invoice=offset_invoice,
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


def _refresh_red_links(project_code: str) -> int:
    """重算一个项目下红票/重开蓝票的配对关系。返回被改写的 intake 条数。

    两侧都要重算，因为红票与重开蓝票谁先落池不确定（真实样本重开蓝票比红票
    早 10 分钟入池）。幂等：只写 ``offset_invoice`` / ``supersedes_intake`` 两个 FK，
    算出的结果与库内一致就不写。

    配对只认红票证据（项目内某张红票的 ``red_against_number`` 指向它）：**不做**
    「同项目同金额」的推测——分期开票、同额多期是常态，擅自推测会把合法旧票
    误判为已作废。

    Args:
        project_code: 律所项目号；空串直接返回 0（无项目就无法限定配对范围）。
    """
    if not project_code:
        return 0

    from apps.contracts.models import Invoice, InvoiceIntake, InvoiceIntakeStatus

    intakes = list(InvoiceIntake.objects.filter(project_code=project_code))
    reds = [item for item in intakes if item.red_against_number]
    if not reds:
        return 0

    # 原蓝票号 → 已确认的 intake（配对骨架：只有被红票点名的原票才参与）
    confirmed_by_number: dict[str, InvoiceIntake] = {}
    for item in intakes:
        number = str(item.invoice_number or "")
        if item.status != InvoiceIntakeStatus.CONFIRMED or not number:
            continue
        confirmed_by_number.setdefault(number, item)

    # 一对一：一条已确认 intake 只能被一条重开蓝票认领，先到先得（按 id 保证可重现）
    claimed: set[int] = set()
    changed = 0

    for red in sorted(reds, key=lambda item: item.pk):
        changed += _link_red_offset(red, Invoice)
        original = confirmed_by_number.get(red.red_against_number)
        if original is None or not _red_amount_cancels(original, red):
            continue
        changed += _link_supersede(original, claimed)

    # 重开蓝票一侧：同项目、非红、非已确认，金额与原票同符号同绝对值
    for candidate in sorted(intakes, key=lambda item: item.pk):
        if candidate.red_against_number or candidate.status != InvoiceIntakeStatus.PENDING:
            continue
        original = _find_supersede_target(candidate, confirmed_by_number)
        if original is None:
            continue
        changed += _link_supersede(original, claimed, reissue=candidate)

    if changed:
        logger.info("invoice_intake_red_links_refreshed", extra={"project_code": project_code, "changed": changed})
    return changed


def _same_amount(left: Any, right: Any) -> bool:
    """两个金额绝对値相等（容差 0.005）。任一为空即不相等。"""
    if left is None or right is None:
        return False
    try:
        return abs(Decimal(str(left)) - Decimal(str(right))) < _RED_AMOUNT_TOLERANCE
    except (ArithmeticError, TypeError, ValueError):
        return False


def _red_amount_cancels(original: InvoiceIntake, red: InvoiceIntake) -> bool:
    """红票是否确实冲掉了原票：红票金额为负，且绝对值与原票相等。

    红票金额未识别（``total_amount is None``）时放行：这是「重解析前」的真实状态，
    拦在这里会让配对永远配不上（裁定层的守卫会挡住金额未知的冲红动作）。
    """
    if red.total_amount is None:
        return True
    if red.total_amount >= 0:
        return False
    return _same_amount(abs(red.total_amount), original.total_amount)


def _link_red_offset(red: InvoiceIntake, invoice_model: Any) -> int:
    """红票 → 原票 Invoice（``offset_invoice``）。返回改写条数（0/1）。"""
    target = (
        invoice_model.objects.filter(invoice_number=red.red_against_number).first() if red.red_against_number else None
    )
    if target is None or red.offset_invoice_id == target.pk:
        return 0
    red.offset_invoice_id = target.pk
    red.save(update_fields=["offset_invoice", "updated_at"])
    return 1


def _link_supersede(original: InvoiceIntake, claimed: set[int], *, reissue: InvoiceIntake | None = None) -> int:
    """把「重开蓝票 → 原票 intake」写进 ``supersedes_intake``。返回改写条数（0/1）。

    已确认 intake 一侧是骨架（它自己就是原票，不需要 supersedes）；真正写値的是
    重开蓝票自己。``claimed`` 保证一对一：已有重开票认领的原票不再参与。
    """
    if reissue is None or original.pk in claimed:
        return 0
    if reissue.pk == original.pk:
        return 0
    claimed.add(int(original.pk))
    if reissue.supersedes_intake_id == original.pk:
        return 0
    reissue.supersedes_intake_id = original.pk
    reissue.save(update_fields=["supersedes_intake", "updated_at"])
    return 1


def _find_supersede_target(
    candidate: InvoiceIntake, confirmed_by_number: dict[str, InvoiceIntake]
) -> InvoiceIntake | None:
    """找出一条「被红票点名、且金额与原票同符号同绝对值」的原票 intake。"""
    if candidate.total_amount is None or candidate.total_amount <= 0:
        return None
    for original in confirmed_by_number.values():
        if original.project_code != candidate.project_code:
            continue
        if not _same_amount(original.total_amount, candidate.total_amount):
            continue
        return original
    return None


def _backfill_missing_amounts() -> set[str]:
    """重解析历史 pending intake，只补**空字段**（不覆盖已有値）。

    存在的理由：解析器修好之前入池的红票（金额、红票事实全抽成 NULL）永远不会
    再被扫一次——去重键已存在，重扫直接跳过。不补的话它们只能等人工驳回。

    「只补空」是硬约束：人工可能已经改过金额/号码，重解析不能把它改回去。

    Returns:
        被回填的记录所属的项目号集合（调用方据此只重算这些项目的红票配对）。
    """
    from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus

    targets = InvoiceIntake.objects.filter(status=InvoiceIntakeStatus.PENDING).exclude(invoice_number="")
    touched_projects: set[str] = set()
    for intake in targets.filter(total_amount__isnull=True):
        att = {"local_path": intake.attachment_path, "filename": intake.original_filename}
        facts = _deeper_parse(att)
        if not facts:
            continue
        updated: list[str] = []
        if intake.total_amount is None and facts.get("total_amount") is not None:
            intake.total_amount = facts["total_amount"]
            updated.append("total_amount")
        if intake.invoice_date is None and facts.get("invoice_date") is not None:
            intake.invoice_date = facts["invoice_date"]
            updated.append("invoice_date")
        for name, limit in (("red_against_number", 32), ("red_confirmation_no", 64)):
            value = str(facts.get(name) or "")
            if not getattr(intake, name) and value:
                setattr(intake, name, value[:limit])
                updated.append(name)
        if intake.offset_invoice_id is None and intake.red_against_number:
            offset = _lookup_offset_invoice(intake.red_against_number)
            if offset is not None:
                intake.offset_invoice_id = offset.pk
                updated.append("offset_invoice")
        if not updated:
            continue
        intake.save(update_fields=[*updated, "updated_at"])
        if intake.project_code:
            touched_projects.add(intake.project_code)
        logger.info(
            "invoice_intake_backfilled",
            extra={"intake_id": intake.pk, "fields": updated, "project_code": intake.project_code},
        )
    return touched_projects


def refresh_red_links(project_code: str) -> int:
    """公开出口：重算一个项目下红票/重开蓝票的配对（见 ``_refresh_red_links``）。

    存在的理由：裁定层（invoice_intake_service）在重解析/导入之后需要重算配对，
    而跨模块直接引私有名 ``_refresh_red_links`` 会破坏模块边界（私有名可随时被改）。
    这里只是一个稳定的名字，不复制任何逻辑。
    """
    return _refresh_red_links(project_code)


def scan_new_messages(message_ids: list[int]) -> int:
    """邮件同步后调用：只扫新入库的那些邮件。返回新建条数。"""
    from apps.message_hub.models import InboxMessage

    total = 0
    project_codes: set[str] = set()
    for message in InboxMessage.objects.filter(pk__in=message_ids):
        if not is_invoice_mail(message):
            continue
        try:
            created = scan_message(message)
        except Exception:
            logger.warning("invoice_intake_scan_failed", extra={"message_id": message.pk}, exc_info=True)
            continue
        total += len(created)
        project_codes.update(item.project_code for item in created if item.project_code)
    for code in project_codes:
        _refresh_red_links(code)
    return total


def scan_since(days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, int]:
    """手动补扫近 N 天（首页「重新扫描」）。幂等：已存在的跳过。

    先回填历史 pending 的空字段（解析器修好之前入池的票），再扫新邮件，最后
    对涉及的每个项目重算红票配对。
    """
    from apps.message_hub.models import InboxMessage

    cutoff = timezone.now() - timedelta(days=max(1, days))
    project_codes = _backfill_missing_amounts()
    scanned = created = 0
    for message in InboxMessage.objects.filter(received_at__gte=cutoff).order_by("-received_at"):
        scanned += 1
        if not is_invoice_mail(message):
            continue
        try:
            fresh = scan_message(message)
        except Exception:
            logger.warning("invoice_intake_scan_failed", extra={"message_id": message.pk}, exc_info=True)
            continue
        created += len(fresh)
        project_codes.update(item.project_code for item in fresh if item.project_code)
    for code in project_codes:
        _refresh_red_links(code)
    return {"scanned": scanned, "created": created, "days": days}
