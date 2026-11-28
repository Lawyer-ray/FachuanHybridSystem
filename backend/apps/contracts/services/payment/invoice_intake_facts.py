"""待认领发票的**只读事实装配**：可见性收敛、裁定权、冲红重开组的三段票面事实。

为什么放在 Service 而不是 API：组的三段各要一次 ORM 查询（原票 / 生成原票的 intake /
重开蓝票），API 层出现 ``Model.objects`` 会撞四层架构门禁。API 只做最后一步
“事实 → 响应结构”的改名装配。

本模块只读：不写库、不碰文件、不开事务。红票的判定与守卫规则在 ``invoice_red_guards``。
"""

from __future__ import annotations

from typing import Any

from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus
from apps.contracts.services.payment.invoice_red_guards import _invoice_is_red


def _is_admin(user: Any) -> bool:
    return bool(getattr(user, "is_admin", False) or getattr(user, "is_superuser", False))


def open_count(user: Any) -> int:
    """首页角标：与我相关的待认领发票数。"""
    # visible_intakes_qs 返回 Any（跨模型 QuerySet），count() 需显式收敛成 int
    return int(visible_intakes_qs(user).filter(status=InvoiceIntakeStatus.PENDING).count())


def visible_intakes_qs(user: Any) -> Any:
    """「与我相关」的待认领发票。

    收敛口径与到账款项一致：邮件收件人 / 建议项目主办律师 / 管理员。
    这里不复刻复杂权限推导——发票天然属于律所内部财务流，可见范围给足，
    真正危险的动作（确认绑定）另有 :func:`can_decide` 把关。
    """
    from django.db.models import Q

    from apps.contracts.models import ContractAssignment

    if _is_admin(user):
        return InvoiceIntake.objects.all()

    primary_contract_ids = ContractAssignment.objects.filter(lawyer=user, is_primary=True).values("contract_id")
    return InvoiceIntake.objects.filter(
        Q(inbox_message__source__credential__lawyer=user)
        | Q(suggested_contract_id__in=primary_contract_ids)
        | Q(suggested_contract__assignments__lawyer=user)
    ).distinct()


def get_intake_for_user(*, intake_id: int, user: Any) -> InvoiceIntake:
    """取一条待认领发票（带常用关联），无权即视为不存在。

    ORM 留在 Service 层：API 层出现 ``Model.objects`` 会撞四层架构门禁。
    无权时抛 NotFound 而不是 PermissionDenied——不泄露记录存在性。
    """
    from apps.core.exceptions import NotFoundError

    # visible_intakes_qs 声明为 Any（跨模型 Q 查询），这里显式收敛回模型类型
    intake: InvoiceIntake | None = (
        visible_intakes_qs(user)
        .select_related("suggested_contract", "confirmed_contract", "inbox_message", "inbox_message__source")
        .filter(pk=intake_id)
        .first()
    )
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    return intake


def generated_invoice_facts(intake: InvoiceIntake) -> dict[str, str]:
    """确认后那张发票的**展示名 + 文件夹落点**（未确认则两者均空串）。

    展示名走 ``InvoiceFileService.display_filename`` 的同一份命名规则——绝不另拼。
    合同名取**确认到的**合同（人工改判过时可能与建议合同不同）。

    一次查库同时给两个字段：列表只关心文件名，详情还要落点，分两次查是白花。
    """
    blank = {"display_filename": "", "folder_subpath": ""}
    if intake.invoice_id is None:
        return blank
    from pathlib import Path

    from apps.contracts.models import Invoice
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    invoice = Invoice.objects.filter(pk=intake.invoice_id).select_related("payment__contract", "contract").first()
    if invoice is None:
        return blank
    payment = invoice.payment if invoice.payment_id else None
    contract = invoice.contract or (payment.contract if payment is not None else None)
    return {
        "display_filename": InvoiceFileService().display_filename(
            contract_name=str(getattr(contract, "name", "") or ""),
            seller=str(invoice.seller_name or ""),
            inv_date=invoice.invoice_date,
            ext=Path(str(invoice.file_path or "")).suffix.lower(),
            # 红票尾部是「红字开具」：列表里与它冲掉/重开的那张票必须看得出区别
            is_red=_invoice_is_red(invoice),
        ),
        "folder_subpath": str(getattr(invoice, "folder_subpath", "") or ""),
    }


