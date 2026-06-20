from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ImageRotationJob, ImageRotationPage

logger = logging.getLogger("apps.image_rotation")


@receiver(post_delete, sender=ImageRotationPage)
def _cleanup_page_files(sender: type, instance: ImageRotationPage, **kwargs: object) -> None:  # pragma: no cover
    if instance.source_image:
        try:
            transaction.on_commit(lambda f=instance.source_image: f.delete(save=False))
        except Exception:
            logger.exception("清理 page source_image 失败: %s", instance.id)


@receiver(post_delete, sender=ImageRotationJob)
def _cleanup_job_files(sender: type, instance: ImageRotationJob, **kwargs: object) -> None:  # pragma: no cover
    job_id = instance.id
    media_root = Path(str(settings.MEDIA_ROOT))
    export_urls = (instance.export_zip_url, instance.export_pdf_url)

    def _do_cleanup() -> None:
        # 清理 flat 导出文件
        for url in export_urls:
            if url:
                rel = url.removeprefix("/media/")
                flat_path = media_root / rel
                try:
                    flat_path.unlink(missing_ok=True)
                except Exception:
                    logger.exception("清理导出文件失败: %s", flat_path)

        # 兜底：删除整个 job 目录（含 source/）
        job_dir = media_root / "image_rotation" / "jobs" / str(job_id)
        import shutil

        shutil.rmtree(job_dir, ignore_errors=True)

    transaction.on_commit(_do_cleanup)
