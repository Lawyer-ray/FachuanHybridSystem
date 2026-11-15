"""材料包删除时回收 pdf_splitting 派生数据的单测。

背景（也是这些用例的存在理由）：拆分任务、任务目录、OCR 缓存此前**没有任何清理
路径**。删掉材料包后它们仍然活着，而 ``find_reusable_job`` 只按「文件名 + 页数 +
已出结果」匹配，于是下次上传同名文件会直接复用**已删除材料**的分段结果。

全部测试数据都是虚构的。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.filesystem.upload_paths import MediaEntity
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.manual_upload_service import (
    create_manual_message,
    delete_manual_message,
    get_or_create_manual_source,
)
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType
from apps.pdf_splitting.services.cleanup_service import (
    purge_orphan_ocr_cache,
    purge_orphan_split_jobs,
    purge_split_jobs_for_attachment,
)

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4 cleanup-test-payload"


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path, settings):
    """把 MEDIA_ROOT 重定向到临时目录。

    ⚠️ 本模块测的是**删目录**，不隔离就是灾难：它们会直接操作开发环境真实的
    ``media/pdf_splitting/jobs``。而且 ``purge_orphan_split_jobs`` 会扫全盘，
    会把真实材料包的任务目录当成“孤儿”删掉（实测误删了两份在用的任务目录）。
    所以这里强制隔离，任何用例都不能碰真实 MEDIA_ROOT。
    """
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _make_job(
    *, name: str = "卷宗.pdf", pages: int = 3, status: str = PdfSplitJobStatus.REVIEW_REQUIRED
) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name=name,
        status=status,
        total_pages=pages,
    )


def _job_root(job_id) -> Path:
    return Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "jobs" / str(job_id)


def _seed_job_disk(job: PdfSplitJob) -> tuple[Path, Path]:
    """造出任务目录（含源文件副本）与对应的 OCR 缓存桶，返回两者路径。"""
    root = _job_root(job.id)
    (root / "source").mkdir(parents=True, exist_ok=True)
    source = root / "source" / "original.pdf"
    source.write_bytes(PDF_BYTES)

    pdf_hash = hashlib.sha256(PDF_BYTES).hexdigest()
    cache = Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "ocr_cache" / pdf_hash
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "page_0001.json").write_text("{}", encoding="utf-8")
    return root, cache


def _make_pack(*, name: str = "卷宗.pdf", pages: int = 3) -> InboxMessage:
    msg = create_manual_message([SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")])
    metas = list(msg.attachments_meta or [])
    metas[0]["page_count"] = pages
    msg.attachments_meta = metas
    msg.save(update_fields=["attachments_meta"])
    return msg


def _cleanup_pack(msg: InboxMessage) -> None:
    from apps.message_hub.services.base import resolve_media_attachment_path

    for att in msg.attachments_meta or []:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    InboxMessage.objects.filter(pk=msg.pk).delete()


class TestPurgeSplitJobsForAttachment:
    def test_removes_job_row_dir_and_ocr_cache(self) -> None:
        """没有别的材料包引用 → 任务行、任务目录（含源文件）、OCR 缓存全部回收。"""
        job = _make_job()
        root, cache = _seed_job_disk(job)
        pack = _make_pack()

        stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=pack.pk)

        assert stats == {"jobs": 1, "dirs": 1, "ocr_cache": 1}
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists()
        assert not root.exists(), "任务目录（含 68MB 级源文件副本）必须一并删除"
        assert not cache.exists(), "OCR 缓存必须一并删除，否则重传同文件仍复用旧识别"
        _cleanup_pack(pack)

    def test_keeps_job_when_another_pack_uses_it(self) -> None:
        """还有别的材料包同名同页数 → 保留任务，否则那个包下次被迫从零重跑。"""
        job = _make_job()
        root, cache = _seed_job_disk(job)
        deleting = _make_pack()
        other = _make_pack()

        stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=deleting.pk)

        assert stats == {"jobs": 0, "dirs": 0, "ocr_cache": 0}
        assert PdfSplitJob.objects.filter(pk=job.pk).exists()
        assert root.exists() and cache.exists()
        _cleanup_pack(deleting)
        _cleanup_pack(other)

    def test_different_page_count_is_not_treated_as_shared(self) -> None:
        """同名但页数不同 → 是另一份文件，不构成复用，照删。"""
        job = _make_job(pages=3)
        root, _cache = _seed_job_disk(job)
        deleting = _make_pack(pages=3)
        other = _make_pack(pages=9)  # 同名不同页

        stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=deleting.pk)

        assert stats["jobs"] == 1
        assert not root.exists()
        _cleanup_pack(deleting)
        _cleanup_pack(other)

    def test_unknown_page_count_keeps_job(self) -> None:
        """别的包附件缺 page_count → 宁可保留，也不赌它不是同一份。"""
        job = _make_job(pages=3)
        _seed_job_disk(job)
        deleting = _make_pack()
        other = _make_pack()
        metas = list(other.attachments_meta or [])
        metas[0].pop("page_count", None)
        other.attachments_meta = metas
        other.save(update_fields=["attachments_meta"])

        stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=deleting.pk)

        assert stats["jobs"] == 0
        _cleanup_pack(deleting)
        _cleanup_pack(other)

    def test_missing_disk_dir_still_removes_row(self) -> None:
        """只有 DB 行、磁盘早没了（历史残留）→ 行照样能清掉，不因目录缺失失败。"""
        job = _make_job()
        pack = _make_pack()

        stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=pack.pk)

        assert stats["jobs"] == 1
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists()
        _cleanup_pack(pack)


class TestDeletePackPurgesDerivedData:
    def test_deleting_pack_removes_split_job(self) -> None:
        """端到端：删材料包 = 收件箱行 + 附件 + 拆分任务 / 目录 / OCR 缓存都清干净。

        这就是「删除不彻底」的回归点：此前删完包，任务仍是 review_required 同名
        同页数，``find_reusable_job`` 照样命中它。
        """
        pack = _make_pack(name="曾用名.pdf", pages=3)
        job = _make_job(name="曾用名.pdf", pages=3)
        root, cache = _seed_job_disk(job)
        pk = pack.pk

        delete_manual_message(pack)

        assert not InboxMessage.objects.filter(pk=pk).exists()
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists(), "删除材料包必须连带清掉可复用的拆分任务"
        assert not root.exists() and not cache.exists()

    def test_deleting_pack_keeps_other_packs_job(self) -> None:
        """删包不能伤到别的包还在用的任务。"""
        deleting = _make_pack(name="共用.pdf", pages=3)
        other = _make_pack(name="共用.pdf", pages=3)
        job = _make_job(name="共用.pdf", pages=3)

        delete_manual_message(deleting)

        assert PdfSplitJob.objects.filter(pk=job.pk).exists(), "别的材料包还在复用，任务必须留下"
        _cleanup_pack(other)

    def test_delete_succeeds_even_if_purge_raises(self, monkeypatch) -> None:
        """派生数据清理失败不得让删除本身报错（包已经删掉了）。"""
        pack = _make_pack(name="容错.pdf", pages=3)
        pk = pack.pk

        from apps.pdf_splitting.services import cleanup_service

        def boom(**_kwargs):
            raise RuntimeError("purge down")

        monkeypatch.setattr(cleanup_service, "purge_split_jobs_for_attachment", boom)
        delete_manual_message(pack)  # 不应抛出

        assert not InboxMessage.objects.filter(pk=pk).exists()


class TestPurgeOrphanSplitJobs:
    def test_purges_jobs_with_no_live_pack(self) -> None:
        """历史残留：材料包早已不存在，任务还在 → 孤儿回收清掉它。"""
        job = _make_job(name="早已删除的卷宗.pdf")
        root, cache = _seed_job_disk(job)

        stats = purge_orphan_split_jobs()

        assert stats["jobs"] >= 1
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists()
        assert not root.exists() and not cache.exists()

    def test_keeps_jobs_referenced_by_live_pack(self) -> None:
        """有活着的材料包引用 → 不是孤儿，绝不能动。"""
        pack = _make_pack(name="在用的卷宗.pdf", pages=3)
        job = _make_job(name="在用的卷宗.pdf", pages=3)

        purge_orphan_split_jobs()

        assert PdfSplitJob.objects.filter(pk=job.pk).exists()
        _cleanup_pack(pack)

    def test_dry_run_deletes_nothing(self) -> None:
        job = _make_job(name="试运行卷宗.pdf")

        stats = purge_orphan_split_jobs(dry_run=True)

        assert stats["jobs"] >= 1
        assert PdfSplitJob.objects.filter(pk=job.pk).exists()

    def test_purges_disk_dir_without_job_row(self) -> None:
        """反向孤儿：有目录无任务行。

        只查 DB→磁盘会漏掉这类（开发库里实测 11 个目录、71MB 全是这种）。
        """
        orphan_id = uuid4()
        root = _job_root(orphan_id)
        (root / "source").mkdir(parents=True, exist_ok=True)
        (root / "source" / "original.pdf").write_bytes(PDF_BYTES)

        purge_orphan_split_jobs()

        assert not root.exists(), "没有任务行的任务目录必须一并回收"

    def test_purges_orphan_ocr_cache_bucket(self) -> None:
        """OCR 缓存桶无现存附件对应 → 删除。

        源文件副本一旦丢了就反查不到桶名（删材料包时清不掉），需这个宝藏办。
        """
        orphan_hash = hashlib.sha256(b"no-such-attachment").hexdigest()
        bucket = Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "ocr_cache" / orphan_hash
        bucket.mkdir(parents=True, exist_ok=True)
        (bucket / "page_0001.json").write_text("{}", encoding="utf-8")

        purge_orphan_ocr_cache()

        assert not bucket.exists()

    def test_keeps_ocr_cache_of_live_attachment(self) -> None:
        """现存材料包的附件对应的 OCR 缓存桶绝不能删：那是重跑的钱。"""
        pack = _make_pack(name="有缓存的卷宗.pdf", pages=3)
        live_hash = hashlib.sha256(PDF_BYTES).hexdigest()
        bucket = Path(settings.MEDIA_ROOT) / MediaEntity.PDF_SPLITTING / "ocr_cache" / live_hash
        bucket.mkdir(parents=True, exist_ok=True)

        purge_orphan_ocr_cache()

        assert bucket.exists(), "活附件的 OCR 缓存不得被当作孤儿清掉"
        _cleanup_pack(pack)

    def test_keeps_disk_dir_of_live_job(self) -> None:
        """有任务行且被活材料包引用 → 目录绝不能动。"""
        pack = _make_pack(name="活卷宗.pdf", pages=3)
        job = _make_job(name="活卷宗.pdf", pages=3)
        root, _cache = _seed_job_disk(job)

        purge_orphan_split_jobs()

        assert root.exists(), "仍有材料包引用的任务目录不得删除"
        _cleanup_pack(pack)
