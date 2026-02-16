"""
检查数据库性能的管理命令
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "检查数据库性能和索引使用情况"

    def handle(self, *args, **options) -> None:
        self.stdout.write(self.style.SUCCESS("=== 数据库性能检查 ===\n"))
        with connection.cursor() as cursor:
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();")
            size = cursor.fetchone()[0]
            self.stdout.write(f"数据库大小: {size / (1024 * 1024):.2f} MB\n")
        self.stdout.write(self.style.WARNING("表大小统计:"))
        with connection.cursor() as cursor:
            cursor.execute(
                "\n                SELECT\n                    name,\n                    (SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name=m.name) as index_count\n                FROM sqlite_master m\n                WHERE type='table' AND name NOT LIKE 'sqlite_%'\n                ORDER BY name;\n            "
            )
            for row in cursor.fetchall():
                table_name, index_count = row
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                self.stdout.write(f"  {table_name}: {row_count} 行, {index_count} 个索引")
        self.stdout.write(self.style.WARNING("\n索引列表:"))
        with connection.cursor() as cursor:
            cursor.execute(
                "\n                SELECT name, tbl_name, sql\n                FROM sqlite_master\n                WHERE type='index' AND name NOT LIKE 'sqlite_%'\n                ORDER BY tbl_name, name;\n            "
            )
            for row in cursor.fetchall():
                index_name, table_name, sql = row
                self.stdout.write(f"  [{table_name}] {index_name}")
        self.stdout.write(self.style.SUCCESS("\n检查完成！"))
