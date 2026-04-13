from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "检查数据库性能和索引使用情况"

    def handle(self, *args: Any, **options: Any) -> None:
        vendor = connection.vendor
        self.stdout.write(self.style.SUCCESS("=== 数据库性能检查 ===\n"))
        self.stdout.write(f"数据库引擎: {vendor}\n")

        if vendor == "sqlite":
            self._check_sqlite()
            return

        if vendor == "postgresql":
            self._check_postgresql()
            return

        self.stdout.write(self.style.WARNING("当前命令仅对 SQLite / PostgreSQL 提供详细分析"))

    def _check_sqlite(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();")
            size = cursor.fetchone()[0]
            self.stdout.write(f"数据库大小: {size / (1024 * 1024):.2f} MB\n")

        self.stdout.write(self.style.WARNING("表大小统计:"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    name,
                    (SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name=m.name) as index_count
                FROM sqlite_master m
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name;
            """
            )
            for row in cursor.fetchall():
                table_name, index_count = row
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")  # nosec B608
                row_count = cursor.fetchone()[0]
                self.stdout.write(f"  {table_name}: {row_count} 行, {index_count} 个索引")

        self.stdout.write(self.style.WARNING("\n索引列表:"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT name, tbl_name, sql
                FROM sqlite_master
                WHERE type='index' AND name NOT LIKE 'sqlite_%'
                ORDER BY tbl_name, name;
            """
            )
            for row in cursor.fetchall():
                index_name, table_name, _sql = row
                self.stdout.write(f"  [{table_name}] {index_name}")

        self.stdout.write(self.style.SUCCESS("\n检查完成！"))

    def _check_postgresql(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_database_size(current_database());
                """
            )
            size = cursor.fetchone()[0]
            self.stdout.write(f"数据库大小: {size / (1024 * 1024):.2f} MB\n")

        self.stdout.write(self.style.WARNING("表大小统计:"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    schemaname,
                    relname,
                    n_live_tup::bigint,
                    pg_total_relation_size(format('%I.%I', schemaname, relname))
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(format('%I.%I', schemaname, relname)) DESC;
                """
            )
            for schema_name, table_name, row_count, total_size in cursor.fetchall():
                self.stdout.write(f"  {schema_name}.{table_name}: {row_count} 行, {total_size / (1024 * 1024):.2f} MB")

        self.stdout.write(self.style.WARNING("\n索引列表:"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    schemaname,
                    tablename,
                    indexname
                FROM pg_indexes
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schemaname, tablename, indexname;
                """
            )
            for schema_name, table_name, index_name in cursor.fetchall():
                self.stdout.write(f"  [{schema_name}.{table_name}] {index_name}")

        self.stdout.write(self.style.SUCCESS("\n检查完成！"))
