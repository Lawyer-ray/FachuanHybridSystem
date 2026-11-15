"""材料包删除时，回收它在 pdf_splitting 侧留下的派生数据。

## 为什么需要这个服务

删除材料包删的是**收件箱那条消息**（``InboxMessage``），但一次自动分段在
pdf_splitting 侧留下了三类互不相干、且**都不属于收件箱**的数据：

1. ``PdfSplitJob`` 行 + ``PdfSplitSegment`` 行（分段结果）；
2. 任务目录 ``media/pdf_splitting/jobs/<job_id>/``——里面有**一份完整源 PDF 副本**
   （实测 164 页 68MB）、逐页预览图、导出 zip；
3. OCR 页缓存 ``media/pdf_splitting/ocr_cache/<sha256>/``——按源文件内容哈希存，
   让同一份文件换名字重传也能复用旧 OCR。

这三样此前**没有任何清理路径**（全仓只有任务创建失败时回滚会删）。后果不只是
占盘（实测 45 个任务目录 87MB 无人回收），更是行为上的“删除不彻底”：

* 删掉材料包后，那条 ``PdfSplitJob`` 仍是 ``review_required`` 且同名同页数，
  于是 ``find_reusable_job`` 依然会命中它——下次上传同名文件点自动分段，
  直接拿回**已删除材料**的分段结果；
* OCR 缓存同样跨材料包存活，重传同一份文件连逐页 OCR 都省了。

## 复用判定为什么不能只看“同名同页数”

``find_reusable_job`` 的口径是「同名 + 同页数 + 已出结果」，刻意跨用户复用。
所以一个任务可能同时被多个材料包享用。删材料包 A 时若无脑删掉任务，会让材料包 B
下次被迫从零重跑（几分钟 + 几十元）。因此：

* **还有别的材料包同名同页数** → 保留任务（只可能在删除的那个包里被用过）；
* **没有别的材料包** → 任务已无人引用，连同磁盘目录一起删。

``shared_with`` 返回的“保留”原因会写进日志，便于事后追查为什么没删。
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.core.filesystem.upload_paths import MediaEntity
from apps.pdf_splitting.models import PdfSplitJob

logger = logging.getLogger(__name__)


def _ocr_cache_root(pdf_hash: str) -> Path:
    return Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "ocr_cache" / pdf_hash


def _job_root(job_id: Any) -> Path:
    return Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "jobs" / str(job_id)


def _sha256_of(path: Path) -> str | None:
    """源文件副本的 sha256（= OCR 缓存的桶名）。读不到就返回 None，调用方跳过缓存清理。"""
    if not path.exists():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        logger.warning("计算源文件哈希失败，跳过 OCR 缓存清理: %s", path, exc_info=True)
        return None
    return digest.hexdigest()


def _remaining_referencing_packs(
    *,
    source_name: str,
    total_pages: int,
    exclude_message_ids: set[int],
) -> int:
    """还有几个**活着的**材料包能命中这个任务（即还会复用）。

    判定口径与 ``find_reusable_job`` 严格对齐：同名 + 同页数。附件元信息是 JSONField，
    在 SQL 里用 ``__contains`` 匹配整个 dict 很容易因多出的键（size / part_index …）
    而漏判，所以拉出候选后在 Python 侧逐条精确比对。

    页数取自 ``attachments_meta[].page_count``；缺失时**按“可能复用”处理**（不删），
    因为宁可多留一个任务，也不能让别人重跑几分钟的识别。
    """
    from apps.message_hub.models import InboxMessage, SourceType

    candidates = (
        InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD)
        .exclude(pk__in=exclude_message_ids)
        .only("id", "attachments_meta")
    )
    remaining = 0
    for msg in candidates.iterator():
        metas = msg.attachments_meta
        if not isinstance(metas, list):
            continue
        for item in metas:
            if not isinstance(item, dict):
                continue
            name = str(item.get("original_filename") or item.get("filename") or "")
            if name != source_name:
                continue
            pages = item.get("page_count")
            # 页数未知 → 视为可能复用，保留
            if pages is None or int(pages) == int(total_pages):
                remaining += 1
                break
    return remaining


def purge_split_jobs_for_attachment(
    *,
    source_name: str,
    total_pages: int | None,
    deleting_message_id: int,
) -> dict[str, int]:
    """回收某个附件在 pdf_splitting 侧的派生数据。返回各类清理计数。

    只清理**没有别的材料包还在用**的任务。``total_pages`` 为 None 时只按文件名匹配
    （调用方拿不到页数，宁可多留也不误删别的尺寸的文件——页数不同本就是不同任务）。

    设计上**尽力而为**：任何一步失败只记日志，绝不把已完成的材料包删除带崩。
    残留的孤儿目录可以靠 ``purge_orphan_split_jobs`` 事后兜底。
    """
    if not source_name:
        return {"jobs": 0, "dirs": 0, "ocr_cache": 0}

    queryset = PdfSplitJob.objects.filter(source_original_name=source_name)
    if total_pages is not None and total_pages > 0:
        queryset = queryset.filter(total_pages=total_pages)

    stats = {"jobs": 0, "dirs": 0, "ocr_cache": 0}
    for job in queryset:
        others = _remaining_referencing_packs(
            source_name=source_name,
            total_pages=job.total_pages,
            exclude_message_ids={deleting_message_id},
        )
        if others > 0:
            # 还有别的材料包同名同页数：这任务仍是它的复用来源，动了就是让别人重跑
            logger.info(
                "保留拆分任务 %s（%s）：另有 %d 个材料包可能复用",
                job.id,
                source_name,
                others,
            )
            continue
        removed = _purge_one_job(job)
        for key in stats:
            stats[key] += removed[key]
    return stats


def _purge_one_job(job: PdfSplitJob) -> dict[str, int]:
    stats = {"jobs": 0, "dirs": 0, "ocr_cache": 0}
    # 删行会把实例的 pk 置为 None，目录定位与日志都得先存下来
    job_id = job.id
    job_name = job.source_original_name
    job_root = _job_root(job_id)
    # 先算哈希再删目录：OCR 缓存桶名来自源文件内容，源文件就在任务目录里
    pdf_hash = _sha256_of(job_root / "source" / "original.pdf")

    try:
        # 分段行靠 job 外键级联；显式删 job 行即可
        job.delete()
        stats["jobs"] = 1
    except Exception:
        logger.exception("删除拆分任务记录失败: %s", job_id)
        return stats

    if job_root.exists():
        try:
            shutil.rmtree(job_root)
            stats["dirs"] = 1
        except OSError:
            logger.warning("清理拆分任务目录失败（可留待孤儿回收）: %s", job_root, exc_info=True)

    if pdf_hash:
        cache_root = _ocr_cache_root(pdf_hash)
        if cache_root.exists():
            try:
                shutil.rmtree(cache_root)
                stats["ocr_cache"] = 1
            except OSError:
                logger.warning("清理 OCR 缓存失败: %s", cache_root, exc_info=True)

    logger.info(
        "回收材料派生数据：任务 %s（%s），目录 %d，OCR 缓存 %d",
        job_id,
        job_name,
        stats["dirs"],
        stats["ocr_cache"],
    )
    return stats


def purge_orphan_split_jobs(*, dry_run: bool = False) -> dict[str, int]:
    """兜底：删掉**没有任何材料包同名**拆分任务与其目录（历史遗留的孤儿）。

    用于两种情况：① 本功能上线前已被删掉材料包、但任务还在的历史残留；
    ② ``purge_split_jobs_for_attachment`` 中途失败留下的孤儿。

    判据保守到几乎不会误伤：任务的 ``source_original_name`` 在**任何** manual_upload
    材料包的附件里都找不到，才认定为孤儿。任务若还被某份材料包引用，一律保留。
    """
    from apps.message_hub.models import InboxMessage, SourceType

    live_names: set[str] = set()
    for meta in InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD).values_list(
        "attachments_meta", flat=True
    ):
        if not isinstance(meta, list):
            continue
        for item in meta:
            if isinstance(item, dict):
                name = str(item.get("original_filename") or item.get("filename") or "")
                if name:
                    live_names.add(name)

    stats = {"jobs": 0, "dirs": 0, "ocr_cache": 0, "scanned": 0}
    for job in PdfSplitJob.objects.all().only("id", "source_original_name").iterator():
        stats["scanned"] += 1
        if job.source_original_name in live_names:
            continue
        if dry_run:
            stats["jobs"] += 1
            continue
        removed = _purge_one_job(job)
        for key in ("jobs", "dirs", "ocr_cache"):
            stats[key] += removed[key]

    # 反向孤儿：磁盘上有任务目录，但 DB 里已经没有对应行了。
    # 只做 DB→磁盘 会漏掉这类——实测开发库里有 11 个这样的目录占着 71MB，
    # 全是历史上删过记录但没清目录留下的。
    stats["dirs"] += _purge_disk_only_orphans(dry_run=dry_run)
    stats["ocr_cache"] += purge_orphan_ocr_cache(dry_run=dry_run)
    return stats


def purge_orphan_ocr_cache(*, dry_run: bool = False) -> int:
    """删掉没有现存材料包附件对应的 OCR 缓存桶。返回个数。

    OCR 缓存以「源文件 sha256」为桶名。删材料包时若源文件副本还在，
    ``_purge_one_job`` 能反查出桶名直接删；但源文件已丢（历史上删过、或任务目录
    先被清）时就反查不到，桶会永久残留。这里用全库现存附件的 sha256 集合做差。

    ⚠️ 要读每个现存附件的全文算 hash。附件总量不大（manual_upload 量级），
    但仍是重操作，管理命令场景合适；不要放到请求路径里。
    """
    from apps.message_hub.models import InboxMessage, SourceType
    from apps.message_hub.services.base import resolve_media_attachment_path

    cache_root = Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "ocr_cache"
    if not cache_root.is_dir():
        return 0

    live_hashes: set[str] = set()
    for msg in (
        InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD)
        .only("id", "attachments_meta")
        .iterator()
    ):
        metas = msg.attachments_meta
        if not isinstance(metas, list):
            continue
        for item in metas:
            if not isinstance(item, dict):
                continue
            path = resolve_media_attachment_path(str(item.get("local_path", "") or ""))
            if path is None or not path.exists():
                continue
            digest = _sha256_of(path)
            if digest:
                live_hashes.add(digest)

    removed = 0
    for bucket in cache_root.iterdir():
        if not bucket.is_dir() or bucket.name in live_hashes:
            continue
        if dry_run:
            logger.info("试运行：将删除孤儿 OCR 缓存 %s", bucket)
            removed += 1
            continue
        try:
            shutil.rmtree(bucket)
            removed += 1
            logger.info("已删除孤儿 OCR 缓存: %s", bucket)
        except OSError:
            logger.warning("删除孤儿 OCR 缓存失败: %s", bucket, exc_info=True)
    return removed


def _purge_disk_only_orphans(*, dry_run: bool = False) -> int:
    """删掉「有目录无任务行」的孤儿目录。返回删除（或试运行将删）的个数。

    与 DB→磁盘 方向互不依赖：这里有目录就一定没有活任务行指着它（目录名就是 job id）。
    """
    jobs_root = Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "jobs"
    if not jobs_root.is_dir():
        return 0

    live_ids = {str(job_id) for job_id in PdfSplitJob.objects.values_list("id", flat=True)}
    removed = 0
    for entry in jobs_root.iterdir():
        if not entry.is_dir() or entry.name in live_ids:
            continue
        if dry_run:
            logger.info("试运行：将删除孤儿任务目录 %s", entry)
            removed += 1
            continue
        try:
            shutil.rmtree(entry)
            removed += 1
            logger.info("已删除孤儿任务目录: %s", entry)
        except OSError:
            logger.warning("删除孤儿任务目录失败: %s", entry, exc_info=True)
    return removed
