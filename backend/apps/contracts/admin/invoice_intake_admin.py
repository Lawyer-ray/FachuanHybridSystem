"""InvoiceIntake Admin —— 发票待认领。

后台只读为主：待认领的正常处理路径是**前端首页的确认模块**，
后台用于排查"这张票为什么没匹配上"——因此把识别结果、候选快照、
附件落点全部摊开显示，且不提供"直接改状态"的自由编辑（发票数据要留痕）。
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Q
from django.http import HttpRequest
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

from apps.contracts.models import Invoice, InvoiceIntake, InvoiceIntakeStatus
from apps.core.admin.base import BaseModelAdmin


class RedAgainstMissingFilter(admin.SimpleListFilter):
    """巡检筛选：「红票但原票不在库」。

    ## 为什么需要这个筛选

    红票的裁定链路要求 ``offset_invoice`` 存在（原票已落账才能冲），否则硬拦。
    但两种数据会停在“红票在池里、原票却查不到”的半死状态：

    - 客户发来的红票对应的那张蓝票从未经过本系统（纸票/他系统开票）；
    - 历史数据：扫描层还没写 ``offset_invoice`` 时入池的红票。

    这些票用户点“冲红”只会得到错误，得人工处理。财务需要一份清单把它们捞出来，
    否则它们会一直躺在待认领里。
    """

    title = "冲红巡检"
    parameter_name = "red_offset"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        return [
            ("missing", "红票但原票不在库"),
            ("red_only", "只看红票"),
        ]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:
        if self.value() == "red_only":
            return queryset.filter(red_against_number__gt="")
        if self.value() == "missing":
            red_number_q = Q(red_against_number__gt="") | Q(total_amount__lt=0)
            offset_numbers = Invoice.objects.filter(invoice_number__gt="").values("invoice_number")
            return (
                queryset.filter(red_number_q)
                .exclude(offset_invoice__isnull=False)
                .exclude(red_against_number__in=offset_numbers)
            )
        return queryset


@admin.register(InvoiceIntake)
class InvoiceIntakeAdmin(BaseModelAdmin):  # pragma: no cover
    list_display = [
        "id",
        "invoice_number",
        "is_red",
        "red_against_number",
        "total_amount",
        "buyer_name",
        "project_code",
        "status_badge",
        "suggested_contract",
        "created_at",
    ]
    list_filter: ClassVar = [
        "status",
        "invoice_date",
        "created_at",
        RedAgainstMissingFilter,
    ]
    search_fields: ClassVar = ("invoice_number", "buyer_name", "project_code", "remark", "original_filename")
    autocomplete_fields: ClassVar = (
        "inbox_message",
        "suggested_contract",
        "suggested_payment",
        "confirmed_contract",
        "confirmed_payment",
        "confirmed_by",
    )
    readonly_fields: ClassVar = [
        "dedupe_key",
        "match_snapshot_pretty",
        "remark",
        "is_red",
        "offset_invoice",
        "supersedes_intake",
        "created_at",
        "updated_at",
    ]
    date_hierarchy = "created_at"
    ordering: ClassVar = ["-created_at", "-id"]

    fieldsets: ClassVar = (
        (
            "发票识别结果",
            {
                "fields": (
                    "inbox_message",
                    "part_index",
                    "original_filename",
                    "attachment_path",
                    "invoice_number",
                    "invoice_date",
                    "total_amount",
                    "buyer_name",
                    "project_code",
                    "remark",
                )
            },
        ),
        (
            "冲红信息（只读）",
            {
                "fields": (
                    "is_red",
                    "red_against_number",
                    "red_confirmation_no",
                    "offset_invoice",
                    "supersedes_intake",
                ),
                "description": "红字发票的冲销关系。待认领链路的裁定动作在前端「冲红重开」卡，后台只展示。",
            },
        ),
        ("系统建议（只读）", {"fields": ("suggested_contract", "suggested_payment", "match_snapshot_pretty")}),
        (
            "人工裁定",
            {
                "fields": (
                    "status",
                    "confirmed_contract",
                    "confirmed_payment",
                    "confirmed_by",
                    "confirmed_at",
                    "invoice",
                    "decision_note",
                )
            },
        ),
        ("元信息", {"fields": ("dedupe_key", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="状态")
    def status_badge(self, obj: InvoiceIntake) -> SafeString:
        colors: dict[str, str] = {
            InvoiceIntakeStatus.PENDING: "#007bff",
            InvoiceIntakeStatus.CONFIRMED: "#28a745",
            InvoiceIntakeStatus.REJECTED: "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="红票", boolean=False)
    def is_red(self, obj: InvoiceIntake) -> SafeString:
        """红底徽标。非红票给短横，不用空字符串（空单元格在列表里像“漏了”）。"""
        if not obj.is_red:
            return format_html("<span style='color:#adb5bd'>{}</span>", "—")
        return format_html(
            '<span style="background:#dc3545;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{}</span>',
            "红字",
        )

    @admin.display(description="匹配快照")
    def match_snapshot_pretty(self, obj: InvoiceIntake) -> SafeString:
        """把候选铺开显示，便于排查"为什么没匹配上"。

        ⚠️ 这里的内容**全部来自邮件解析**（合同名、购买方、备注栏、匹配理由），
        属于外部可控输入。因此一律走 ``format_html`` 逐项转义，**禁止**用字符串
        拼接 + ``mark_safe``——那样一封构造过的发票邮件就能在后台管理页打 XSS。
        """
        snapshot = obj.match_snapshot or {}
        if not snapshot:
            return format_html("<em>无</em>")

        parts: list[SafeString] = []

        parsed = snapshot.get("parsed") or {}
        if parsed:
            parts.append(
                format_html(
                    "<div><strong>解析：</strong>发票号 {} / 价税合计 {} / 购买方 {} / 项目号 {}</div>",
                    parsed.get("invoice_number") or "-",
                    parsed.get("total_amount") or "-",
                    parsed.get("buyer_name") or "-",
                    parsed.get("project_code") or "-",
                )
            )

        candidates = snapshot.get("candidates") or []
        if candidates:
            items = [
                format_html(
                    '<li>[{}] {:.2f} <a href="/admin/contracts/contract/{}/change/">{}</a> — {}</li>',
                    c.get("kind", ""),
                    float(c.get("score") or 0),
                    c.get("contract_id", ""),
                    str(c.get("contract_name", ""))[:40],
                    "；".join(c.get("reasons") or [])[:120],
                )
                for c in candidates
            ]
            parts.append(
                format_html(
                    "<div><strong>候选：</strong><ul style='margin:4px 0 4px 18px'>{}</ul></div>",
                    format_html_join("", "{}", ((item,) for item in items)),
                )
            )

        hints = snapshot.get("excluded_hints") or []
        if hints:
            hint_items = [
                format_html(
                    '<li>[{}] <a href="/admin/contracts/contract/{}/change/">{}</a> — {}</li>',
                    h.get("excluded_by", ""),
                    h.get("contract_id", ""),
                    str(h.get("contract_name", ""))[:40],
                    h.get("note", ""),
                )
                for h in hints
            ]
            parts.append(
                format_html(
                    "<div><strong>被排除的线索：</strong><ul style='margin:4px 0 4px 18px'>{}</ul></div>",
                    format_html_join("", "{}", ((item,) for item in hint_items)),
                )
            )

        if not parts:
            # 兜底：直接把快照按 JSON 展示，同样必须转义
            parts.append(format_html("<pre>{}</pre>", json.dumps(snapshot, ensure_ascii=False, indent=2)[:2000]))

        return format_html_join("", "{}", ((part,) for part in parts))

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁止后台手工新增：待认领只能由邮件解析产生，手工造会绕过去重键。"""
        return False
