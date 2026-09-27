"""扫描 django_migrations 的异常记录。

三类异常，根子都是「迁移记录与代码不一致」：

1. **孤儿**：库里有记录、磁盘上没有对应迁移文件。多因「在共享开发库上跑了某个分支的
   迁移，之后分支被丢弃、代码回退」而来。
2. **重复**：同一 ``(app, name)`` 有多行。``django_migrations`` 没有唯一约束，并发执行
   ``migrate`` 时两个进程可能各插一行。
3. **未应用**：磁盘上有迁移文件、库里没记录。正常 ``migrate`` 前的临时状态；长期存在
   说明有迁移没跑，可能导致列缺失。

危害不同：**孤儿与重复通常不影响运行**——Django 读 ``applied_migrations`` 得到的是
dict，天然去重，所以功能上无感。但它们会让「记录 vs 代码」的一致性检查失去意义，
并且让 ``COUNT(*)`` 与唯一键数对不上（本项目就因此误判过一次）。**未应用**才是会
直接报错的那类。

用法::

    python apiSystem/manage.py scan_migration_anomalies

存在任一异常时以非零退出码结束，便于挂到部署前检查或本地巡检。
清理前务必先确认「模型与数据库 schema 一致」，否则删记录只是把不一致藏起来。
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "扫描 django_migrations 的异常记录（孤儿 / 重复 / 未应用）"

    def handle(self, *args: object, **options: object) -> None:
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        applied = set(loader.applied_migrations)
        disk = set(loader.disk_migrations)

        orphans = sorted(applied - disk)
        unapplied = sorted(disk - applied)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT app, name, COUNT(*) AS n FROM django_migrations "
                "GROUP BY app, name HAVING COUNT(*) > 1 ORDER BY app, name"
            )
            duplicates = [(str(app), str(name), int(n)) for app, name, n in cur.fetchall()]

        if not (orphans or duplicates or unapplied):
            self.stdout.write(self.style.SUCCESS("迁移记录健康：无孤儿、无重复、无未应用"))
            return

        if orphans:
            self.stdout.write(self.style.WARNING(f"[孤儿] 库有记录、磁盘无文件：{len(orphans)} 条"))
            for app, name in orphans:
                self.stdout.write(f"  {app}.{name}")

        if duplicates:
            self.stdout.write(self.style.WARNING(f"[重复] 同一 (app, name) 多行：{len(duplicates)} 组"))
            for app, name, count in duplicates:
                self.stdout.write(f"  {app}.{name}  出现 {count} 次")

        if unapplied:
            self.stdout.write(self.style.ERROR(f"[未应用] 磁盘有文件、库无记录：{len(unapplied)} 个"))
            for app, name in unapplied:
                self.stdout.write(f"  {app}.{name}")

        self.stdout.write("")
        self.stdout.write("清理方式：确认「模型与数据库 schema 一致」后，从 django_migrations 删除多余行：")
        self.stdout.write(
            "  DELETE FROM django_migrations WHERE app = '<app>' AND name = '<name>';  -- 重复只删多出来的那行"
        )
        self.stdout.write("清理前建议先导出清单留档，便于日后追溯这些记录曾在这个库上存在过。")

        raise CommandError(
            f"迁移记录存在异常：孤儿 {len(orphans)} / 重复 {len(duplicates)} 组 / 未应用 {len(unapplied)}"
        )
