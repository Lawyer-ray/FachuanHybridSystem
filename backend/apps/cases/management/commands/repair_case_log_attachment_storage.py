"""Repair historical case log attachment storage metadata."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.exceptions import ValidationException
from apps.core.services import BusinessFileStorageService


class Command(BaseCommand):
    help = "修复案件日志附件历史存储路径，将旧绝对路径统一纠正为相对路径"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--case-id", type=int, default=None, help="仅修复指定案件 ID 的日志附件")
        parser.add_argument("--log-id", type=int, default=None, help="仅修复指定日志 ID 的附件")
        parser.add_argument("--dry-run", action="store_true", help="只输出修复结果，不写入数据库")

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.cases.models import CaseLogAttachment

        case_id = options.get("case_id")
        log_id = options.get("log_id")
        dry_run = bool(options.get("dry_run"))

        storage_service = BusinessFileStorageService()
        queryset = CaseLogAttachment.objects.select_related("log").all().order_by("id")
        if case_id:
            queryset = queryset.filter(log__case_id=case_id)
        if log_id:
            queryset = queryset.filter(log_id=log_id)

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("未找到需要检查的案件日志附件"))
            return

        self.stdout.write(f"待检查附件数: {total}")
        if dry_run:
            self.stdout.write(self.style.WARNING("当前为 dry-run 模式，不会写入数据库"))

        scanned = 0
        updated = 0
        skipped = 0

        for attachment in queryset.iterator(chunk_size=200):
            scanned += 1
            patch = self._build_patch(attachment=attachment, storage_service=storage_service)
            if patch is None:
                continue

            if patch.get("skip_reason"):
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"[SKIP] attachment={attachment.id} log={attachment.log_id}: {patch['skip_reason']}"
                    )
                )
                continue

            updated += 1
            self.stdout.write(
                f"[FIX] attachment={attachment.id} log={attachment.log_id} "
                f"file: {patch['old_file_name']} -> {patch['new_file_name']}"
            )
            if dry_run:
                continue

            self._apply_patch(attachment=attachment, patch=patch)

        summary = f"扫描 {scanned} 条，修复 {updated} 条，跳过 {skipped} 条"
        if dry_run:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _build_patch(self, *, attachment: Any, storage_service: BusinessFileStorageService) -> dict[str, str] | None:
        file_name = str(getattr(getattr(attachment, "file", None), "name", "") or "").strip()
        relative_file_path = self._normalize_relative(getattr(attachment, "relative_file_path", ""))
        subdir_path = self._normalize_relative(getattr(attachment, "subdir_path", ""), allow_empty=True)
        original_filename = str(getattr(attachment, "original_filename", "") or "").strip()
        root_type = str(getattr(attachment, "storage_root_type", "") or "media").strip() or "media"

        target_relative = relative_file_path

        if not target_relative:
            target_relative = self._resolve_relative_from_record(
                attachment=attachment,
                storage_service=storage_service,
                file_name=file_name,
            )

        if not target_relative and root_type == "media" and file_name and not os.path.isabs(file_name):
            target_relative = self._normalize_relative(file_name)

        if not target_relative:
            return {
                "skip_reason": "无法推导 relative_file_path，请先确认绑定文件夹和物理文件是否存在",
            }

        new_subdir_path = subdir_path
        if not new_subdir_path:
            new_subdir_path = self._normalize_relative(str(Path(target_relative).parent), allow_empty=True)
            if new_subdir_path == ".":
                new_subdir_path = ""

        new_original_filename = original_filename or Path(target_relative).name or Path(file_name).name
        new_file_name = target_relative if root_type != "media" else target_relative

        if (
            file_name == new_file_name
            and relative_file_path == target_relative
            and subdir_path == new_subdir_path
            and original_filename == new_original_filename
        ):
            return None

        return {
            "old_file_name": file_name,
            "new_file_name": new_file_name,
            "new_relative_file_path": target_relative,
            "new_subdir_path": new_subdir_path,
            "new_original_filename": new_original_filename,
        }

    def _resolve_relative_from_record(
        self,
        *,
        attachment: Any,
        storage_service: BusinessFileStorageService,
        file_name: str,
    ) -> str:
        try:
            resolved = storage_service.resolve_file(attachment)
        except ValidationException:
            resolved = None

        if resolved and resolved.relative_file_path:
            return self._normalize_relative(resolved.relative_file_path)

        if file_name and not os.path.isabs(file_name):
            return self._normalize_relative(file_name)

        return ""

    @transaction.atomic
    def _apply_patch(self, *, attachment: Any, patch: dict[str, str]) -> None:
        attachment.file = patch["new_file_name"]
        attachment.relative_file_path = patch["new_relative_file_path"]
        attachment.subdir_path = patch["new_subdir_path"]
        attachment.original_filename = patch["new_original_filename"]
        attachment.save(update_fields=["file", "relative_file_path", "subdir_path", "original_filename"])

    def _normalize_relative(self, value: str, *, allow_empty: bool = False) -> str:
        raw = str(value or "").strip().replace("\\", "/")
        if not raw:
            return "" if allow_empty else ""
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts:
            return "" if allow_empty else ""
        if any(part == ".." for part in parts):
            return "" if allow_empty else ""
        return "/".join(parts)
