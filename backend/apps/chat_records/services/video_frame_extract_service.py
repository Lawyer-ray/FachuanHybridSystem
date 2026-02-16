"""Business logic services."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import select
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.core.exceptions import ValidationException
from apps.core.subprocess_runner import SubprocessRunner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FFProbeInfo:
    duration_seconds: float
    time_base_seconds: float | None = None


class VideoFrameExtractService:
    def _is_path_under_dir(self, path: str, root: str) -> bool:
        try:
            path_real = os.path.realpath(path)
            root_real = os.path.realpath(root)
            return os.path.commonpath([path_real, root_real]) == root_real
        except Exception:
            logger.exception("操作失败")
            # 静默处理:文件操作失败不影响主流程

            # 静默处理:文件操作失败不影响主流程

            return False

    def _default_allowed_output_roots(self) -> list[str]:
        roots: list[str] = []
        try:
            media_root = getattr(settings, "MEDIA_ROOT", None)
            if media_root:
                roots.append(str(media_root))
        except Exception:
            logger.exception("操作失败")

            pass
        roots.append(tempfile.gettempdir())
        return roots

    def _ensure_output_pattern_safe(self, output_pattern: str) -> None:
        if not output_pattern:
            raise ValidationException("输出路径不能为空")
        output_dir = os.path.dirname(str(output_pattern)) or ""
        if not output_dir:
            raise ValidationException("输出目录不能为空")
        if not os.path.isabs(output_dir):
            raise ValidationException("输出目录必须为绝对路径")
        allowed_roots = self._default_allowed_output_roots()
        if not any(self._is_path_under_dir(output_dir, root) for root in allowed_roots if root):
            raise ValidationException("输出目录不安全")

    def ensure_ffmpeg(self) -> None:
        self._ensure_ffmpeg()

    def _find_tool(self, name: str) -> str | None:
        p = shutil.which(name)
        if p:
            return p
        candidates = []
        for root in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"):
            candidates.append(os.path.join(root, name))
        for p in candidates:
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p
        return None

    def probe(self, video_path: str) -> FFProbeInfo:
        self._ensure_ffmpeg()
        if not video_path or not os.path.exists(video_path):
            raise ValidationException("视频文件不存在")

        duration = 0.0
        time_base_seconds: float | None = None
        ffprobe = self._find_tool("ffprobe")
        if ffprobe:
            cmd = [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "format=duration:stream=time_base",
                "-of",
                "json",
                video_path,
            ]
            try:
                out = SubprocessRunner(allowed_programs={ffprobe}).run(
                    args=cmd, timeout_seconds=10, check=True, text=True
                )
                data = json.loads(out.stdout or "{}")
                duration = float((data.get("format") or {}).get("duration") or 0.0)
                streams = data.get("streams") or []
                if streams:
                    tb = str((streams[0] or {}).get("time_base") or "")
                    if "/" in tb:
                        n, d = tb.split("/", 1)
                        time_base_seconds = float(n) / float(d) if float(d) else None
            except Exception:
                logger.exception("操作失败")

                duration = 0.0
        else:
            duration = self._probe_duration_by_ffmpeg(video_path)

        if duration <= 0:
            raise ValidationException("无法解析视频时长")

        return FFProbeInfo(duration_seconds=duration, time_base_seconds=time_base_seconds)

    def _build_ffmpeg_filter_args(
        self, strategy: str, interval_seconds: float, scene_threshold: float
    ) -> tuple[list[str], str, list[str]]:
        """根据策略构建 ffmpeg 滤镜参数,返回 (input_args, vf, extra_args)"""
        scale = "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'"
        vfr_args = ["-vsync", "vfr", "-frame_pts", "1"]

        strategy_map: dict[str, tuple[list[str], str, list[str]]] = {
            "scene": ([], f"select='gt(scene,{float(scene_threshold)})',{scale},mpdecimate", vfr_args),
            "keyframe": (["-skip_frame", "nokey"], f"{scale},mpdecimate", vfr_args),
            "smart": ([], f"{scale},mpdecimate", vfr_args),
        }

        if strategy in strategy_map:
            return strategy_map[strategy]

        fps = 1.0 / interval_seconds
        return [], f"fps={fps},{scale},mpdecimate", []

    def _force_kill_proc(self, proc: Any) -> None:
        """强制终止进程"""
        with contextlib.suppress(Exception):
            proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            logger.exception("操作失败")

            with contextlib.suppress(Exception):
                proc.kill()

    def _read_ffmpeg_progress_lines(
        self,
        proc: Any,
        *,
        should_cancel: Callable[[], bool] | None,
        timeout_seconds: float | None,
        started: float,
    ) -> Iterator[dict[str, str]]:
        """从 ffmpeg 进程读取进度行"""
        assert proc.stdout is not None

        while True:
            if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
                self._force_kill_proc(proc)
                raise ValidationException("ffmpeg 抽帧超时")

            if should_cancel and should_cancel():
                self._force_kill_proc(proc)
                raise ValidationException("抽帧已取消")

            if proc.poll() is not None:
                break

            rlist, _, _ = select.select([proc.stdout], [], [], 0.2)
            if not rlist:
                continue
            line = proc.stdout.readline()
            if not line:
                break
            line = (line or "").strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            yield {k: v}

    def _check_ffmpeg_exit(self, proc: Any) -> None:
        """检查 ffmpeg 退出码,非零则抛出异常"""
        try:
            rc = proc.wait(timeout=5)
        except Exception:
            logger.exception("操作失败")

            with contextlib.suppress(Exception):
                proc.kill()
            rc = proc.wait()
        if rc != 0:
            err = ""
            try:
                if proc.stderr is not None:
                    err = proc.stderr.read() or ""
            except Exception:
                logger.exception("操作失败")

                err = ""
            err = (err or "").strip()
            if err:
                tail = "\n".join(err.splitlines()[-12:])
                raise ValidationException(f"ffmpeg 抽帧失败:{tail}")
            raise ValidationException("ffmpeg 抽帧失败,请检查视频文件或 ffmpeg 安装")

    def iter_ffmpeg_progress(
        self,
        *,
        video_path: str,
        output_pattern: str,
        interval_seconds: float,
        strategy: str = "interval",
        scene_threshold: float = 0.25,
        should_cancel: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> Iterator[dict[str, str]]:
        self._ensure_ffmpeg()
        strategy = str(strategy or "interval").strip().lower()
        if interval_seconds <= 0 and strategy == "interval":
            raise ValidationException("截帧间隔必须大于 0")
        self._ensure_output_pattern_safe(output_pattern)
        timeout_seconds = float(timeout_seconds) if timeout_seconds is not None else None
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValidationException("超时时间必须大于 0")

        input_args, vf, extra_args = self._build_ffmpeg_filter_args(strategy, interval_seconds, scene_threshold)

        ffmpeg = self._find_tool("ffmpeg")
        if not ffmpeg:
            raise ValidationException("未检测到 ffmpeg,请先安装")

        cmd = [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            *input_args,
            "-i",
            video_path,
            "-vf",
            vf,
            *extra_args,
            "-q:v",
            "6",
            output_pattern,
        ]
        proc = SubprocessRunner(allowed_programs={ffmpeg}).popen(
            args=cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        started = time.monotonic()

        yield from self._read_ffmpeg_progress_lines(
            proc,
            should_cancel=should_cancel,
            timeout_seconds=timeout_seconds,
            started=started,
        )

        self._check_ffmpeg_exit(proc)

    def estimate_total_frames(self, duration_seconds: float, interval_seconds: float) -> int:
        if duration_seconds <= 0:
            return 0
        if interval_seconds <= 0:
            return 0
        return math.ceil(duration_seconds / interval_seconds)

    def _ensure_tools(self) -> None:
        self._ensure_ffmpeg()

    def _ensure_ffmpeg(self) -> None:
        if not self._find_tool("ffmpeg"):
            raise ValidationException("未检测到 ffmpeg,请先安装")

    def _probe_duration_by_ffmpeg(self, video_path: str) -> float:
        cmd = ["ffmpeg", "-hide_banner", "-i", video_path]
        try:
            out = SubprocessRunner().run(args=cmd, timeout_seconds=10, check=False, text=True)
        except Exception:
            logger.exception("操作失败")

            return 0.0
        text = (out.stderr or "") + "\n" + (out.stdout or "")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", text)
        if not m:
            return 0.0
        h = int(m.group(1))
        mm = int(m.group(2))
        s = float(m.group(3))
        return h * 3600 + mm * 60 + s
