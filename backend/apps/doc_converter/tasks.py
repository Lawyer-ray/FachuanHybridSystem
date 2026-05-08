"""DOC 转 DOCX 异步任务

Django Q2 入口，调用 engine.py 的转换函数。
"""

from __future__ import annotations

import logging
import time
import uuid
import zipfile
from pathlib import Path
from uuid import UUID

from django.utils import timezone

from apps.core.services.storage_service import normalize_to_media_rel
from apps.doc_converter.models import DocConverterItem, DocConverterJob, DocConverterJobStatus
from apps.doc_converter.services.engine import batch_convert
from apps.doc_converter.services.storage import DocConverterStorage

logger = logging.getLogger("apps.doc_converter")


def run_conversion_job(job_id: str) -> None:
    """Django Q2 入口"""
    job_uuid = UUID(job_id)
    storage = DocConverterStorage(job_uuid)

    try:
        job = DocConverterJob.objects.get(id=job_uuid)
        storage.ensure_dirs()

        DocConverterJob.objects.filter(id=job_uuid).update(status=DocConverterJobStatus.CONVERTING)

        items = list(job.items.all())
        if not items:
            DocConverterJob.objects.filter(id=job_uuid).update(
                status=DocConverterJobStatus.COMPLETED,
                progress=100,
                finished_at=timezone.now(),
            )
            return

        # 将 source_file 复制到 source_dir（soffice 需要本地文件路径）
        doc_paths: list[str] = []
        item_path_map: dict[str, DocConverterItem] = {}
        for item in items:
            src = Path(item.source_file.path)
            dest = storage.source_dir / item.original_name
            if not dest.exists():
                dest.write_bytes(src.read_bytes())
            doc_paths.append(str(dest))
            item_path_map[str(dest)] = item

        total = len(doc_paths)
        converted_count = 0
        failed_count = 0

        # 分批转换
        batch_size = 25
        for i in range(0, total, batch_size):
            # 检查取消
            job.refresh_from_db(fields=["cancel_requested"])
            if job.cancel_requested:
                DocConverterJob.objects.filter(id=job_uuid).update(
                    status=DocConverterJobStatus.CANCELLED,
                    finished_at=timezone.now(),
                )
                storage.cleanup()
                return

            batch = doc_paths[i : i + batch_size]
            batch_start = time.monotonic()

            result = batch_convert(batch, str(storage.output_dir), batch_size=batch_size)

            for doc_path in batch:
                item = item_path_map[doc_path]
                docx_path = result.get(doc_path)
                if docx_path:
                    # 用 UUID 重命名，避免中文长文件名超过 DB 字段 max_length=100
                    docx_p = Path(docx_path)
                    if not docx_p.exists():
                        # batch_convert 基于文件名推断路径，可能因字符编码差异找不到
                        # 回退：在 output_dir 中查找匹配 stem 的 .docx 文件
                        stem = Path(doc_path).stem
                        candidates = [
                            f
                            for f in storage.output_dir.iterdir()
                            if f.suffix.lower() == ".docx" and f.stem.startswith(stem[:10])
                        ]
                        if candidates:
                            docx_p = candidates[0]
                        else:
                            DocConverterItem.objects.filter(id=item.id).update(
                                status=DocConverterJobStatus.FAILED,
                                error="转换后文件未找到",
                            )
                            failed_count += 1
                            continue
                    new_name = f"{uuid.uuid4().hex}.docx"
                    new_path = docx_p.parent / new_name
                    docx_p.rename(new_path)
                    rel = normalize_to_media_rel(str(new_path))
                    DocConverterItem.objects.filter(id=item.id).update(
                        converted_file=rel,
                        status=DocConverterJobStatus.COMPLETED,
                        duration_ms=(time.monotonic() - batch_start) * 1000 / len(batch),
                    )
                    converted_count += 1
                else:
                    DocConverterItem.objects.filter(id=item.id).update(
                        status=DocConverterJobStatus.FAILED,
                        error="转换失败",
                    )
                    failed_count += 1

            progress = min(99, int((i + len(batch)) / total * 100))
            DocConverterJob.objects.filter(id=job_uuid).update(
                converted_files=converted_count,
                failed_files=failed_count,
                progress=progress,
            )

        # 打包 ZIP（使用原始文件名而非 UUID 文件名）
        DocConverterJob.objects.filter(id=job_uuid).update(status=DocConverterJobStatus.PACKING)
        name_map: dict[str, str] = {}
        for item in DocConverterItem.objects.filter(job_id=job_uuid, status=DocConverterJobStatus.COMPLETED).exclude(
            converted_file=""
        ):
            if not item.converted_file.name:
                continue
            uuid_filename = Path(item.converted_file.name).name
            original_stem = Path(item.original_name).stem
            name_map[uuid_filename] = f"{original_stem}.docx"
        _create_zip(storage, name_map)

        zip_relpath = normalize_to_media_rel(str(storage.export_zip_path))
        DocConverterJob.objects.filter(id=job_uuid).update(
            status=DocConverterJobStatus.COMPLETED,
            output_zip=zip_relpath,
            progress=100,
            converted_files=converted_count,
            failed_files=failed_count,
            finished_at=timezone.now(),
            error_message="",
        )
        logger.info("doc_converter_job_completed: %s (converted=%d, failed=%d)", job_id, converted_count, failed_count)

    except Exception as exc:
        logger.exception("doc_converter_job_failed: %s", job_id)
        DocConverterJob.objects.filter(id=job_uuid).update(
            status=DocConverterJobStatus.FAILED,
            error_message=str(exc)[:4000],
            finished_at=timezone.now(),
        )
        # 任务失败，清理上传的源文件和中间产物
        storage.cleanup()


def _create_zip(storage: DocConverterStorage, name_map: dict[str, str] | None = None) -> None:
    """将 output_dir 中的 docx 文件打包为 ZIP。

    name_map: UUID 文件名 -> 原始文件名 的映射，用于在 ZIP 中使用可读的原始文件名。
    """
    output_dir = storage.output_dir
    if not output_dir.exists():
        return

    storage.export_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(storage.export_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for docx_file in sorted(output_dir.iterdir()):
            if docx_file.is_file() and docx_file.suffix.lower() == ".docx":
                arcname = (name_map or {}).get(docx_file.name, docx_file.name)
                zf.write(docx_file, arcname)
