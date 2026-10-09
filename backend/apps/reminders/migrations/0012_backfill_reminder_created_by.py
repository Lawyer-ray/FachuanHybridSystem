"""回填 Reminder.created_by（安全审计 2026Q4 M-1）。

新增 FK 之前，「创建人」只存在于部分内部路径写入的
``metadata["created_by_user_id"]``（案件日志提醒链路）。全局提醒的写权限
判定依赖 created_by，存量数据必须回填，否则历史全局提醒会因 created_by
为空而被判定为「仅管理员可写」——行为虽然安全，但会让原有创建人突然失去
编辑权，故在此按 metadata 兜底回填。

回填口径：
- 只处理 metadata 里有 created_by_user_id 且该用户仍存在的行；
- 用户已删除、或 metadata 无该键的行保持 NULL——由管理员兜底（fail-closed）；
- 同时回填 HistoricalReminder，保持审计历史与主表一致。
"""

from __future__ import annotations

from typing import Any

from django.db import migrations

BATCH_SIZE = 1000


def _backfill_rows(model: Any, existing_ids: set[int]) -> int:
    """把 metadata 中的 created_by_user_id 回填到 created_by 列。"""
    qs = model.objects.filter(created_by__isnull=True, metadata__has_key="created_by_user_id").values_list(
        "id", "metadata"
    )
    updated = 0
    batch: list[tuple[int, Any]] = []
    for reminder_id, metadata in qs.iterator():
        batch.append((reminder_id, metadata))
        if len(batch) < BATCH_SIZE:
            continue
        updated += _apply_batch(model, batch, existing_ids)
        batch = []
    if batch:
        updated += _apply_batch(model, batch, existing_ids)
    return updated


def _apply_batch(model: Any, batch: list[tuple[int, Any]], existing_ids: set[int]) -> int:
    updated = 0
    for reminder_id, metadata in batch:
        user_id = (metadata or {}).get("created_by_user_id")
        if user_id in existing_ids:
            model.objects.filter(id=reminder_id).update(created_by_id=user_id)
            updated += 1
    return updated


def backfill_created_by(apps: Any, schema_editor: Any) -> None:
    """主表 + 历史表回填。"""
    Reminder = apps.get_model("reminders", "Reminder")
    HistoricalReminder = apps.get_model("reminders", "HistoricalReminder")
    Lawyer = apps.get_model("organization", "Lawyer")

    existing_ids = set(Lawyer.objects.values_list("id", flat=True))
    _backfill_rows(Reminder, existing_ids)
    _backfill_rows(HistoricalReminder, existing_ids)


def noop(apps: Any, schema_editor: Any) -> None:
    """反向迁移不回填（created_by 列本身由 0011 的 RemoveField 处理）。"""


class Migration(migrations.Migration):
    dependencies = [
        ("reminders", "0011_historicalreminder_created_by_reminder_created_by"),
    ]

    operations = [
        migrations.RunPython(backfill_created_by, noop),
    ]
