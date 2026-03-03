"""帧处理服务 —— 从 tasks.py 拆分的帧级去重 / ffmpeg / 截图写入逻辑。"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path

from apps.chat_records.services.extract_helpers import DedupState, ExtractParams, jaccard_sets, shingles
from apps.chat_records.services.frame_selection_service import FrameSelectionService
from apps.chat_records.services.protocols import ProgressUpdater, ScreenshotCreator
from apps.chat_records.services.video_frame_extract_service import FFProbeInfo, VideoFrameExtractService
from apps.core.protocols.automation_protocols import IOcrService
from apps.core.tasking.runtime import CancellationToken, ProgressReporter

logger = logging.getLogger("apps.chat_records")

# Type alias for the reorder callback
ReorderCallback = Callable[[int], None]


class FrameProcessingService:
    """帧处理服务：封装抽帧流程中的去重、ffmpeg 调度、截图写入等逻辑。"""

    # ------------------------------------------------------------------
    # dhash / pixel 去重
    # ------------------------------------------------------------------

    def is_dhash_duplicate(
        self,
        selection_service: FrameSelectionService,
        dhash_hex: str,
        kept_dhashes: list[str],
        window: int,
        threshold: int,
    ) -> bool:
        """检查 dhash 是否与最近帧重复。"""
        for prev in kept_dhashes[-window:]:
            dist: int | None = selection_service.hamming_distance_hex(prev, dhash_hex)
            if dist is not None and dist <= threshold:
                return True
        return False

    def is_pixel_duplicate(
        self,
        selection_service: FrameSelectionService,
        thumb: bytes,
        kept_thumbs: list[bytes],
        window: int,
        threshold: float,
    ) -> bool:
        """检查像素差异是否与最近帧重复。"""
        for prev_thumb in kept_thumbs[-window:]:
            diff: float | None = selection_service.mean_abs_diff(prev_thumb, thumb)
            if diff is not None and diff <= threshold:
                return True
        return False

    # ------------------------------------------------------------------
    # OCR 相似度
    # ------------------------------------------------------------------

    def check_ocr_similarity(
        self,
        ocr_text: str,
        state: DedupState,
        ocr_similarity_threshold: float,
        ocr_min_new_chars: int,
    ) -> float | None:
        """检查 OCR 文本相似度，返回 frame_score（None 表示不跳过）。"""
        if not ocr_text or not state.kept_ocr_texts:
            return None
        cur_set = shingles(ocr_text)
        best_similarity = 0.0
        for prev_text, prev_set in zip(
            state.kept_ocr_texts[-4:],
            state.kept_ocr_shingles[-4:],
            strict=False,
        ):
            if not prev_text:
                continue
            seq_sim = float(SequenceMatcher(None, prev_text, ocr_text).ratio())
            jac_sim = jaccard_sets(prev_set, cur_set)
            sim = max(seq_sim, jac_sim)
            best_similarity = max(best_similarity, sim)
            new_tokens = len(cur_set - prev_set) if prev_set else len(cur_set)
            if sim >= ocr_similarity_threshold and new_tokens < ocr_min_new_chars:
                return 1.0 - float(sim)
        return None

    def get_ocr_frame_score(
        self,
        best_similarity: float,
        ocr_text: str,
        state: DedupState,
    ) -> float:
        """计算 OCR 帧分数。"""
        if not ocr_text or not state.kept_ocr_texts:
            return 0.0
        cur_set = shingles(ocr_text)
        best = 0.0
        for prev_text, prev_set in zip(
            state.kept_ocr_texts[-4:],
            state.kept_ocr_shingles[-4:],
            strict=False,
        ):
            if not prev_text:
                continue
            seq_sim = float(SequenceMatcher(None, prev_text, ocr_text).ratio())
            jac_sim = jaccard_sets(prev_set, cur_set)
            best = max(best, seq_sim, jac_sim)
        return 1.0 - float(best)

    # ------------------------------------------------------------------
    # OCR 帧处理
    # ------------------------------------------------------------------

    def process_ocr_for_frame(
        self,
        content: bytes,
        ocr_service: IOcrService,
        selection_service: FrameSelectionService,
        state: DedupState,
        params: ExtractParams,
        soft_deadline: float,
        progress_updater: ProgressUpdater,
    ) -> tuple[str, float | None, bool]:
        """处理单帧的 OCR 去重，返回 (ocr_text, frame_score, should_skip)。"""
        if not ocr_service:
            return "", None, False

        # 检查超时降级
        if not state.ocr_disabled and time.monotonic() > soft_deadline:
            state.ocr_disabled = True
            progress_updater.update_progress(
                progress=0,
                current=0,
                total=0,
                message="接近超时,已降级为图片去重",
            )
            return "", None, False

        # 执行 OCR
        crop_bytes, crop_range = selection_service.crop_for_ocr_bytes_with_range(
            content,
        )
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
        skip_score = self.check_ocr_similarity(
            ocr_text,
            state,
            params.ocr_similarity_threshold,
            params.ocr_min_new_chars,
        )
        if skip_score is not None:
            return ocr_text, skip_score, True

        frame_score = self.get_ocr_frame_score(0.0, ocr_text, state) if ocr_text and state.kept_ocr_texts else None
        return ocr_text, frame_score, False

    # ------------------------------------------------------------------
    # ffmpeg 阶段
    # ------------------------------------------------------------------

    def run_ffmpeg_phase(
        self,
        service: VideoFrameExtractService,
        recording_video_path: str,
        recording_id: str,
        info: FFProbeInfo,
        params: ExtractParams,
        cancel_token: CancellationToken,
        ffmpeg_reporter: ProgressReporter,
        progress_updater: ProgressUpdater,
        soft_deadline: float,
        tmpdir: str,
    ) -> tuple[int, Callable[[], bool]]:
        """运行 ffmpeg 抽帧阶段。"""
        total_estimate: int = (
            service.estimate_total_frames(info.duration_seconds, params.interval_seconds)
            if params.interval_based
            else 0
        )

        progress_updater.update_progress(
            progress=0,
            current=0,
            total=total_estimate,
            message="抽帧中",
        )

        last_progress = -1
        ffmpeg_timeout = max(30.0, float(soft_deadline) - time.monotonic() - 5.0)
        output_pattern = str(Path(tmpdir) / ("frame_%010d.jpg" if not params.interval_based else "frame_%06d.jpg"))

        def should_cancel() -> bool:
            return cancel_token.is_cancelled()

        for kv in service.iter_ffmpeg_progress(
            video_path=recording_video_path,
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
                logger.info(
                    "ffmpeg out_time_ms 解析失败",
                    extra={"raw_value": kv.get("out_time_ms")},
                )
                continue
            out_seconds = out_time_us / 1_000_000.0
            progress = int(out_seconds * 100 / info.duration_seconds) if info.duration_seconds else 0
            progress = min(max(progress, 0), 99)
            if progress != last_progress:
                ffmpeg_reporter.report_extra(
                    progress=progress,
                    current=0,
                    total=total_estimate,
                    message="抽帧中",
                )
                last_progress = progress

        return total_estimate, should_cancel

    # ------------------------------------------------------------------
    # 帧文件收集 / 时间计算
    # ------------------------------------------------------------------

    def collect_frame_files(self, tmpdir: str) -> list[str]:
        """收集并排序帧文件。"""
        frame_files = [
            str(Path(tmpdir) / f.name)
            for f in Path(tmpdir).iterdir()
            if f.name.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        frame_files.sort()
        return frame_files

    def calc_capture_time(
        self,
        path: str,
        index: int,
        params: ExtractParams,
        info: FFProbeInfo,
    ) -> float | None:
        """计算帧的捕获时间。"""
        if not params.interval_based and info.time_base_seconds:
            m = re.search(r"(\d+)", Path(path).name)
            return float(int(m.group(1)) * float(info.time_base_seconds)) if m else None
        return float(index - 1) * float(params.interval_seconds)

    # ------------------------------------------------------------------
    # 去重状态更新 / 帧重复判定
    # ------------------------------------------------------------------

    def update_dedup_state(
        self,
        state: DedupState,
        digest: str,
        dhash_hex: str,
        thumb: bytes,
        ocr_text: str,
        ocr_service: IOcrService | None,
        pixel_diff_threshold: float,
        selection_service: FrameSelectionService,
        content: bytes,
    ) -> None:
        """更新去重状态。"""
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
            state.kept_ocr_shingles.append(shingles(ocr_text))

    def is_frame_duplicate(
        self,
        content: bytes,
        digest: str,
        dhash_hex: str,
        state: DedupState,
        params: ExtractParams,
        selection_service: FrameSelectionService,
        window: int,
        pixel_diff_threshold: float,
    ) -> tuple[bool, bytes]:
        """检查帧是否重复，返回 (is_dup, thumb)。"""
        if digest in state.existing_sha256 or digest in state.seen_sha256:
            return True, b""
        if (
            params.dedup_threshold
            and state.kept_dhashes
            and self.is_dhash_duplicate(
                selection_service,
                dhash_hex,
                state.kept_dhashes,
                window,
                params.dedup_threshold,
            )
        ):
            return True, b""
        thumb = b""
        if pixel_diff_threshold and state.kept_thumbs:
            thumb = selection_service.calc_thumb_bytes(content)
            if thumb and self.is_pixel_duplicate(
                selection_service, thumb, state.kept_thumbs, window, pixel_diff_threshold
            ):
                return True, thumb
        return False, thumb

    # ------------------------------------------------------------------
    # 单帧处理
    # ------------------------------------------------------------------

    def process_single_frame(
        self,
        path: str,
        index: int,
        project_id: int,
        info: FFProbeInfo,
        params: ExtractParams,
        state: DedupState,
        selection_service: FrameSelectionService,
        ocr_service: IOcrService | None,
        soft_deadline: float,
        base_ordering: int,
        window: int,
        pixel_diff_threshold: float,
        screenshot_creator: ScreenshotCreator,
        progress_updater: ProgressUpdater,
    ) -> bool:
        """处理单帧，返回是否创建了截图。"""
        try:
            with open(path, "rb") as fp:
                content = fp.read()
        except Exception:
            logger.info(
                "帧文件读取失败",
                extra={"path": path},
                exc_info=True,
            )
            return False

        digest = sha256(content).hexdigest()
        dhash_hex: str = selection_service.calc_dhash_hex(content)

        is_dup, thumb = self.is_frame_duplicate(
            content,
            digest,
            dhash_hex,
            state,
            params,
            selection_service,
            window,
            pixel_diff_threshold,
        )
        if is_dup:
            return False

        # OCR 去重
        frame_score: float | None = None
        ocr_text = ""
        if ocr_service is not None:
            ocr_text, frame_score, should_skip = self.process_ocr_for_frame(
                content,
                ocr_service,
                selection_service,
                state,
                params,
                soft_deadline,
                progress_updater,
            )
            if should_skip:
                return False

        # 创建截图 — 通过回调
        capture_time_seconds = self.calc_capture_time(path, index, params, info)
        screenshot_creator.create_screenshot(
            project_id=project_id,
            ordering=base_ordering + state.created_count + 1,
            sha256=digest,
            dhash=dhash_hex,
            capture_time_seconds=capture_time_seconds,
            source="extract",
            frame_score=frame_score,
            image_name=Path(path).name,
            image_content=content,
        )

        self.update_dedup_state(
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

    # ------------------------------------------------------------------
    # 截图重排序
    # ------------------------------------------------------------------

    def reorder_screenshots(
        self,
        project_id: int,
        reorder_callback: ReorderCallback,
    ) -> None:
        """重新排序截图（委托给回调完成）。"""
        reorder_callback(project_id)
