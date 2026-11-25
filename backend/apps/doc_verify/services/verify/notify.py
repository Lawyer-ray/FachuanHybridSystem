"""把「检出红线」变成一条待办（reminders），进日历/待办流。

## 为什么只在「真检出问题」时建待办

待办流的价值来自稀缺：里面每一条都该值得律师放下手里的事看一眼。灰的
（图片页比不了）、干净的（正文逐项比过）、字节相同的（原样回传）也往里塞，
律师很快就会整体忽略这个流——那比不提醒更糟。所以触发条件是两条同时成立：
`state` 落在阻塞集合（`changed` / `unverifiable`）**且** findings 里至少一条
`severity == "red"`。

## 为什么不按承办律师拆行（一个 run → N 条待办）

`Reminder` 没有「收件人」字段，谁能看到是由 `reminder_read_scope` 算的：绑了
案件的提醒对该案 `CaseAccessPolicy` 可见人（= 全部承办律师）可见，是**同一行**。
按人拆行的话，3 个承办律师会各自在日历里看到 3 条一模一样的待办
（`ReminderType.OTHER` 不进 `calendar_view_service.merge_events` 的合并口径），
待办流当场变噪声。反过来，把提醒做成不绑案件、只靠 `created_by` 定向，案件详情
的提醒列表（按 `case_id` 过滤）就看不到它了，而律师判断「这份件要不要放行」正
需要案卷上下文。所以：一件事、一行、绑案件。留痕在 append-only 的
`VerificationDecision` 上，`Reminder` 只是待办——谁处理完谁勾掉，不需要每人各勾一次。

## 为什么查重要查 metadata 而不是「列表里翻一遍」

同一份回传件会被多条链路看见（邮件附件 / 回传链接 / 归案上传），编排层的
`run_key` 已把它们收敛成同一行 run；这里再用 `metadata.doc_verify_run_id` 把
「这件事已经通知过」收敛成一条待办。升层重核（同一 run 从免费层升到 OCR 层、
结论从「未发现差异」变成「疑似改动」）也是同一个 run，同样不该再建一条。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.doc_verify.domain.contracts import Severity
from apps.doc_verify.domain.states import BLOCKING_STATES

logger = logging.getLogger(__name__)

#: 红线待办的到期时间：不是「今天必须处理」，但也不能无限挂着。
REMINDER_DUE_IN_DAYS = 3

#: 通知失败只能吞掉「这条待办没写成」，绝不能连带把核对结论搞挂。
#: `ValidationException` 单列：reminders 服务的 `create_reminder` 抛的是
#: `apps.core.exceptions.ValidationException`，与 Django 的 `ValidationError` 不同源。
NOTIFY_FAILURES: tuple[type[Exception], ...] = (
    DatabaseError,
    ObjectDoesNotExist,
    ValidationError,
    ValidationException,
    ValueError,
)


def notify_pending_decision(*, run: Any, actor: Any = None) -> int:
    """检出红线时给承办律师建一条待办；返回本次新建的条数（0 或 1，永不抛异常）。

    调用点必须在 run 落库**之后**：待办通知的是「这一行结论」，不是「打算核」。
    """
    try:
        return _notify_pending_decision(run=run, actor=actor)
    except NOTIFY_FAILURES as exc:
        logger.warning(
            "回传件红线待办写入失败（核对结论不受影响）: run=%s error=%s",
            getattr(run, "pk", None),
            exc,
        )
        return 0


def reminder_content(run: Any) -> str:
    """给人看的一句话：文书名 + 红线数 + 前两条 code。

    前两条就够：一条红线已经足够让律师去开核对报告，把 20 个 code 塞进待办
    标题只会让它读不成句子（`Reminder.content` 上限 255 字）。
    """
    findings = _red_findings(run)
    artifact = getattr(run, "artifact", None)
    doc_type = str(getattr(artifact, "doc_type", "") or "回传件")
    codes = "、".join(str(finding.get("code", "")) for finding in findings[:2])
    head = f"回传件《{doc_type}》检出 {len(findings)} 条红线"
    return f"{head}（{codes}），请裁决" if codes else f"{head}，请裁决"


def _notify_pending_decision(*, run: Any, actor: Any) -> int:
    if str(getattr(run, "state", "")) not in BLOCKING_STATES or not _red_findings(run):
        return 0
    case = _case_of(run)
    if case is None:
        logger.info("回传件核对没有关联案件，不建待办: run=%s", run.pk)
        return 0
    if not case.assignments.exists():
        logger.info(
            "案件没有指派承办律师，不建待办（case 绑定的提醒没有任何人看得见）: run=%s case=%s",
            run.pk,
            case.pk,
        )
        return 0
    if _already_notified(run):
        logger.info("回传件红线待办已存在，不重复建: run=%s", run.pk)
        return 0
    _create_pending_reminder(run=run, case=case, actor=actor)
    logger.info("回传件检出红线，已建待办: run=%s case=%s", run.pk, case.pk)
    return 1


def _red_findings(run: Any) -> list[dict[str, Any]]:
    """落库的发现项里 `severity == red` 的那些（形状见 `Finding.as_dict`）。"""
    findings = getattr(run, "findings", None)
    if not isinstance(findings, list):
        return []
    return [
        finding
        for finding in findings
        if isinstance(finding, dict) and str(finding.get("severity", "")) == Severity.RED
    ]


def _case_of(run: Any) -> Any | None:
    """run → 出站基线 → 案件。基线或案件为空时返回 None（不建待办）。"""
    artifact = getattr(run, "artifact", None)
    if artifact is None:
        return None
    return getattr(artifact, "case", None)


def _already_notified(run: Any) -> bool:
    """这次 run 是否已经通知过（同一份回传件只该有一条待办）。

    读走 JSONField 包含查询：reminders 的 service 没有按 metadata 查的口子，
    写仍必须走 service（四层：Service 不直接写别人的 Model），所以这里只**读**
    一次它的模型。
    """
    from apps.reminders.models import Reminder

    return Reminder.objects.filter(metadata__doc_verify_run_id=run.pk).exists()


def _create_pending_reminder(*, run: Any, case: Any, actor: Any) -> None:
    """走 reminders 的 service 建待办（构造口径与它的既有调用方一致：wiring 组合根）。"""
    from apps.reminders.models import ReminderType
    from apps.reminders.services.wiring import get_reminder_service

    get_reminder_service().create_reminder(
        case_id=case.pk,
        reminder_type=ReminderType.OTHER,
        content=reminder_content(run),
        due_at=timezone.now() + timedelta(days=REMINDER_DUE_IN_DAYS),
        metadata=_reminder_metadata(run),
        created_by=actor,
    )


def _reminder_metadata(run: Any) -> dict[str, Any]:
    """待办的溯源三件套；`doc_verify_run_id` 同时是查重键，键名不要改。"""
    return {
        "doc_verify_run_id": run.pk,
        "doc_verify_doc_type": run.artifact.doc_type,
        "doc_verify_state": run.state,
    }
