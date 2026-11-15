"""``cleanup_service`` 的失败与降级分支单测。

存在理由：这个服务是**唯一**回收 pdf_splitting 派生数据（任务行 / 任务目录 /
OCR 缓存）的路径，而它的调用点全都挂在别的操作后面——删材料包、孤儿回收管理命令。
所以它有一条硬约束：**任何一步失败都只能记日志，绝不能把调用方带崩**。删材料包
已经提交了 DB 删除，若这里抛异常，用户会看到「删除失败」但数据其实已经删了；
孤儿回收则会被一个删不掉的目录卡死，后面所有孤儿永远清不完。

正因如此，"能容错"这件事必须被测出来：正常路径的用例（见
``test_cleanup_service.py``）证明数据会被清掉，本文件证明**清不掉时不会炸**，
并且返回值如实反映"哪一步没做成"，方便事后追查。

⚠️ 全部用例把 MEDIA_ROOT 指到 ``tmp_path``。本文件测的是"删目录"，
不隔离就是动开发环境真实 media 目录（本仓库曾因此误删 47 个任务目录，含两份在用卷宗）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.filesystem.upload_paths import MediaEntity
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import (
    create_manual_message,
    delete_manual_message,
    get_or_create_manual_source,
)
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType
from apps.pdf_splitting.services import cleanup_service
from apps.pdf_splitting.services.cleanup_service import (
    purge_orphan_ocr_cache,
    purge_orphan_split_jobs,
    purge_split_jobs_for_attachment,
)

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4 cleanup-failure-fixture"


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """MEDIA_ROOT → 临时目录。

    与 ``test_cleanup_service.py`` 同款隔离：``purge_orphan_split_jobs`` 会扫全盘并
    删"看起来没人用"的目录，跑在真实 media 上就是把在用的卷宗当孤儿删掉。
    """
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _media(*parts: str) -> Path:
    return Path(settings.MEDIA_ROOT).joinpath(*parts)


def _job_root(job_id: Any) -> Path:
    return _media(MediaEntity.PDF_SPLITTING, "jobs", str(job_id))


def _make_job(
    *,
    name: str = "卷宗.pdf",
    pages: int = 3,
    status: str = PdfSplitJobStatus.REVIEW_REQUIRED,
) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name=name,
        status=status,
        total_pages=pages,
    )


def _seed_job_disk(job: PdfSplitJob) -> tuple[Path, Path]:
    """造出任务目录（含源文件副本）与对应 OCR 缓存桶。"""
    root = _job_root(job.id)
    source = root / "source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "original.pdf").write_bytes(PDF_BYTES)

    bucket = _ocr_cache_bucket(hashlib.sha256(PDF_BYTES).hexdigest())
    bucket.mkdir(parents=True, exist_ok=True)
    (bucket / "page_0001.json").write_text("{}", encoding="utf-8")
    return root, bucket


def _ocr_cache_bucket(pdf_hash: str) -> Path:
    return _media(MediaEntity.PDF_SPLITTING, "ocr_cache", pdf_hash)


def _make_pack(*, name: str = "卷宗.pdf", pages: int | None = 3) -> InboxMessage:
    msg = create_manual_message([SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")])
    if pages is not None:
        metas = list(msg.attachments_meta or [])
        metas[0]["page_count"] = pages
        msg.attachments_meta = metas
        msg.save(update_fields=["attachments_meta"])
    return msg


def _cleanup_pack(msg: InboxMessage) -> None:
    """删附件文件 + 消息行。元信息可能是本文件故意造脏的，逐条防御。"""
    metas = msg.attachments_meta
    for att in metas if isinstance(metas, list) else []:
        if not isinstance(att, dict):
            continue
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    InboxMessage.objects.filter(pk=msg.pk).delete()


def _make_bare_message(*, message_id: str, metas: Any) -> InboxMessage:
    """直接建一条 manual_upload 消息，``attachments_meta`` 想写什么就写什么。

    用于测"元信息形状不对"的降级（非 list / 条目非 dict）——正常上传路径写不出
    这种脏数据，但历史数据与手工导入会。
    """
    return InboxMessage.objects.create(
        source=get_or_create_manual_source(),
        message_id=message_id,
        subject="脏元信息材料包",
        received_at=timezone.now(),
        attachments_meta=metas,
    )


# ── _sha256_of ────────────────────────────────────────────────────


class TestSha256Of:
    """源文件哈希 = OCR 缓存桶名，读不出来要返回 None 而不是抛。"""

    def test_正常文件返回哈希(self, tmp_path: Path) -> None:
        target = tmp_path / "original.pdf"
        target.write_bytes(PDF_BYTES)
        assert cleanup_service._sha256_of(target) == hashlib.sha256(PDF_BYTES).hexdigest()

    def test_文件不存在返回None(self, tmp_path: Path) -> None:
        assert cleanup_service._sha256_of(tmp_path / "ghost.pdf") is None

    def test_读文件报错返回None而不是抛(self, tmp_path: Path) -> None:
        """源文件权限坏掉 / 被占用时，不能让整个清理链炸掉。

        ``exists()`` 会通过，失败点在 ``open()`` 上——那一步是 OSError。
        所以这里 patch ``open`` 抛 OSError（比 chmod 000 可靠：以 root 跑测试时
        chmod 拦不住读，用例会假绿）。
        """
        target = tmp_path / "original.pdf"
        target.write_bytes(PDF_BYTES)

        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            assert cleanup_service._sha256_of(target) is None


# ── purge_split_jobs_for_attachment：失败分支 ─────────────────────


class TestPurgeSplitJobsForAttachmentFailures:
    def test_删任务行抛异常时返回计数而不崩(self) -> None:
        """``job.delete()`` 失败只记日志：材料包已经删了，这里再抛会让用户以为没删掉。

        返回 stats 全 0 而不是 .5 之类的部分计数——调用方据此判断"什么都没清成"，
        剩下的孤儿交给 ``purge_orphan_split_jobs`` 兜底。
        """
        job = _make_job()
        _seed_job_disk(job)
        pack = _make_pack()

        def boom(self: PdfSplitJob, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("db is gone")

        with patch.object(PdfSplitJob, "delete", boom):
            stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=pack.pk)

        assert stats == {"jobs": 0, "dirs": 0, "ocr_cache": 0}
        # 行还在（删除失败），目录与缓存也一个都没动 —— 全部留待孤儿回收
        assert PdfSplitJob.objects.filter(pk=job.pk).exists()
        assert _job_root(job.id).exists()
        _cleanup_pack(pack)

    def test_删任务目录OSError只警告并继续删缓存(self) -> None:
        """目录删不掉（NFS 占用 / 权限）不能让 OCR 缓存也留下来继续被复用。"""
        job = _make_job()
        _seed_job_disk(job)
        pack = _make_pack()

        with patch.object(cleanup_service.shutil, "rmtree", side_effect=OSError("device busy")):
            stats = purge_split_jobs_for_attachment(source_name="卷宗.pdf", total_pages=3, deleting_message_id=pack.pk)

        assert stats["jobs"] == 1, "任务行已经删掉了"
        assert stats["dirs"] == 0, "目录没删成，计数必须如实反映"
        assert stats["ocr_cache"] == 0
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists()
        _cleanup_pack(pack)

    def test_名称为空时什么都不做(self) -> None:
        """空文件名是"调用方没传到"的信号；按空名去匹配会把不相关的任务全删光。"""
        job = _make_job(name="")
        assert purge_split_jobs_for_attachment(source_name="", total_pages=3, deleting_message_id=1) == {
            "jobs": 0,
            "dirs": 0,
            "ocr_cache": 0,
        }
        assert PdfSplitJob.objects.filter(pk=job.pk).exists()

    def test_页数为None时只按文件名匹配(self) -> None:
        """调用方拿不到页数时不能因为"筛不到"就一条都不删（那样等于清理失效）。"""
        job = _make_job(name="无页数卷宗.pdf", pages=7)
        pack = _make_pack(name="别的.pdf", pages=3)

        stats = purge_split_jobs_for_attachment(
            source_name="无页数卷宗.pdf", total_pages=None, deleting_message_id=pack.pk
        )

        assert stats["jobs"] == 1
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists()
        _cleanup_pack(pack)


# ── _remaining_referencing_packs ──────────────────────────────────


class TestRemainingReferencingPacks:
    """「还有别的材料包能命中这个任务」的判定——决定删还是留。

    判错方向只有两种，代价都很实在：多留 = 白占盘（可接受）；少留 = 别人的材料包
    下次被迫从零重跑几分钟 + 几十元。所以口径必须是"拿不准就留"。
    """

    def test_页数未知视为可能复用(self) -> None:
        """别的包附件缺 ``page_count`` 时，宁可保留任务也不赌它不是同一份。"""
        _make_pack(name="共用.pdf", pages=None)

        remaining = cleanup_service._remaining_referencing_packs(
            source_name="共用.pdf", total_pages=3, exclude_message_ids=set()
        )

        assert remaining == 1

    def test_同名同页数计数且每包只算一次(self) -> None:
        """一个包里有两份同名同页附件，也只算"一个复用来源"（break 掉）。"""
        _make_pack(name="共用.pdf", pages=3)
        msg = _make_bare_message(
            message_id="manual-dup-in-one-pack",
            metas=[
                {"original_filename": "共用.pdf", "page_count": 3},
                {"original_filename": "共用.pdf", "page_count": 3},
            ],
        )

        remaining = cleanup_service._remaining_referencing_packs(
            source_name="共用.pdf", total_pages=3, exclude_message_ids=set()
        )

        assert remaining == 2, "两个包各算一次；同一包内重复附件不得重复计数"
        _cleanup_pack(msg)

    def test_页数不同不算复用(self) -> None:
        _make_pack(name="共用.pdf", pages=9)

        assert (
            cleanup_service._remaining_referencing_packs(
                source_name="共用.pdf", total_pages=3, exclude_message_ids=set()
            )
            == 0
        )

    def test_exclude_message_ids生效(self) -> None:
        """正在被删除的那个包不能算作"还有人用"，否则任务永远删不掉。"""
        deleting = _make_pack(name="共用.pdf", pages=3)

        remaining = cleanup_service._remaining_referencing_packs(
            source_name="共用.pdf", total_pages=3, exclude_message_ids={deleting.pk}
        )

        assert remaining == 0
        _cleanup_pack(deleting)

    def test_附件元信息非list时跳过(self) -> None:
        """历史脏数据（JSONField 被写成 dict / 字符串）不能让判定崩掉。"""
        msg = _make_bare_message(message_id="manual-bad-meta", metas={"original_filename": "共用.pdf"})

        assert (
            cleanup_service._remaining_referencing_packs(
                source_name="共用.pdf", total_pages=3, exclude_message_ids=set()
            )
            == 0
        )
        _cleanup_pack(msg)

    def test_附件条目非dict时跳过(self) -> None:
        msg = _make_bare_message(message_id="manual-bad-item", metas=["not-a-dict", 42])

        assert (
            cleanup_service._remaining_referencing_packs(
                source_name="共用.pdf", total_pages=3, exclude_message_ids=set()
            )
            == 0
        )
        _cleanup_pack(msg)


# ── purge_orphan_ocr_cache ────────────────────────────────────────


class TestPurgeOrphanOcrCache:
    def test_dry_run只计数不删(self) -> None:
        """试运行必须真的"什么都没删"——这是运维敢在生产上先跑一次的前提。"""
        orphan = _ocr_cache_bucket("f" * 64)
        orphan.mkdir(parents=True, exist_ok=True)
        (orphan / "page_0001.json").write_text("{}", encoding="utf-8")

        removed = purge_orphan_ocr_cache(dry_run=True)

        assert removed == 1
        assert orphan.exists()

    def test_rmtree报错吞掉并跳过(self) -> None:
        """单个桶删不掉不能中断整轮回收，也不能把计数虚报成删掉了。"""
        orphan = _ocr_cache_bucket("e" * 64)
        orphan.mkdir(parents=True, exist_ok=True)

        with patch.object(cleanup_service.shutil, "rmtree", side_effect=OSError("device busy")):
            removed = purge_orphan_ocr_cache()

        assert removed == 0
        assert orphan.exists()

    def test_缓存根目录不存在返回0(self) -> None:
        """全新环境还没跑过拆分：缓存根目录根本不存在，不能因此抛异常。"""
        assert not _media(MediaEntity.PDF_SPLITTING, "ocr_cache").exists()
        assert purge_orphan_ocr_cache() == 0

    def test_普通文件不算缓存桶(self) -> None:
        """桶名必须是目录；散落的同名文件不该被当桶删（也不该计数）。"""
        cache_root = _media(MediaEntity.PDF_SPLITTING, "ocr_cache")
        cache_root.mkdir(parents=True, exist_ok=True)
        stray = cache_root / ("d" * 64)
        stray.write_text("not a bucket", encoding="utf-8")

        assert purge_orphan_ocr_cache() == 0
        assert stray.exists()

    def test_活附件的缓存桶保留(self) -> None:
        """现存材料包附件对应的缓存是"重跑的钱"，绝不能当孤儿清掉。"""
        pack = _make_pack(name="有缓存.pdf", pages=3)
        live_hash = hashlib.sha256(PDF_BYTES).hexdigest()
        live = _ocr_cache_bucket(live_hash)
        live.mkdir(parents=True, exist_ok=True)

        assert purge_orphan_ocr_cache() == 0
        assert live.exists()
        _cleanup_pack(pack)


# ── _purge_disk_only_orphans ──────────────────────────────────────


class TestPurgeDiskOnlyOrphans:
    def test_jobs根目录不存在返回0(self) -> None:
        """全新环境没有 jobs 目录，回收命令不该因此报错。"""
        assert not _media(MediaEntity.PDF_SPLITTING, "jobs").exists()
        assert cleanup_service._purge_disk_only_orphans() == 0

    def test_有任务行的目录保留(self) -> None:
        """目录名就是 job id：DB 里还有行 → 目录一定不是孤儿，绝不能删。"""
        job = _make_job()
        root, _bucket = _seed_job_disk(job)

        assert cleanup_service._purge_disk_only_orphans() == 0
        assert root.exists()

    def test_dry_run只计数不删(self) -> None:
        orphan = _job_root(uuid4())
        orphan.mkdir(parents=True, exist_ok=True)

        assert cleanup_service._purge_disk_only_orphans(dry_run=True) == 1
        assert orphan.exists()

    def test_rmtree报错吞掉(self) -> None:
        orphan = _job_root(uuid4())
        orphan.mkdir(parents=True, exist_ok=True)

        with patch.object(cleanup_service.shutil, "rmtree", side_effect=OSError("device busy")):
            assert cleanup_service._purge_disk_only_orphans() == 0
        assert orphan.exists()

    def test_普通文件不算任务目录(self) -> None:
        jobs_root = _media(MediaEntity.PDF_SPLITTING, "jobs")
        jobs_root.mkdir(parents=True, exist_ok=True)
        stray = jobs_root / "notes.txt"
        stray.write_text("x", encoding="utf-8")

        assert cleanup_service._purge_disk_only_orphans() == 0
        assert stray.exists()


# ── purge_orphan_split_jobs 兜底链 ────────────────────────────────


class TestPurgeOrphanSplitJobsResilience:
    def test_单个任务删除失败不阻断后续任务(self) -> None:
        """一个任务删不掉不能把它后面的孤儿全挡住——回收命令必须能继续跑。"""
        first = _make_job(name="删不掉的卷宗.pdf")
        _seed_job_disk(first)
        second = _make_job(name="能删掉的卷宗.pdf")

        real_delete = PdfSplitJob.delete
        calls = {"n": 0}

        def flaky_delete(self: PdfSplitJob, *args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if self.pk == first.pk:
                raise RuntimeError("locked row")
            return real_delete(self, *args, **kwargs)

        with patch.object(PdfSplitJob, "delete", flaky_delete):
            stats = purge_orphan_split_jobs()

        assert calls["n"] >= 2, "第一个失败后仍必须尝试第二个"
        assert stats["scanned"] >= 2
        assert PdfSplitJob.objects.filter(pk=first.pk).exists(), "删不掉的仍留着，等下次兜底"
        assert not PdfSplitJob.objects.filter(pk=second.pk).exists()

    def test_材料包元信息非list时不影响活名集合构建(self) -> None:
        """构建 live_names 时遇到脏元信息要跳过，不能让整轮回收在第一步就崩。"""
        msg = _make_bare_message(message_id="manual-dirty", metas="broken")
        job = _make_job(name="看起来像孤儿的卷宗.pdf")

        purge_orphan_split_jobs()

        assert not PdfSplitJob.objects.filter(pk=job.pk).exists()
        _cleanup_pack(msg)

    def test_dry_run不动磁盘(self) -> None:
        """试运行不删行也不删目录——运维靠它先看"会删多少"。"""
        job = _make_job(name="试运行孤儿.pdf")
        root, _bucket = _seed_job_disk(job)
        disk_only = _job_root(uuid4())
        disk_only.mkdir(parents=True, exist_ok=True)

        stats = purge_orphan_split_jobs(dry_run=True)

        assert stats["jobs"] >= 1
        assert stats["dirs"] >= 1
        assert PdfSplitJob.objects.filter(pk=job.pk).exists()
        assert root.exists() and disk_only.exists()


# ── 端到端：删材料包时清理失败不影响删除本身 ─────────────────────


class TestDeletePackSurvivesCleanupFailure:
    def test_清理抛异常时材料包仍然删掉(self) -> None:
        """派生数据清理是尽力而为：删包已经成功，清不掉不该反过来报错。"""
        pack = _make_pack(name="清理失败.pdf", pages=3)
        pk = pack.pk

        def boom(**_kwargs: Any) -> dict[str, int]:
            raise RuntimeError("cleanup down")

        with patch.object(cleanup_service, "purge_split_jobs_for_attachment", boom):
            delete_manual_message(pack)  # 不应抛出

        assert not InboxMessage.objects.filter(pk=pk).exists()

    def test_页数是非数字时不阻断清理(self) -> None:
        """``attachments_meta[].page_count`` 可能是 '三页' 这种脏值。

        调用方（``_purge_derived_split_data``）把转不成 int 的页数降级成 None，
        于是按文件名清理，而不是整个跳过。
        """
        pack = _make_pack(name="脏页数.pdf", pages=3)
        metas = list(pack.attachments_meta or [])
        metas[0]["page_count"] = "三页"
        pack.attachments_meta = metas
        pack.save(update_fields=["attachments_meta"])
        job = _make_job(name="脏页数.pdf", pages=3)
        pk = pack.pk

        delete_manual_message(pack)

        assert not InboxMessage.objects.filter(pk=pk).exists()
        assert not PdfSplitJob.objects.filter(pk=job.pk).exists(), "脏页数必须降级成按名清理，不能整条跳过"
