"""PaymentIntake Admin —— 到账待认领。

后台只读为主：待认领的正常处理路径是**前端首页的确认模块**（设计文档 §9），
后台用于排查"为什么这条没匹配上"——因此把解析结果、候选快照、被排除线索
全部摊开显示，且不提供"直接改状态"的自由编辑（财务数据要留痕）。
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

from apps.contracts.models import IntakeStatus, PaymentIntake
from apps.core.admin.base import BaseModelAdmin


@admin.register(PaymentIntake)
class PaymentIntakeAdmin(BaseModelAdmin):  # pragma: no cover
    list_display = [
        "id",
        "received_at",
        "amount",
        "payer_display",
        "status_badge",
        "suggested_contract",
        "confirmed_contract",
        "payment_link",
    ]
    list_filter: ClassVar = ["status", "received_at"]
    search_fields: ClassVar = ("payer_name", "on_behalf_of", "bank_remark")
    autocomplete_fields: ClassVar = ("inbox_message", "suggested_contract", "confirmed_contract", "confirmed_by")
    readonly_fields: ClassVar = [
        "dedupe_key",
        "match_snapshot_pretty",
        "bank_remark",
        "created_at",
        "updated_at",
    ]
    date_hierarchy = "received_at"
    ordering: ClassVar = ["-received_at", "-id"]

    fieldsets: ClassVar = (
        (
            "到账信息",
            {
                "fields": (
                    "inbox_message",
                    "amount",
                    "received_at",
                    "payer_name",
                    "on_behalf_of",
                    "bank_remark",
                )
            },
        ),
        ("系统建议（只读）", {"fields": ("suggested_contract", "match_snapshot_pretty")}),
        (
            "人工裁定",
            {
                "fields": (
                    "status",
                    "confirmed_contract",
                    "confirmed_by",
                    "confirmed_at",
                    "payment",
                    "decision_note",
                )
            },
        ),
        ("元信息", {"fields": ("dedupe_key", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="状态")
    def status_badge(self, obj: PaymentIntake) -> SafeString:
        colors: dict[str, str] = {
            IntakeStatus.PENDING: "#007bff",
            IntakeStatus.CONFIRMED: "#28a745",
            IntakeStatus.REJECTED: "#6c757d",
            IntakeStatus.IGNORED: "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="付款人")
    def payer_display(self, obj: PaymentIntake) -> str:
        return obj.display_payer

    @admin.display(description="收款记录")
    def payment_link(self, obj: PaymentIntake) -> SafeString:
        if not obj.payment_id:
            return format_html("-")
        return format_html(
            '<a href="/admin/contracts/contractpayment/{}/change/">{}</a>', obj.payment_id, obj.payment_id
        )

    @admin.display(description="匹配快照")
    def match_snapshot_pretty(self, obj: PaymentIntake) -> SafeString:
        """把候选与被排除线索铺开显示，便于排查"为什么没匹配上"。

        ⚠️ 这里的内容**全部来自邮件解析**（合同名、付款人、银行备注、匹配理由），
        属于外部可控输入。因此一律走 ``format_html`` 逐项转义，**禁止**用字符串
        拼接 + ``mark_safe``——那样一封构造过的到账邮件就能在后台管理页打 XSS。
        """
        snapshot = obj.match_snapshot or {}
        if not snapshot:
            return format_html("<em>无</em>")

        parts: list[SafeString] = []

        parsed = snapshot.get("parsed") or {}
        if parsed:
            parts.append(
                format_html(
                    "<div><strong>解析：</strong>金额 {} / 付款人 {} / 代付方 {}</div>",
                    parsed.get("amount") or "-",
                    parsed.get("payer_name") or "-",
                    parsed.get("on_behalf_of") or "-",
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
