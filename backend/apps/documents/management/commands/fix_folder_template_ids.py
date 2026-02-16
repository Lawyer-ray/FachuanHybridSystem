"""Django management command."""

from __future__ import annotations

from typing import Any

"\n修复文件夹模板中的重复 ID 问题\n\n用法:python manage.py fix_folder_template_ids\n"
from django.core.management.base import BaseCommand

from apps.documents.models import FolderTemplate
from apps.documents.services.folder_template.id_service import FolderTemplateIdService
from apps.documents.services.folder_template.repair_service import FolderTemplateStructureIdRepairService


class Command(BaseCommand):
    help: str = "修复文件夹模板中的重复 ID 问题"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true", help="只显示需要修复的问题,不实际修改数据")
        parser.add_argument("--template-id", type=int, help="只修复指定 ID 的模板")

    def handle(self, *args, **options: Any) -> None:  # type: ignore
        dry_run = options.get("dry_run", False)
        template_id = options.get("template_id")
        self.stdout.write(self.style.SUCCESS("=== 文件夹模板 ID 修复工具 ===\n"))
        templates = self._get_templates(template_id=template_id)
        if templates is None or not templates:
            return
        repair_service = FolderTemplateStructureIdRepairService(id_service=FolderTemplateIdService())
        self._detect_cross_template_duplicates(repair_service=repair_service, templates=templates)
        total_fixed = self._fix_templates(repair_service=repair_service, templates=templates, dry_run=dry_run)
        self._print_summary(dry_run=dry_run, total_fixed=total_fixed)

    def _get_templates(self, *, template_id: int | None) -> list[FolderTemplate] | None:
        if template_id is not None:
            templates = list(FolderTemplate.objects.filter(id=template_id))
            if not templates:
                self.stdout.write(self.style.ERROR(f"未找到 ID 为 {template_id} 的模板"))
                return None
            return templates
        return list(FolderTemplate.objects.all())

    def _detect_cross_template_duplicates(
        self, *, repair_service: FolderTemplateStructureIdRepairService, templates: list[FolderTemplate]
    ) -> None:
        self.stdout.write("第一步:检测跨模板重复ID...")
        duplicate_ids = repair_service.detect_cross_template_duplicates(templates=templates)
        if duplicate_ids:
            self.stdout.write(f"发现 {len(duplicate_ids)} 个跨模板重复的ID:")
            for dup_id in sorted(duplicate_ids):
                self.stdout.write(f"  - {dup_id}")
        else:
            self.stdout.write("未发现跨模板重复ID")
        self.stdout.write("")

    def _fix_templates(
        self, *, repair_service: FolderTemplateStructureIdRepairService, templates: list[FolderTemplate], dry_run: bool
    ) -> int:
        self.stdout.write("第二步:修复模板ID...")
        total_fixed = 0
        global_used_ids: set[str] = set()
        for template in templates:
            self.stdout.write(f"检查模板: {template.name} (ID: {template.id})")
            if not template.structure or not isinstance(template.structure, dict):
                self.stdout.write("  跳过:无有效结构数据")
                continue
            fixed_structure, changes = repair_service.repair_structure_ids_global(
                structure=template.structure, global_used_ids=global_used_ids
            )
            if changes > 0:
                self.stdout.write(f"  发现 {changes} 个重复或缺失的 ID")
                if not dry_run:
                    template.structure = fixed_structure
                    template.save(update_fields=["structure"])
                    self.stdout.write(self.style.SUCCESS("  ✓ 已修复"))
                    total_fixed += 1
                else:
                    self.stdout.write(self.style.WARNING("  [试运行] 需要修复"))
            else:
                self.stdout.write("  ✓ ID 正常,无需修复")
            self.stdout.write("")
        return total_fixed

    def _print_summary(self, *, dry_run: bool, total_fixed: int) -> None:
        if dry_run:
            self.stdout.write(self.style.WARNING(f"试运行完成,发现 {total_fixed} 个模板需要修复"))
            self.stdout.write("运行 python manage.py fix_folder_template_ids 进行实际修复")
        else:
            self.stdout.write(self.style.SUCCESS(f"修复完成!共修复了 {total_fixed} 个模板"))
