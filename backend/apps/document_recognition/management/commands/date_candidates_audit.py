"""存量关键日期候选的复核命令（默认 dry-run，只出清单不写库）。

## 为什么需要它

2026-11-24 之前落库的候选是「没有出处」的：只有 ``(due_at, type, confidence)``，
无法区分「原文写明」与「规则按错误的锚点算出来的」。那两条实测误报
（告知书 2026-11-27、退费须知 2026-12-01）就是这种形态。新闸门只影响新识别的
文书，存量行必须重判一次，否则律师还会在待确认列表里看到旧假日期。

## 判定口径

用**当时的原文**（``task.raw_text``）+ 同批文书清单重跑
``build_date_candidates``，得到「新规则下应该存在的候选集合」：

- 行不在新集合里 → ``--apply`` 时置 ``skipped`` + ``discarded_by_gate``（**不硬删**，
  律师追问时要能查到「为什么没了」）；
- 行仍在集合里 → 按新结果更新 ``review_flags`` / ``default_checked`` / ``anchor_*``；
- 已 ``confirmed``（律师已确认写入日历）的一律**不动**，只列入「人工回看」清单——
  那是已被人工确认过的事实，不该由脚本改写。

## 用法

```bash
# 只看清单（默认）
uv run python apiSystem/manage.py date_candidates_audit --sms 300
# 应用
uv run python apiSystem/manage.py date_candidates_audit --sms 300 --apply
```
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionTask


class Command(BaseCommand):
    help = "按当前日期闸门口径复核存量候选（默认 dry-run）"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--sms", type=int, default=None, help="只处理某条法院短信派生的任务")
        parser.add_argument("--task", type=int, default=None, help="只处理某个识别任务")
        parser.add_argument("--apply", action="store_true", default=False, help="实际写库；不传则只打印清单")
        parser.add_argument("--limit", type=int, default=500, help="最多处理多少个任务（默认 500）")

    def handle(self, *args: Any, **options: Any) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.services.date_candidate_service import (
            build_date_candidates,
            refresh_task_confirmation_status,
        )

        qs = DocumentRecognitionTask.objects.exclude(raw_text="")
        if options["sms"]:
            qs = qs.filter(source_court_sms_id=options["sms"])
        if options["task"]:
            qs = qs.filter(id=options["task"])
        apply = bool(options["apply"])
        if apply and not (options["sms"] or options["task"]):
            raise CommandError("--apply 必须配合 --sms 或 --task 限定范围（避免一条命令改全表）")
        tasks = list(qs.order_by("id")[: int(options["limit"])])

        total_drop = total_update = total_keep = 0
        manual_review: list[str] = []

        for task in tasks:
            pending = [row for row in task.date_candidates.all() if row.status == DateCandidateStatus.PENDING]
            if not pending:
                continue
            siblings: list[str] = []
            if task.source_court_sms_id:
                siblings = list(
                    DocumentRecognitionTask.objects.filter(source_court_sms_id=task.source_court_sms_id).values_list(
                        "original_filename", flat=True
                    )
                )
            received = None
            if task.source_court_sms_id:
                from apps.automation.models import CourtSMS

                sms = CourtSMS.objects.filter(id=task.source_court_sms_id).only("received_at").first()
                received = sms.received_at if sms else None

            try:
                doc_type = DocumentType(task.document_type)
            except ValueError:
                doc_type = DocumentType.OTHER

            drafts = build_date_candidates(
                task.raw_text,
                None,
                doc_type,
                received_at=received,
                sibling_documents=siblings,
            )
            fresh = {(d.due_at.date(), d.reminder_type) for d in drafts}

            for row in pending:
                key = (row.due_at.date(), row.reminder_type)
                label = f"task={task.id} row={row.id} {row.due_at.date()} {row.reminder_type}"
                if key not in fresh and row.derivation not in ("rule_relative", "rule_period"):
                    # 明文日期（LLM 读到 / 正则读到）复现不出来，很可能是重跑条件不同
                    # （task.raw_text 落库时已截断到 10000 字），不能因此判它该丢。
                    total_keep += 1
                    self.stdout.write(f"[SKIP] {label} | 明文日期无法复现，需人工判断（不写库）")
                    continue
                if key not in fresh:
                    total_drop += 1
                    self.stdout.write(f"[DROP] {label} | {task.original_filename[:30]}")
                    if apply:
                        flags = list(row.review_flags or [])
                        from apps.document_recognition.services.date_candidate_policy import FLAG_DISCARDED

                        if FLAG_DISCARDED not in flags:
                            flags.append(FLAG_DISCARDED)
                        row.review_flags = flags
                        row.status = DateCandidateStatus.SKIPPED
                        row.default_checked = False
                        row.save(update_fields=["review_flags", "status", "default_checked", "updated_at"])
                    continue

                match = next(d for d in drafts if (d.due_at.date(), d.reminder_type) == key)
                changed = (
                    list(row.review_flags or []) != list(match.review_flags)
                    or bool(row.default_checked) != bool(match.default_checked)
                    or row.derivation != match.derivation
                )
                if changed:
                    total_update += 1
                    self.stdout.write(
                        f"[FLAG] {label} | flags={list(match.review_flags)} default_checked={match.default_checked}"
                    )
                    if apply:
                        row.review_flags = list(match.review_flags)
                        row.default_checked = bool(match.default_checked)
                        row.derivation = match.derivation or row.derivation
                        row.anchor_kind = match.anchor_kind or row.anchor_kind
                        row.anchor_at = match.anchor_at or row.anchor_at
                        row.anchor_document = match.anchor_document or row.anchor_document
                        row.save(
                            update_fields=[
                                "review_flags",
                                "default_checked",
                                "derivation",
                                "anchor_kind",
                                "anchor_at",
                                "anchor_document",
                                "updated_at",
                            ]
                        )
                else:
                    total_keep += 1

            confirmed = [row for row in task.date_candidates.all() if row.status == DateCandidateStatus.CONFIRMED]
            if confirmed:
                manual_review.append(f"task={task.id} 已确认 {len(confirmed)} 条（不动，供人工回看）")

            if apply:
                refresh_task_confirmation_status(task)

        self.stdout.write("")
        self.stdout.write(
            f"汇总：待丢弃 {total_drop} · 需更新标记 {total_update} · 无需变动 {total_keep}"
            f" · 模式={'APPLY' if apply else 'DRY-RUN'}"
        )
        for line in manual_review:
            self.stdout.write(f"  [回看] {line}")
        if not apply:
            self.stdout.write("（未写库；确认清单无误后加 --apply 执行）")
