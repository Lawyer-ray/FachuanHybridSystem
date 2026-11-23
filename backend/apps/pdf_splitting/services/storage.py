from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.filesystem.upload_paths import MediaEntity


class PdfSplitStorage:
    def __init__(self, job_id: UUID | str) -> None:
        self._job_id = str(job_id)

    @property
    def job_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "jobs" / self._job_id

    @property
    def source_dir(self) -> Path:
        return self.job_root / "source"

    @property
    def analysis_dir(self) -> Path:
        return self.job_root / "analysis"

    @property
    def previews_dir(self) -> Path:
        return self.job_root / "previews"

    @property
    def exports_dir(self) -> Path:
        return self.job_root / "exports"

    @property
    def source_pdf_path(self) -> Path:
        return self.source_dir / "original.pdf"

    @property
    def pages_json_path(self) -> Path:
        return self.analysis_dir / "pages.json"

    @property
    def extract_summary_json_path(self) -> Path:
        """取字阶段的观测摘要（实际生效平台 ocr_provider / 容灾链 / 缓存命中 / 版面策略落地情况）。

        单独落盘的理由：``extract_stage`` 只返回 (pages, summary)，summary 不进 DB，
        而分段阶段是另一个 Django-Q 任务。不落盘时 ``ocr_provider`` 就永久丢失，
        分段阶段只能拿 ``job.cloud_backend``（通常是 "auto"）当坐标系依据——
        ``resolve_bbox_unit("auto")`` 是 unknown，positioned 直接恒空。
        """
        return self.analysis_dir / "extract_summary.json"

    @property
    def segments_json_path(self) -> Path:
        return self.analysis_dir / "segments.json"

    @property
    def segments_md_path(self) -> Path:
        """分段 Markdown 产物（order / 页区间 / 正文 / 段级质量标记），供 API content_md 透出与下游 AI 消费。"""
        return self.analysis_dir / "segments_md.json"

    @property
    def page_quality_json_path(self) -> Path:
        """页面质量画像产物（summary 区块 + 逐页画像）。

        单独落盘的理由：这份产物在**取字阶段**算出来，而段级 ``quality_flags``
        要等到**分段阶段**才贴得上；两个阶段是两个 Django-Q 任务，只靠 job 目录
        里的文件传递。只写 DB summary 的话分段阶段读不到它。
        """
        return self.analysis_dir / "page_quality.json"

    @property
    def engine_disagreements_json_path(self) -> Path:
        """双引擎分歧产物（分歧列表 + 严重度计数 + 各引擎运行状态）。

        单独落盘的理由与 ``page_quality.json`` 一样：这份产物在**取字阶段**算出来
        （双引擎就是取字的一部分），而 summary 要到**分段阶段**才最终写进 DB。
        两个阶段是两个 Django-Q 任务，只能靠 job 目录里的文件传递。
        """
        return self.analysis_dir / "engine_disagreements.json"

    @property
    def rotated_backfill_json_path(self) -> Path:
        """转正页回填报告（哪几页被 VL 换过正文 / 每页跳过原因 / 字数变化）。

        单独落盘的理由：回填发生在 cross_check 阶段，而 summary 要到 segment 阶段才写进
        DB；两个阶段只能靠 job 目录里的文件传递。它同时是「这页的正文到底被谁换过」的
        唯一凭据——出问题时不能只靠翻日志。
        """
        return self.analysis_dir / "rotated_backfill.json"

    @property
    def table_geometry_json_path(self) -> Path:
        """表格格子几何产物（逐页逐块量到的真实格子）。

        单独落盘的理由与 ``engine_disagreements.json`` 一样，但多一条：
        ``build_segments_markdown`` 有**三个**调用点（两阶段分段 / 单任务分析 /
        用户确认后重建 segments_md），任何一处拿不到几何就会退回整表框——
        “确认分段后点格子又画错”正是 ``bbox_backend`` 踩过的同类坑。
        所以这份产物必须是三处共享的**文件**，而不是某个调用点手里的内存变量。
        """
        return self.analysis_dir / "table_geometry.json"

    @property
    def export_zip_path(self) -> Path:
        return self.exports_dir / "split_result.zip"

    def rel_path_of(self, path: Path) -> str:
        """把 job 目录内的绝对路径转换为 media 相对路径（供 default_storage 使用）。"""
        return path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()

    def save_overwrite(self, path: Path, content: File[Any]) -> None:
        # 参数取 `File[Any]` 而不是只收 `ContentFile[bytes]`：`ContentFile` 是 `File`
        # 的子类，而大文件入口（S17-04，2026-11-23 二轮审计）传进来的是磁盘上的
        # 只读文件对象，靠 `chunks()` 分块落盘而不把整份字节读进内存。
        rel_path = self.rel_path_of(path)
        if default_storage.exists(rel_path):
            default_storage.delete(rel_path)
        default_storage.save(rel_path, content)

    def ensure_dirs(self) -> None:  # pragma: no cover
        for path in (self.source_dir, self.analysis_dir, self.previews_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:  # pragma: no cover
        shutil.rmtree(self.job_root, ignore_errors=True)

    def write_json(self, path: Path, payload: object) -> None:  # pragma: no cover
        self.save_overwrite(
            path,
            ContentFile(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")),
        )

    def read_json(self, path: Path, default: object) -> object:  # pragma: no cover
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def preview_path(self, page_no: int) -> Path:
        return self.previews_dir / f"page_{page_no:03d}.png"

    def export_pdf_path(self, filename: str) -> Path:
        return self.exports_dir / filename
