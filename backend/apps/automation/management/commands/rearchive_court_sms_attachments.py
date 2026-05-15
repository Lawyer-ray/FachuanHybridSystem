from __future__ import annotations

from argparse import BooleanOptionalAction
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.automation.models import CourtSMS
from apps.cases.services.log.case_log_attachment_storage_service import CaseLogAttachmentStorageService


class Command(BaseCommand):
    help = "批量将历史法院短信日志附件从 media 重归档到案件目录推荐子目录。"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--sms-id", type=int, default=None, help="仅处理指定法院短信 ID")
        parser.add_argument("--case-id", type=int, default=None, help="仅处理指定案件 ID 下的法院短信")
        parser.add_argument("--dry-run", action="store_true", help="仅预演，不写库、不移动文件")
        parser.add_argument(
            "--only-media",
            action=BooleanOptionalAction,
            default=True,
            help="是否只处理仍存放在 media 下的附件，默认开启",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        sms_id = options.get("sms_id")
        case_id = options.get("case_id")
        dry_run = bool(options.get("dry_run"))
        only_media = bool(options.get("only_media", True))

        queryset = (
            CourtSMS.objects.select_related("case", "case_log")
            .prefetch_related("case_log__attachments")
            .order_by("id")
        )
        if sms_id:
            queryset = queryset.filter(id=sms_id)
        if case_id:
            queryset = queryset.filter(case_id=case_id)

        total_sms = queryset.count()
        if total_sms == 0:
            self.stdout.write(self.style.WARNING("未找到可处理的法院短信"))
            return

        storage_service = CaseLogAttachmentStorageService()
        seen_attachment_ids: set[int] = set()

        scanned_sms = 0
        scanned_attachments = 0
        planned_moves = 0
        moved_count = 0
        skipped_count = 0
        failed_count = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("当前为 dry-run 模式，不会写库或移动文件"))

        for sms in queryset:
            scanned_sms += 1

            if not sms.case_id:
                skipped_count += 1
                self.stdout.write(self.style.WARNING(f"[SKIP] sms={sms.id}: 未绑定案件"))
                continue
            if not sms.case_log_id:
                skipped_count += 1
                self.stdout.write(self.style.WARNING(f"[SKIP] sms={sms.id}: 未生成案件日志"))
                continue

            attachments = list(sms.case_log.attachments.all()) if sms.case_log else []
            if not attachments:
                skipped_count += 1
                self.stdout.write(self.style.WARNING(f"[SKIP] sms={sms.id}: 案件日志下没有附件"))
                continue

            for attachment in attachments:
                attachment_id = int(attachment.id)
                if attachment_id in seen_attachment_ids:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"[SKIP] sms={sms.id} attachment={attachment_id}: 附件已在本次任务中处理过")
                    )
                    continue
                seen_attachment_ids.add(attachment_id)
                scanned_attachments += 1

                plan = self._build_move_plan(
                    sms=sms,
                    attachment=attachment,
                    storage_service=storage_service,
                    only_media=only_media,
                )
                skip_reason = str(plan.get("skip_reason") or "").strip()
                if skip_reason:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f"[SKIP] sms={sms.id} attachment={attachment_id}: {skip_reason}")
                    )
                    continue

                source_path = str(plan["source_abs_path"])
                target_subdir = str(plan["target_subdir"])
                target_name = str(plan["preferred_name"])
                if dry_run:
                    planned_moves += 1
                    self.stdout.write(
                        f"[PLAN] sms={sms.id} attachment={attachment_id}: {source_path} -> {target_subdir}/{target_name}"
                    )
                    continue

                try:
                    moved = self._apply_move(
                        sms=sms,
                        attachment=attachment,
                        storage_service=storage_service,
                        target_subdir=target_subdir,
                    )
                except Exception as exc:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"[FAIL] sms={sms.id} attachment={attachment_id}: {exc!s}")
                    )
                    continue

                moved_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[MOVED] sms={sms.id} attachment={attachment_id}: "
                        f"{source_path} -> {moved.relative_file_path}"
                    )
                )

        summary = (
            f"检查短信 {scanned_sms} 条，扫描附件 {scanned_attachments} 个，"
            f"{'计划迁移' if dry_run else '成功迁移'} {planned_moves if dry_run else moved_count} 个，"
            f"跳过 {skipped_count} 个，失败 {failed_count} 个"
        )
        if failed_count:
            self.stdout.write(self.style.ERROR(summary))
        elif dry_run:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _build_move_plan(
        self,
        *,
        sms: CourtSMS,
        attachment: Any,
        storage_service: CaseLogAttachmentStorageService,
        only_media: bool,
    ) -> dict[str, str]:
        root_type = str(getattr(attachment, "storage_root_type", "") or "media").strip() or "media"
        if root_type == "case_folder":
            return {"skip_reason": "附件已在案件目录，无需重复归档"}
        if only_media and root_type != "media":
            return {"skip_reason": f"当前存储根为 {root_type}，默认只处理 media 附件"}
        if not sms.case_id:
            return {"skip_reason": "法院短信未绑定案件，无法计算推荐目录"}

        resolved = storage_service.resolve_attachment(attachment)
        if not resolved.exists or not resolved.abs_path:
            return {"skip_reason": "源文件不存在，无法迁移"}

        preferred_name = self._resolve_preferred_name(attachment=attachment, resolved_abs_path=resolved.abs_path)
        recommendation = storage_service.recommend_attachment_subdir(
            case_id=int(sms.case_id),
            log=getattr(sms, "case_log", None),
            file_name=Path(resolved.abs_path).name,
            source_scene="court_sms_attachment",
            recommendation_file_name=preferred_name,
            perm_open_access=True,
        )
        target_subdir = str(recommendation.get("recommended_subdir") or "").strip()
        if not target_subdir:
            return {"skip_reason": "未获取到推荐子目录"}

        return {
            "source_abs_path": str(resolved.abs_path),
            "target_subdir": target_subdir,
            "preferred_name": preferred_name,
        }

    @transaction.atomic
    def _apply_move(
        self,
        *,
        sms: CourtSMS,
        attachment: Any,
        storage_service: CaseLogAttachmentStorageService,
        target_subdir: str,
    ) -> Any:
        if not sms.case_id:
            raise ValueError("法院短信未绑定案件，无法迁移附件")

        moved = storage_service.move_attachment(
            attachment,
            case_id=int(sms.case_id),
            target_subdir=target_subdir,
        )
        attachment.file = moved.relative_file_path
        attachment.storage_root_type = moved.root_type
        attachment.subdir_path = moved.subdir_path
        attachment.relative_file_path = moved.relative_file_path
        if not str(getattr(attachment, "original_filename", "") or "").strip():
            attachment.original_filename = moved.original_filename
            update_fields = [
                "file",
                "storage_root_type",
                "subdir_path",
                "relative_file_path",
                "original_filename",
            ]
        else:
            update_fields = [
                "file",
                "storage_root_type",
                "subdir_path",
                "relative_file_path",
            ]
        attachment.save(update_fields=update_fields)
        return moved

    def _resolve_preferred_name(self, *, attachment: Any, resolved_abs_path: str) -> str:
        original_name = str(getattr(attachment, "original_filename", "") or "").strip()
        if original_name:
            return original_name

        relative_path = str(getattr(attachment, "relative_file_path", "") or "").strip()
        if relative_path:
            return Path(relative_path).name

        file_name = str(getattr(getattr(attachment, "file", None), "name", "") or "").strip()
        if file_name:
            return Path(file_name).name

        return Path(str(resolved_abs_path)).name