def can_decide(user: Any, intake: InvoiceIntake) -> bool:
    """能不能对这张票做裁定。

    规则：管理员一律可以；其余人须是邮件收件人 或 建议项目的主办律师。
    无权时对外表现为"不存在"，不泄露记录存在性。
    """
    if _is_admin(user):
        return True
    credential_lawyer_id = getattr(getattr(intake.inbox_message, "source", None), "credential", None)
    if credential_lawyer_id is not None and getattr(credential_lawyer_id, "lawyer_id", None) == user.pk:
        return True
    contract = intake.suggested_contract
    if contract is not None:
        return contract.assignments.filter(lawyer=user, is_primary=True).exists()
    return False


def _group_item(invoice: Any, intake: Any) -> dict[str, Any]:
    """组内一段：票面事实一律优先取 ``Invoice``（真凭证），缺失才回落 intake。"""
    return {
        "intake_id": getattr(intake, "pk", None),
        "invoice_id": getattr(invoice, "pk", None),
        "invoice_number": str(getattr(invoice, "invoice_number", "") or getattr(intake, "invoice_number", "") or ""),
        "total_amount": (
            str(invoice.total_amount)
            if invoice is not None and getattr(invoice, "total_amount", None) is not None
            else (str(intake.total_amount) if intake is not None and intake.total_amount is not None else None)
        ),
    }


def _red_intakes_for_reissues(reissue_rows: list[InvoiceIntake]) -> list[InvoiceIntake]:
    """给一批「重开蓝票」找出各自所属的红票（可能为空：红票还没到）。

    路径：重开票 → supersedes_intake（被替代的原票 intake）→ 其 invoice → 同号发票
    被哪张红票点名（``red_against_number``）。

    一次批量查完，不随行数增长：首页 50 行里可能有多组冲红重开。
    """
    from apps.contracts.models import Invoice, InvoiceIntakeStatus

    original_intake_ids = {intake.supersedes_intake_id for intake in reissue_rows if intake.supersedes_intake_id}
    if not original_intake_ids:
        return []

    # 原票 intake -> 它的发票号
    original_numbers = {
        str(number)
        for number in InvoiceIntake.objects.filter(pk__in=original_intake_ids).values_list(
            "invoice__invoice_number", flat=True
        )
        if number
    }
    if not original_numbers:
        return []

    # 同项目的红票（未确认的），其 red_against_number 命中上面的号
    project_codes = {
        str(code)
        for code in InvoiceIntake.objects.filter(pk__in=original_intake_ids).values_list("project_code", flat=True)
        if code
    }
    qs = InvoiceIntake.objects.filter(
        status=InvoiceIntakeStatus.PENDING,
        red_against_number__in=original_numbers,
    ).select_related("offset_invoice")
    if project_codes:
        qs = qs.filter(project_code__in=project_codes)
    return list(qs)


