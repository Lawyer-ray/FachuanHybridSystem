"""
检查数据库性能的管理命令
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = '检查数据库性能和索引使用情况'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== 数据库性能检查 ===\n'))

        # 检查数据库大小
        with connection.cursor() as cursor:
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();")
            size = cursor.fetchone()[0]
            self.stdout.write(f"数据库大小: {size / (1024 * 1024):.2f} MB\n")

        # 检查表大小
        self.stdout.write(self.style.WARNING('表大小统计:'))
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    name,
                    (SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name=m.name) as index_count
                FROM sqlite_master m
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name;
            """)
            for row in cursor.fetchall():
                table_name, index_count = row
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                self.stdout.write(f"  {table_name}: {row_count} 行, {index_count} 个索引")

        # 检查未使用的索引
        self.stdout.write(self.style.WARNING('\n索引列表:'))
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT name, tbl_name, sql
                FROM sqlite_master
                WHERE type='index' AND name NOT LIKE 'sqlite_%'
                ORDER BY tbl_name, name;
            """)
            for row in cursor.fetchall():
                index_name, table_name, sql = row
                self.stdout.write(f"  [{table_name}] {index_name}")

        self.stdout.write(self.style.SUCCESS('\n检查完成！'))
