"""Business logic services."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Case, F, IntegerField, Max, QuerySet, Value, When

from apps.chat_records.models import ChatRecordRecording, ChatRecordScreenshot, ScreenshotSource
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException

from .access_policy import ensure_can_access_project
from .frame_selection_service import FrameSelectionService
from .project_service import ProjectService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User

logger = logging.getLogger("apps.chat_records")


class ScreenshotService:
    MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024

    def __init__(self, *, project_service: ProjectService) -> None:
        self._project_service = project_service

    def list_screenshots(self, *, user: User, project_id: int) -> QuerySet[ChatRecordScreenshot, ChatRecordScreenshot]:
        self._project_service.get_project(user=user, project_id=project_id)
        return ChatRecordScreenshot.objects.filter(project_id=project_id).order_by("ordering", "created_at")


    def get_screenshot(self, *, user: User, screenshot_id: str) -> ChatRecordScreenshot:
        try:
            screenshot: ChatRecordScreenshot = (
                ChatRecordScreenshot.objects.select_related("project").get(id=screenshot_id)
            )
        except ChatRecordScreenshot.DoesNotExist:
            raise NotFoundError(f"截图 {screenshot_id} 不存在") from None
        ensure_can_access_project(user=user, project=screenshot.project)
        return screenshot

    @transaction.atomic
    def upload_screenshots(
        self,
        *,
        user: User,
        project_id: int,
        files: Iterable[UploadedFile],
        deduplicate: bool = True,
        capture_time_seconds: float | None = None,
    ) -> list[ChatRecordScreenshot]:
        project = self._project_service.get_project(user=user, project_id=project_id)
        files_list = [f for f in files if f]
        if not files_list:
            raise ValidationException("请上传至少一张图片")

        if ChatRecordRecording.objects.filter(project_id=project_id).exists() and capture_time_seconds is None:
            raise ValidationException("该项目已上传录屏,不能切换为图片模式")

        max_ordering = (
            ChatRecordScreenshot.objects.filter(project_id=project_id).aggregate(v=Max("ordering")).get("v") or 0
        )
        created: list[ChatRecordScreenshot] = []
        selection_service = FrameSelectionService()

        for idx, file in enumerate(files_list, start=1):
            self._validate_upload_file(file)
            sha256, dhash = self._compute_hashes(file, deduplicate, selection_service)

            if sha256 and ChatRecordScreenshot.objects.filter(project_id=project_id, sha256=sha256).exists():
                continue

            ordering = self._resolve_ordering(project_id, max_ordering + idx, capture_time_seconds)

            screenshot = ChatRecordScreenshot.objects.create(
                project=project,
                image=file,
                ordering=ordering,
                sha256=sha256,
                dhash=dhash,
                capture_time_seconds=capture_time_seconds,
                source=ScreenshotSource.UPLOAD,
            )
            created.append(screenshot)

        if not created:
            raise ValidationException("未新增截图(可能全部重复)")
        return created

    def _validate_upload_file(self, file: UploadedFile) -> None:
        content_type = (getattr(file, "content_type", "") or "").lower()
        if not content_type.startswith("image/"):
            raise ValidationException("仅支持上传图片文件")
        size = int(getattr(file, "size", 0) or 0)
        if size > self.MAX_IMAGE_SIZE_BYTES:
            raise ValidationException("图片过大(单张最大 20MB)")

    def _compute_hashes(
        self, file: UploadedFile, deduplicate: bool, selection_service: FrameSelectionService
    ) -> tuple[str, str]:
        if not deduplicate:
            return "", ""
        try:
            content = file.read()
            file.seek(0)
        except Exception:
            logger.exception("截图文件读取失败: %s", getattr(file, 'name', '<unknown>'))
            raise ValidationException(_("截图文件读取失败，无法进行去重"))
        if not content:
            return "", ""
        return hashlib.sha256(content).hexdigest(), selection_service.calc_dhash_hex(content)

    def _resolve_ordering(self, project_id: int, default_ordering: int, capture_time_seconds: float | None) -> int:
        if capture_time_seconds is None:
            return default_ordering
        try:
            capture_time_seconds = float(capture_time_seconds)
        except Exception:
            logger.exception(
                "capture_time_seconds 转换失败",
                extra={"capture_time_seconds": capture_time_seconds, "project_id": project_id},
            )
            return default_ordering

        # Lock all rows for this project to prevent concurrent ordering conflicts.
        # The caller (upload_screenshots) already wraps this in @transaction.atomic.
        locked_qs: QuerySet[ChatRecordScreenshot, ChatRecordScreenshot] = (
            ChatRecordScreenshot.objects.select_for_update()
            .filter(project_id=project_id)
        )

        insert_before = (
            locked_qs.filter(
                capture_time_seconds__isnull=False,
                capture_time_seconds__gt=capture_time_seconds,
            )
            .order_by("ordering", "created_at")
            .first()
        )
        if insert_before:
            ordering = int(insert_before.ordering or 1)
        else:
            ordering = (locked_qs.aggregate(v=Max("ordering")).get("v") or 0) + 1

        locked_qs.filter(ordering__gte=ordering).update(ordering=F("ordering") + 1)
        return ordering

    @transaction.atomic
    def update_screenshot(
        self, *, user: User, screenshot_id: str, title: str | None = None, note: str | None = None
    ) -> ChatRecordScreenshot:
        screenshot = self.get_screenshot(user=user, screenshot_id=screenshot_id)
        update_fields: list[str] = []
        if title is not None:
            screenshot.title = title
            update_fields.append("title")
        if note is not None:
            screenshot.note = note
            update_fields.append("note")
        if not update_fields:
            return screenshot
        screenshot.full_clean()
        screenshot.save(update_fields=update_fields)
        return screenshot

    @transaction.atomic
    def delete_screenshot(self, *, user: User, screenshot_id: str) -> dict[str, bool]:
        screenshot = self.get_screenshot(user=user, screenshot_id=screenshot_id)
        screenshot.delete()
        return {"success": True}

    @transaction.atomic
    def reorder_screenshots(self, *, user: User, project_id: int, screenshot_ids: list[str]) -> dict[str, bool]:
        self._project_service.get_project(user=user, project_id=project_id)
        existing_ids = set(ChatRecordScreenshot.objects.filter(project_id=project_id).values_list("id", flat=True))
        if existing_ids != set(screenshot_ids):
            raise ValidationException("截图列表不匹配,无法保存顺序")

        cases = [When(id=sid, then=Value(idx)) for idx, sid in enumerate(screenshot_ids, start=1)]
        ChatRecordScreenshot.objects.filter(project_id=project_id).update(
            ordering=Case(*cases, output_field=IntegerField())
        )
        return {"success": True}

    def reorder_by_capture_time(self, project_id: int) -> None:
        """按 capture_time_seconds 排序并批量更新 ordering（CASE/WHEN）。

        最多 2 次数据库查询：1 次查询 ID + 1 次批量更新。
        """
        all_ids = list(
            ChatRecordScreenshot.objects.filter(project_id=project_id)
            .order_by(
                Case(
                    When(capture_time_seconds__isnull=True, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                "capture_time_seconds",
                "created_at",
            )
            .values_list("id", flat=True)
        )
        if not all_ids:
            return
        cases = [When(id=sid, then=Value(idx)) for idx, sid in enumerate(all_ids, start=1)]
        ChatRecordScreenshot.objects.filter(project_id=project_id).update(
            ordering=Case(*cases, output_field=IntegerField())
        )

