"""
初始化默认文件夹模板

创建标准的案件文件夹结构模板.

Usage:
    python manage.py init_folder_templates
    python manage.py init_folder_templates --force
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.documents.services.template.folder_template.admin_service import FolderTemplateAdminService


class Command(BaseCommand):
    help: str = "初始化默认文件夹模板"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--force", action="store_true", help="强制重新创建已存在的模板")

    def handle(self, *args, **options: Any) -> None:
        force = options["force"]
        self.stdout.write("开始初始化默认文件夹模板...")
        if force:
            from apps.documents.models import FolderTemplate

            existing_templates = ["顾问项目合同", "非诉项目合同", "民商事案件合同", "民事一审起诉", "民事一审答辩"]
            deleted_count = 0
            for template_name in existing_templates:
                deleted = FolderTemplate.objects.filter(name=template_name).delete()[0]
                deleted_count += deleted
            if deleted_count > 0:
                self.stdout.write(f"删除了 {deleted_count} 个现有模板")
        admin_service = FolderTemplateAdminService()
        result = admin_service.initialize_default_templates()
        if result["success"]:
            created_count = result.get("created_count", 0)
            skipped_count = result.get("skipped_count", 0)
            if created_count > 0:
                self.stdout.write(self.style.SUCCESS(f"✅ 成功创建 {created_count} 个默认模板"))
            if skipped_count > 0:
                self.stdout.write(self.style.WARNING(f"⚠️ 跳过 {skipped_count} 个已存在的模板"))
            if created_count == 0 and skipped_count == 0:
                self.stdout.write(self.style.WARNING("⚠️ 没有可初始化的模板"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ 初始化失败:{result.get('error', '未知错误')}"))
        self.stdout.write("初始化完成!")
