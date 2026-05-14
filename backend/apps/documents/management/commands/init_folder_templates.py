"""Initialize default folder templates."""

from typing import Any

from django.core.management.base import BaseCommand

from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService


class Command(BaseCommand):
    help: str = "初始化默认文件夹模板"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--force", action="store_true", help="强制重新初始化默认模板")

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("开始初始化默认文件夹模板...")

        admin_service = FolderTemplateAdminService()
        result = admin_service.initialize_default_templates()

        if result["success"]:
            created_count = result.get("created_count", 0)
            skipped_count = result.get("skipped_count", 0)

            if created_count > 0:
                self.stdout.write(self.style.SUCCESS(f"成功创建 {created_count} 个默认模板"))
            if skipped_count > 0:
                self.stdout.write(self.style.WARNING(f"跳过 {skipped_count} 个已存在的模板"))
            if created_count == 0 and skipped_count == 0:
                self.stdout.write(self.style.WARNING("没有可初始化的模板"))
        else:
            self.stdout.write(self.style.ERROR(f"初始化失败: {result.get('error', '未知错误')}"))

        self.stdout.write("默认文件夹模板初始化完成")
