"""首页「待认领」卡右上角那个同步按钮的落地逻辑。

## 为什么需要一个统一入口

待认领下面挂着两类东西：到账款项（`PaymentIntake`）与发票（`InvoiceIntake`）。
它们各有自己的扫描器和 rescan 端点，但用户看到的只是「待认领」一个卡、一个按钮。
让前端去分别调两个接口，就得在 UI 层拼两套加载态与错误态——那是把服务端的
编排职责漏到浏览器里。

所以这里提供**一次调用、两类都收**的入口。

## 按钮按下去究竟发生了什么

1. **兜底补扫近 N 天已入库邮件**（同步、快）：无论 IMAP 同步成不成功，库里已有的
   邮件都先扫一遍。这一步单独就能产出结果，不依赖外部邮箱可用性。
2. **提交 IMAP 同步任务**（异步）：把最近 N 天的新邮件拉进库。拉回来之后
   `imap_fetcher` 会自己触发两类扫描（拉起新邮件时已经接好），所以这里**不等**
   它的结果——django-q 跑完可能是几十秒后，用户不该盯着转圈。

两步都幂等（`dedupe_key` / `invoice_number` 去重），重复点不会产生重复记录。

## 为什么不做成「等同步完再返回」

IMAP 拉取走 django-q 异步队列，最坏情况要一分钟。让 HTTP 请求等在那里，
前端只能显示一个无尽转圈，还可能被浏览器/网关超时掐断。
返回「已提交」+ 让列表在几秒后自动刷新（前端轮询），体验反而更好。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("apps.contracts")

__all__ = ["sync_pending_intakes"]

#: 按钮默认只扫 1 天：这个按钮是「我刚收到东西，让我看看」，
#: 不是「把邮箱历史翻一遍」。更早的走收件箱页的完整同步。
DEFAULT_SYNC_DAYS = 1


def sync_pending_intakes(*, days: int = DEFAULT_SYNC_DAYS, user: Any = None) -> dict[str, Any]:
    """补扫并提交邮件同步。返回两类各自扫出多少条 + 提交了几个来源。"""
    window = max(1, min(int(days), 30))

    payments = _scan_payments(window)
    invoices = _scan_invoices(window)
    submitted = _submit_imap_sync(window, user)

    logger.info(
        "pending_intakes_synced",
        extra={
            "days": window,
            "payment_created": payments.get("created", 0),
            "invoice_created": invoices.get("created", 0),
            "sources_submitted": submitted,
        },
    )
    return {
        "days": window,
        "payment_created": payments.get("created", 0),
        "invoice_created": invoices.get("created", 0),
        "sources_submitted": submitted,
    }


def _scan_payments(days: int) -> dict[str, Any]:
    """到账通知补扫。扫描器自身会吞掉单封邮件的异常，不会把整次同步带崩。"""
    try:
        from apps.contracts.services.payment.intake_scanner import scan_since

        return dict(scan_since(days=days))
    except Exception:
        logger.warning("pending_sync_payment_scan_failed", exc_info=True)
        return {"created": 0}


def _scan_invoices(days: int) -> dict[str, Any]:
    """发票补扫。"""
    try:
        from apps.contracts.services.payment.invoice_intake_scanner import scan_since

        return dict(scan_since(days=days))
    except Exception:
        logger.warning("pending_sync_invoice_scan_failed", exc_info=True)
        return {"created": 0}


def _submit_imap_sync(days: int, user: Any) -> int:
    """提交可见 IMAP 来源的同步任务（异步）。返回提交了几个。

    只挑 `poll_interval_minutes > 0` 的来源：材料包/客户上传这类来源没有
    「拉新邮件」这个动作，同步它们只是白跑一轮 fetcher。
    """
    try:
        from django_q.tasks import async_task

        from apps.message_hub.services.inbox_access import visible_sources_qs

        qs = visible_sources_qs(user).filter(is_enabled=True, poll_interval_minutes__gt=0)
        count = 0
        for source in qs:
            # 必须走 django-q 异步：IMAP 拉取最坏要一分钟，同步执行会卡住 HTTP
            # 请求并可能被网关/浏览器超时掐断。入队后立即返回，拉回来的邮件由
            # imap_fetcher 自己触发两类扫描（已接好）。
            try:
                async_task("apps.message_hub.tasks.sync_source_by_id", source.pk, days)
                count += 1
            except Exception:
                logger.warning("pending_sync_source_failed", extra={"source_id": source.pk}, exc_info=True)
        return count
    except Exception:
        logger.warning("pending_sync_submit_failed", exc_info=True)
        return 0
