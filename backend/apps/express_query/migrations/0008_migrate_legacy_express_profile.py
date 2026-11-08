"""把改造前的共享 profile 目录登记为一个会话，避免升级后所有人重新扫码。

改造前：所有查询共用 ``browser_profiles/express``。
改造后：每个 (律师, 承运商) 一个目录 ``browser_profiles/<carrier>_<lawyer_id>``。

为了不让现有登录态白白作废，这里做两件事：
1. 把旧目录复制给「历史任务最多的律师」（或超级管理员），登记为 active；
2. 旧目录原样保留，不删除——复制失败时仍有回退余地。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.db.models import Count

#: 改造前的共享目录名
LEGACY_DIR_NAME = "express"


def _browser_data_root() -> Path:
    """与 apps.core.services.browser.profiles._BROWSER_DATA_ROOT 保持一致。"""
    backend_dir = Path(settings.BASE_DIR).parent  # backend/
    return backend_dir / "data" / "browser_profiles"


def _pick_owner(apps) -> object | None:
    """选择旧登录态的归属律师：历史任务最多者，否则超级管理员。"""
    ExpressQueryTask = apps.get_model("express_query", "ExpressQueryTask")
    Lawyer = apps.get_model("organization", "Lawyer")

    row = (
        ExpressQueryTask.objects.filter(created_by__isnull=False)
        .values("created_by")
        .order_by()
        .annotate(total=Count("id"))
        .order_by("-total")
        .first()
    )
    if row and row["created_by"]:
        lawyer = Lawyer.objects.filter(id=row["created_by"]).first()
        if lawyer:
            return lawyer

    return Lawyer.objects.filter(is_superuser=True).order_by("id").first() or Lawyer.objects.order_by("id").first()


def forwards(apps, schema_editor):  # pragma: no cover
    ExpressSession = apps.get_model("express_query", "ExpressSession")

    root = _browser_data_root()
    legacy_dir = root / LEGACY_DIR_NAME
    if not legacy_dir.is_dir():
        return  # 没有旧登录态，无需迁移

    owner = _pick_owner(apps)
    if owner is None:
        return  # 库中无律师，跳过

    for carrier in ("ems", "sf"):
        session, created = ExpressSession.objects.get_or_create(
            lawyer=owner,
            carrier_type=carrier,
        )
        if not created and session.status == "active":
            continue

        target_dir = root / f"{carrier}_{owner.id}"
        if not target_dir.exists():
            try:
                shutil.copytree(legacy_dir, target_dir)
            except Exception:
                # 复制失败不影响升级：该律师重新扫码即可
                continue

        session.status = "active"
        session.last_error = "由升级迁移自旧共享目录继承"
        session.save(update_fields=["status", "last_error"])


def backwards(apps, schema_editor):  # pragma: no cover
    """回滚只清会话记录，磁盘目录保留（含登录凭证，不擅自删除）。"""
    ExpressSession = apps.get_model("express_query", "ExpressSession")
    ExpressSession.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("express_query", "0007_expresssession"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