def red_group_facts(intakes: list[InvoiceIntake]) -> dict[int, dict[str, Any] | None]:
    """批量装配「冲红重开组」的**票面事实**，返回 ``{intake_id: group | None}``。

    为什么放在 Service 而不是 API：组的三段各要一次 ORM 查询（原票 / 生成原票的
    intake / 重开蓝票），API 层出现 ``Model.objects`` 会撞四层架构门禁（基线 0）。
    API 只做最后一步"事实 → 响应结构"的改名装配。

    组只按 ``group_key`` 语义给出三段，**不判断该不该折叠**——那是前端的事：

    - ``original`` 原蓝票（可能不在库 → ``None``）
    - ``red``      红票本身；只要 ``is_red`` 成立就一定有这一段
    - ``reissue``  重开蓝票（只有"冲红并重开"才落，可能 ``None``）

    非红票且在库无对应记录的 intake 返回 ``None``（扁平列表里的普通行）。
    """
    groups: dict[int, dict[str, Any] | None] = {intake.pk: None for intake in intakes}
    red_intakes = [intake for intake in intakes if getattr(intake, "is_red", False)]
    if not red_intakes:
        pass

    # 重开票自己不是红票，单独看它算不出组。详情端点只传来这一张时必须
    # **从它反查所属红票**，否则同一张重开票在列表里有组、进详情就没组，
    # 弹窗里「冲红重开」的三段信息凭空消失。
    reissue_rows = [
        intake for intake in intakes if not getattr(intake, "is_red", False) and intake.supersedes_intake_id
    ]
    if reissue_rows:
        red_intakes = [*red_intakes, *_red_intakes_for_reissues(reissue_rows)]
    _red_intakes_dedup = {intake.pk: intake for intake in red_intakes}
    red_intakes = list(_red_intakes_dedup.values())

    if not red_intakes:
        return groups

    # 原票 / 重开票一次性批量取，避免首页 50 行退化成 150 次查询
    offset_ids = {intake.offset_invoice_id for intake in red_intakes if intake.offset_invoice_id}
    offset_numbers = {
        str(intake.red_against_number)
        for intake in red_intakes
        if not intake.offset_invoice_id and str(getattr(intake, "red_against_number", "") or "")
    }
    from apps.contracts.models import Invoice

    offset_by_id = {invoice.pk: invoice for invoice in Invoice.objects.filter(pk__in=offset_ids)}
    offset_by_number = {
        str(invoice.invoice_number): invoice for invoice in Invoice.objects.filter(invoice_number__in=offset_numbers)
    }
    # 重开蓝票的查找**不能**限定在本批 intakes 里。
    #
    # 真实样本：原票（intake #13）早已确认 -> 不在 pending 列表里；重开蓝票
    # ``supersedes_intake`` 指向的是那张**已确认的** 原票 intake。若按
    # ``supersedes_intake_id__in=<本批 pending ids>`` 过滤，就永远匹配不到，
    # 冲红重开组永远拼不起来（实测：红票显示正常但组卡片为空）。
    #
    # 正确口径：先定「原票」，再找「替代了这张原票」的那条待认领 intake。
    offset_intakes = {
        intake.invoice_id: intake
        for intake in InvoiceIntake.objects.filter(invoice_id__in=[inv.pk for inv in offset_by_id.values()])
    }
    # 原票 intake 的 id 集合 -> 用它反查重开票（一次批量，不随行数增长）
    original_intake_ids = {i.pk for i in offset_intakes.values() if i is not None}
    reissue_by_original_intake_id: dict[int, InvoiceIntake] = {}
    if original_intake_ids:
        for candidate in InvoiceIntake.objects.filter(supersedes_intake_id__in=original_intake_ids).order_by("-id"):
            reissue_by_original_intake_id.setdefault(int(candidate.supersedes_intake_id or 0), candidate)

    for red in red_intakes:
        offset = (
            offset_by_id.get(red.offset_invoice_id)
            if red.offset_invoice_id
            else offset_by_number.get(str(red.red_against_number))
        )
        original_intake = offset_intakes.get(offset.pk) if offset is not None else None
        reissue = reissue_by_original_intake_id.get(original_intake.pk) if original_intake is not None else None
        group = {
            "group_key": f"red:{red.red_against_number}",
            "original": _group_item(offset, original_intake) if offset is not None else None,
            "red": _group_item(None, red),
            "reissue": _group_item(None, reissue) if reissue is not None else None,
        }
        # 组事实必须同时发给**组内每一个成员**，不能只给红票。
        #
        # 前端按 ``reatch_group.group_key`` 折叠：只给红票时，重开蓝票自己对不上
        # 任何组，会被当成一条独立行渲染——用户看到“组卡片 + 一条重复的新票”。
        # 实测就是这个现象（#19 既在组里、又单独占一行）。
        groups[red.pk] = group
        if reissue is not None and reissue.pk in groups:
            groups[reissue.pk] = group
    return groups
