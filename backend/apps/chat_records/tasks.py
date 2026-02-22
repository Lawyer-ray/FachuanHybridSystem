"""Module for tasks."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import tempfile
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, cast

from django.utils import timezone

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.chat_records")


def export_chat_record_task(task_id: str) -> Any:
    from apps.chat_records.models import ChatRecordExportTask, ExportStatus, ExportType
    from apps.chat_records.services.export_service import ExportLayout, ExportService

    try:
        task = ChatRecordExportTask.objects.select_related("project").get(id=task_id)
    except ChatRecordExportTask.DoesNotExist:
        logger.error("导出任务不存在", extra={"task_id": task_id})
        return {"task_id": task_id, "status": "failed", "error": "导出任务不存在"}

    try:
        screenshots = list(task.project.screenshots.all().order_by("ordering", "created_at"))
        if not screenshots:
            raise ValidationException("没有截图,无法导出")

        layout = ExportLayout.from_payload(task.export_type, task.layout or {})

        ChatRecordExportTask.objects.filter(id=task.id).update(
            status=ExportStatus.RUNNING,
            started_at=timezone.now(),
            finished_at=None,
            error="",
            message=_("开始生成文件"),
            progress=0,
            current=0,
            total=len(screenshots),
            updated_at=timezone.now(),
        )

        def on_progress(current: int, total: int, message: str) -> Any:
            progress = int(current * 100 / total) if total else 0
            ChatRecordExportTask.objects.filter(id=task.id).update(
                progress=progress,
                current=current,
                total=total,
                message=message,
                updated_at=timezone.now(),
            )

        export_service = ExportService()
        header_text = layout.header_text or task.project.name
        layout = ExportLayout(
            images_per_page=layout.images_per_page,
            show_page_number=layout.show_page_number,
            header_text=header_text,
        )

        if task.export_type == ExportType.PDF:
            filename = f"梳理聊天记录_{task.project.id}.pdf"
            file_obj = export_service.export_pdf(
                project=task.project,
                screenshots=screenshots,
                layout=layout,
                filename=filename,
                progress_callback=on_progress,
            )
        else:
            filename = f"梳理聊天记录_{task.project.id}.docx"
            file_obj = export_service.export_docx(
                project=task.project,
                screenshots=screenshots,
                layout=layout,
                filename=filename,
                progress_callback=on_progress,
            )

        task.refresh_from_db()
        task.output_file.save(filename, file_obj, save=False)
        task.status = ExportStatus.SUCCESS
        task.progress = 100
        task.current = task.total
        task.message = _("生成完成")
        task.finished_at = timezone.now()
        task.save(
            update_fields=[
                "output_file",
                "status",
                "progress",
                "current",
                "message",
                "finished_at",
                "updated_at",
            ]
        )

        return {"task_id": task_id, "status": "success", "export_type": task.export_type}
    except Exception as e:
        logger.error("导出失败", extra={"task_id": task_id, "error": str(e)}, exc_info=True)
        ChatRecordExportTask.objects.filter(id=task_id).update(
            status=ExportStatus.FAILED,
            error=str(e),
            message=_("生成失败"),
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return {"task_id": task_id, "status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# extract_recording_frames_task 辅助函数 / 数据类
# ---------------------------------------------------------------------------


def _safe_int(raw: Any, default: int) -> int:
    """安全转换为 int,失败返回 default"""
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        logger.exception("操作失败")
        return default


def _safe_float(raw: Any, default: float, lo: float | None = None, hi: float | None = None) -> float:
    """安全转换为 float,可选范围裁剪"""
    if raw is None:
        return default
    try:
        v = float(raw)
    except Exception:
        logger.exception("操作失败")
        return default
    if lo is not None:
        v = max(v, lo)
    if hi is not None:
        v = min(v, hi)
    return v


@dataclass
class _ExtractParams:
    """抽帧参数"""

    interval_seconds: float = 1.0
    strategy: str = "interval"
    interval_based: bool = True
    dedup_threshold: int = 8
    ocr_similarity_threshold: float = 0.92
    ocr_min_new_chars: int = 8

    @classmethod
    def from_recording(cls, recording: Any, interval_seconds: float) -> _ExtractParams:
        interval_seconds = _safe_float(interval_seconds or 1.0, 1.0, lo=0.01)
        strategy = str(getattr(recording, "extract_strategy", "") or "interval").strip().lower()
        dedup_threshold = max(0, _safe_int(getattr(recording, "extract_dedup_threshold", None), 8))
        ocr_similarity_threshold = _safe_float(
            getattr(recording, "extract_ocr_similarity_threshold", None), 0.92, lo=0.0, hi=1.0
        )
        ocr_min_new_chars = max(0, _safe_int(getattr(recording, "extract_ocr_min_new_chars", None), 8))
        return cls(
            interval_seconds=interval_seconds,
            strategy=strategy,
            interval_based=strategy in ("interval", "ocr"),
            dedup_threshold=dedup_threshold,
            ocr_similarity_threshold=ocr_similarity_threshold,
            ocr_min_new_chars=ocr_min_new_chars,
        )


@dataclass
class _DedupState:
    """去重状态"""

    existing_sha256: set[str] = field(default_factory=set)
    seen_sha256: set[str] = field(default_factory=set)
    kept_dhashes: list[str] = field(default_factory=list)
    kept_thumbs: list[bytes] = field(default_factory=list)
    kept_ocr_texts: list[str] = field(default_factory=list)
    kept_ocr_shingles: list[set[str]] = field(default_factory=list)
    created_count: int = 0
    processed_count: int = 0
    ocr_calls: int = 0
    ocr_skipped: int = 0
    ocr_disabled: bool = False


def _shingles(s: str, n: int = 3) -> set[str]:
    s = s or ""
    if not s:
        return set()
    if len(s) <= n:
        return {s}
    return {s[i : i + n] for i in range(0, len(s) - n + 1)}


def _jaccard_sets(sa: set[str], sb: set[str]) -> float:
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0


def _is_dhash_duplicate(
    selection_service: Any, dhash_hex: str, kept_dhashes: list[str], window: int, threshold: int
) -> bool:
    """检查 dhash 是否与最近帧重复"""
    for prev in kept_dhashes[-window:]:
        dist = selection_service.hamming_distance_hex(prev, dhash_hex)
        if dist is not None and dist <= threshold:
            return True
    return False


def _is_pixel_duplicate(
    selection_service: Any, thumb: bytes, kept_thumbs: list[bytes], window: int, threshold: float
) -> bool:
    """检查像素差异是否与最近帧重复"""
    for prev_thumb in kept_thumbs[-window:]:
        diff = selection_service.mean_abs_diff(prev_thumb, thumb)
        if diff is not None and diff <= threshold:
            return True
    return False


def _check_ocr_similarity(
    ocr_text: str,
    state: _DedupState,
    ocr_similarity_threshold: float,
    ocr_min_new_chars: int,
) -> float | None:
    """检查 OCR 文本相似度,返回 frame_score(None 表示不跳过)"""
    if not ocr_text or not state.kept_ocr_texts:
        return None
    cur_set = _shingles(ocr_text)
    best_similarity = 0.0
    for prev_text, prev_set in zip(state.kept_ocr_texts[-4:], state.kept_ocr_shingles[-4:], strict=False):
        if not prev_text:
            continue
        seq_sim = float(SequenceMatcher(None, prev_text, ocr_text).ratio())
        jac_sim = _jaccard_sets(prev_set, cur_set)
        sim = max(seq_sim, jac_sim)
        best_similarity = max(best_similarity, sim)
        new_tokens = len(cur_set - prev_set) if prev_set else len(cur_set)
        if sim >= ocr_similarity_threshold and new_tokens < ocr_min_new_chars:
            return 1.0 - float(sim)  # 返回 score 表示应跳过
    return None  # 不跳过


def _get_ocr_frame_score(best_similarity: float, ocr_text: str, state: _DedupState) -> float:
    """计算 OCR 帧分数"""
    if not ocr_text or not state.kept_ocr_texts:
        return 0.0
    cur_set = _shingles(ocr_text)
    best = 0.0
    for prev_text, prev_set in zip(state.kept_ocr_texts[-4:], state.kept_ocr_shingles[-4:], strict=False):
        if not prev_text:
            continue
        seq_sim = float(SequenceMatcher(None, prev_text, ocr_text).ratio())
        jac_sim = _jaccard_sets(prev_set, cur_set)
        best = max(best, seq_sim, jac_sim)
    return 1.0 - float(best)


def _process_ocr_for_frame(
    content: bytes,
    ocr_service: Any,
    selection_service: Any,
    state: _DedupState,
    params: _ExtractParams,
    soft_deadline: float,
    recording_id: Any,
) -> tuple[str, float | None, bool]:
    """处理单帧的 OCR 去重,返回 (ocr_text, frame_score, should_skip)"""
    from apps.chat_records.models import ChatRecordRecording

    if not ocr_service:
        return "", None, False

    # 检查超时降级
    if not state.ocr_disabled and time.monotonic() > soft_deadline:
        state.ocr_disabled = True
        ChatRecordRecording.objects.filter(id=recording_id).update(
            extract_message=_("接近超时,已降级为图片去重"),
            updated_at=timezone.now(),
        )
        return "", None, False

    # 执行 OCR
    crop_bytes, crop_range = selection_service.crop_for_ocr_bytes_with_range(content)
    if not crop_bytes or crop_range < 18:
        ocr_text = ""
        state.ocr_skipped += 1
    else:
        state.ocr_calls += 1
        ocr_text = ocr_service.extract_text(crop_bytes).text

    ocr_text = re.sub(r"\s+", "", ocr_text or "")
    ocr_text = re.sub(r"[^\w\u4e00-\u9fff]+", "", ocr_text)

    # 空文本且已有帧 → 跳过
    if not ocr_text and state.created_count > 0:
        return ocr_text, None, True

    # 相似度检查
    skip_score = _check_ocr_similarity(ocr_text, state, params.ocr_similarity_threshold, params.ocr_min_new_chars)
    if skip_score is not None:
        return ocr_text, skip_score, True

    frame_score = _get_ocr_frame_score(0.0, ocr_text, state) if ocr_text and state.kept_ocr_texts else None
    return ocr_text, frame_score, False


def _run_ffmpeg_phase(
    service: Any,
    recording: Any,
    info: Any,
    params: _ExtractParams,
    cancel_token: Any,
    ffmpeg_reporter: Any,
    soft_deadline: float,
    tmpdir: str,
) -> tuple[int, Any]:
    """运行 ffmpeg 抽帧阶段"""
    total_estimate = (
        service.estimate_total_frames(info.duration_seconds, params.interval_seconds) if params.interval_based else 0
    )
    from apps.chat_records.models import ChatRecordRecording

    ChatRecordRecording.objects.filter(id=recording.id).update(
        duration_seconds=info.duration_seconds,
        extract_total=total_estimate,
        extract_message=_("抽帧中"),
        updated_at=timezone.now(),
    )

    last_progress = -1
    ffmpeg_timeout = max(30.0, float(soft_deadline) - time.monotonic() - 5.0)
    output_pattern = str(Path(tmpdir) / ("frame_%010d.jpg" if not params.interval_based else "frame_%06d.jpg"))

    def should_cancel() -> bool:
        return cast(bool, cancel_token.is_cancelled())

    for kv in service.iter_ffmpeg_progress(
        video_path=recording.video.path,
        output_pattern=output_pattern,
        interval_seconds=params.interval_seconds,
        strategy=params.strategy,
        should_cancel=should_cancel,
        timeout_seconds=ffmpeg_timeout,
    ):
        if "out_time_ms" not in kv:
            continue
        try:
            out_time_us = int(kv["out_time_ms"])
        except Exception:
            logger.exception("操作失败")
            continue
        out_seconds = out_time_us / 1_000_000.0
        progress = int(out_seconds * 100 / info.duration_seconds) if info.duration_seconds else 0
        progress = min(max(progress, 0), 99)
        if progress != last_progress:
            ffmpeg_reporter.report_extra(progress=progress, current=0, total=total_estimate, message=_("抽帧中"))
            last_progress = progress

    return total_estimate, should_cancel


def _collect_frame_files(tmpdir: str) -> list[str]:
    """收集并排序帧文件"""
    frame_files = [
        str(Path(tmpdir) / f)
        for f in Path(tmpdir).iterdir()
        if f.name.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    frame_files.sort()
    return frame_files


def _calc_capture_time(path: str, index: int, params: _ExtractParams, info: Any) -> float | None:
    """计算帧的捕获时间"""
    if not params.interval_based and info.time_base_seconds:
        m = re.search(r"(\d+)", Path(path).name)
        return float(int(m.group(1)) * float(info.time_base_seconds)) if m else None
    return float(index - 1) * float(params.interval_seconds)


def _update_dedup_state(
    state: _DedupState,
    digest: str,
    dhash_hex: str,
    thumb: bytes,
    ocr_text: str,
    ocr_service: Any,
    pixel_diff_threshold: float,
    selection_service: Any,
    content: bytes,
) -> None:
    """更新去重状态"""
    state.created_count += 1
    state.seen_sha256.add(digest)
    if dhash_hex:
        state.kept_dhashes.append(dhash_hex)
    if pixel_diff_threshold:
        if not thumb:
            thumb = selection_service.calc_thumb_bytes(content)
        if thumb:
            state.kept_thumbs.append(thumb)
    if ocr_service is not None and ocr_text:
        state.kept_ocr_texts.append(ocr_text)
        state.kept_ocr_shingles.append(_shingles(ocr_text))


def _is_frame_duplicate(
    content: bytes,
    digest: str,
    dhash_hex: str,
    state: _DedupState,
    params: _ExtractParams,
    selection_service: Any,
    window: int,
    pixel_diff_threshold: float,
) -> tuple[bool, bytes]:
    """检查帧是否重复,返回 (is_dup, thumb)"""
    if digest in state.existing_sha256 or digest in state.seen_sha256:
        return True, b""
    if (
        params.dedup_threshold
        and state.kept_dhashes
        and _is_dhash_duplicate(selection_service, dhash_hex, state.kept_dhashes, window, params.dedup_threshold)
    ):
        return True, b""
    thumb = b""
    if pixel_diff_threshold and state.kept_thumbs:
        thumb = selection_service.calc_thumb_bytes(content)
        if thumb and _is_pixel_duplicate(selection_service, thumb, state.kept_thumbs, window, pixel_diff_threshold):
            return True, thumb
    return False, thumb


def _process_single_frame(
    path: str,
    index: int,
    recording: Any,
    info: Any,
    params: _ExtractParams,
    state: _DedupState,
    selection_service: Any,
    ocr_service: Any,
    soft_deadline: float,
    base_ordering: int,
    window: int,
    pixel_diff_threshold: float,
) -> bool:
    """处理单帧,返回是否创建了截图"""
    from django.core.files.base import ContentFile

    from apps.chat_records.models import ChatRecordScreenshot, ScreenshotSource

    try:
        with open(path, "rb") as fp:
            content = fp.read()
    except Exception:
        logger.exception("操作失败")
        return False

    digest = sha256(content).hexdigest()
    dhash_hex = selection_service.calc_dhash_hex(content)

    is_dup, thumb = _is_frame_duplicate(
        content, digest, dhash_hex, state, params, selection_service, window, pixel_diff_threshold
    )
    if is_dup:
        return False

    # OCR 去重
    frame_score = None
    ocr_text = ""
    if ocr_service is not None:
        ocr_text, frame_score, should_skip = _process_ocr_for_frame(
            content, ocr_service, selection_service, state, params, soft_deadline, recording.id
        )
        if should_skip:
            return False

    # 创建截图
    capture_time_seconds = _calc_capture_time(path, index, params, info)
    screenshot = ChatRecordScreenshot(
        project_id=recording.project_id,
        ordering=base_ordering + state.created_count + 1,
        sha256=digest,
        dhash=dhash_hex,
        capture_time_seconds=capture_time_seconds,
        source=ScreenshotSource.EXTRACT,
    )
    if ocr_service is not None and frame_score is not None:
        screenshot.frame_score = frame_score
    screenshot.image.save(Path(path).name, ContentFile(content), save=False)
    screenshot.save()

    _update_dedup_state(
        state,
        digest,
        dhash_hex,
        thumb,
        ocr_text,
        ocr_service,
        pixel_diff_threshold,
        selection_service,
        content,
    )
    return True


def _reorder_screenshots(project_id: Any) -> None:
    """重新排序截图"""
    from django.db.models import Case, IntegerField, Value, When

    from apps.chat_records.models import ChatRecordScreenshot

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
    for order, sid in enumerate(all_ids, start=1):
        ChatRecordScreenshot.objects.filter(project_id=project_id, id=sid).update(ordering=order)


def extract_recording_frames_task(
    recording_id: str,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    from django.db.models import Max

    from apps.chat_records.models import ChatRecordRecording, ChatRecordScreenshot, ExtractStatus, ScreenshotSource
    from apps.chat_records.services.frame_selection_service import FrameSelectionService
    from apps.chat_records.services.video_frame_extract_service import VideoFrameExtractService
    from apps.core.interfaces import ServiceLocator
    from apps.core.tasking.runtime import CancellationToken, ProgressReporter, TaskRunContext

    try:
        recording = ChatRecordRecording.objects.select_related("project").get(id=recording_id)
    except ChatRecordRecording.DoesNotExist:
        logger.error("录屏不存在", extra={"recording_id": recording_id})
        return {"recording_id": recording_id, "status": "failed", "error": "录屏不存在"}

    params = _ExtractParams.from_recording(recording, interval_seconds)
    run_ctx = TaskRunContext.from_django_q()
    soft_deadline = float(run_ctx.soft_deadline_monotonic)

    ChatRecordRecording.objects.filter(id=recording.id).update(
        extract_status=ExtractStatus.RUNNING,
        extract_started_at=timezone.now(),
        extract_finished_at=None,
        extract_error="",
        extract_progress=0,
        extract_current=0,
        extract_total=0,
        extract_message=_("准备抽帧"),
        updated_at=timezone.now(),
    )

    service = VideoFrameExtractService()
    selection_service = FrameSelectionService()
    ocr_service = ServiceLocator.get_ocr_service() if params.strategy == "ocr" else None

    try:
        info = service.probe(recording.video.path)

        cancel_token = CancellationToken(
            lambda: bool(
                ChatRecordRecording.objects.filter(id=recording.id)
                .values_list("extract_cancel_requested", flat=True)
                .first()
            )
        )

        def _update_progress(progress: int, current: int, total: int, message: str) -> Any:
            ChatRecordRecording.objects.filter(id=recording.id).update(
                extract_progress=min(int(progress), 99),
                extract_current=int(current),
                extract_total=int(total),
                extract_message=message,
                updated_at=timezone.now(),
            )

        ffmpeg_reporter = ProgressReporter(update_fn=_update_progress, min_interval_seconds=0.5)
        write_reporter = ProgressReporter(update_fn=_update_progress, min_interval_seconds=0.5)

        with tempfile.TemporaryDirectory(prefix="chat_records_frames_") as tmpdir:
            total_estimate, should_cancel = _run_ffmpeg_phase(
                service, recording, info, params, cancel_token, ffmpeg_reporter, soft_deadline, tmpdir
            )

            frame_files = _collect_frame_files(tmpdir)
            total_files = len(frame_files)
            if total_files:
                ChatRecordRecording.objects.filter(id=recording.id).update(
                    extract_total=total_files, updated_at=timezone.now()
                )

            ChatRecordScreenshot.objects.filter(
                project_id=recording.project_id, source=ScreenshotSource.EXTRACT
            ).delete()

            base_ordering = (
                ChatRecordScreenshot.objects.filter(project_id=recording.project_id)
                .aggregate(v=Max("ordering"))
                .get("v")
                or 0
            )

            state = _DedupState(
                existing_sha256=set(
                    ChatRecordScreenshot.objects.filter(project_id=recording.project_id)
                    .exclude(sha256="")
                    .values_list("sha256", flat=True)
                ),
            )
            window = 12 if params.dedup_threshold >= 20 else 6
            pixel_diff_threshold = 2.8 if params.dedup_threshold >= 20 else 0.0

            for index, path in enumerate(frame_files, start=1):
                if should_cancel():
                    raise ValidationException("抽帧已取消")
                state.processed_count += 1

                _process_single_frame(
                    path,
                    index,
                    recording,
                    info,
                    params,
                    state,
                    selection_service,
                    ocr_service,
                    soft_deadline,
                    base_ordering,
                    window,
                    pixel_diff_threshold,
                )

                progress = int(state.processed_count * 100 / total_files) if total_files else 100
                write_reporter.report_extra(
                    progress=min(progress, 99),
                    current=state.created_count,
                    total=total_files,
                    message=_("写入截图"),
                    force=(state.processed_count == total_files),
                )

            _reorder_screenshots(recording.project_id)

        if params.strategy == "ocr":
            logger.info(
                "录屏抽帧 OCR 统计",
                extra={
                    "recording_id": recording_id,
                    "ocr_calls": int(state.ocr_calls),
                    "ocr_skipped": int(state.ocr_skipped),
                    "ocr_disabled": bool(state.ocr_disabled),
                },
            )
        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.SUCCESS,
            extract_progress=100,
            extract_current=state.created_count,
            extract_total=state.created_count,
            extract_message=_("抽帧完成"),
            extract_finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return {"recording_id": recording_id, "status": "success"}
    except Exception as e:
        logger.error("录屏抽帧失败", extra={"recording_id": recording_id, "error": str(e)}, exc_info=True)
        ChatRecordRecording.objects.filter(id=recording.id).update(
            extract_status=ExtractStatus.FAILED,
            extract_error=str(e),
            extract_message=_("抽帧失败"),
            extract_finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return {"recording_id": recording_id, "status": "failed", "error": str(e)}
