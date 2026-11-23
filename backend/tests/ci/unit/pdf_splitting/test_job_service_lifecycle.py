"""PdfSplitJobService 的生命周期与安全校验单测。

存在理由（为什么这些用例必须真实跑，而不是用 MagicMock 数调用次数）：

这个服务此前把 7 个方法的 ``# pragma: no cover`` 写在 **def 行尾**。coverage 的
``exclude_lines`` 只排除那一行 def，函数体照算未覆盖——于是度量上看不出它们没测，
实际却是全模块最关键的几段逻辑：

* ``create_job`` —— 唯一的任务入口，上传/本地路径二选一、任务提交失败必须回滚；
* ``_validate_local_pdf_path`` —— 安全审计 B-11 的**路径越界防护**（任意登录用户
  若能让它放行 MEDIA_ROOT 外的路径，就能拆解并回读服务器上任意 PDF）；
* ``_validate_pdf_file`` —— 空文件 / 超大 / 损坏 / 0 页 / 超页数 的准入闸门；
* ``find_reusable_job`` —— 决定「复用已算好的结果」还是「从零重跑 164 页」；
* ``mark_completed`` / ``mark_failed`` / ``request_cancel`` —— 状态机收口。

因此这里不用 mock 断言调用参数，而是断言**真实的 DB 状态与磁盘副作用**。

⚠️ 所有涉及磁盘的用例都把 MEDIA_ROOT 指到 ``tmp_path``：``create_job`` 会真的落盘
一份源文件副本，``_save_uploaded_pdf`` 走 ``default_storage``。不隔离就等于往开发
环境的真实 media 目录里写陌生文件（本仓库曾发生过测试误删真实 media 的事故）。

测试数据（文件名、正文）全部虚构。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pymupdf as fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.exceptions import NotFoundError, ValidationException
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode, PdfSplitSourceType
from apps.pdf_splitting.services import job_service as job_service_module
from apps.pdf_splitting.services.job_service import (
    PdfSplitJobService,
    load_segments_md,
    load_segments_positioned,
    load_segments_quality_flags,
)
from apps.testing.factories import LawyerFactory

pytestmark = pytest.mark.django_db

#: create_job 里需要提交 Django-Q 任务的入口。测试一律 patch 掉，
#: 否则会真的往队列里塞任务（测试环境没有 worker，任务永远躺在 OrmQ 里）。
_SUBMIT_PATH = "apps.pdf_splitting.services.job_service.build_task_submission_service"
#: 内容分析模式的首次取字提交在 two_stage 里（带阶段预算），是**另一个**入口。
_STAGE_SUBMIT_PATH = "apps.pdf_splitting.services.split.two_stage.build_task_submission_service"


@contextmanager
def _patched_submits() -> Iterator[MagicMock]:
    """两个提交入口共用一个替身。

    只 patch job_service 那一个会漏掉内容分析路径：它走
    ``two_stage.submit_extract_stage``，用的是 two_stage 模块里的工厂——
    漏掉就等于在测试里真的入队一个取字任务。
    """
    factory = MagicMock()
    factory.return_value.submit.return_value = "task-stub"
    with patch(_SUBMIT_PATH, factory), patch(_STAGE_SUBMIT_PATH, factory):
        yield factory


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """把 MEDIA_ROOT 重定向到临时目录。

    ``create_job`` / ``_save_uploaded_pdf`` 会真的写盘（源文件副本 + 任务目录），
    ``PdfSplitStorage`` 的路径全部由 ``settings.MEDIA_ROOT`` 推导。不隔离就是往
    开发环境真实 media 目录里写东西，删的时候也不想碰真数据。
    """
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _make_pdf(path: Path, *, pages: int = 3) -> Path:
    """生成一份真实的、可被 pymupdf 打开的最小 PDF。"""
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {index + 1}")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


def _upload(path: Path, *, name: str = "示例卷宗.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, path.read_bytes(), content_type="application/pdf")


def _service() -> PdfSplitJobService:
    return PdfSplitJobService()


def _make_job(
    *,
    name: str = "复用卷宗.pdf",
    pages: int = 3,
    status: str = PdfSplitJobStatus.REVIEW_REQUIRED,
    created_by: Any = None,
) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid.uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name=name,
        status=status,
        total_pages=pages,
        created_by=created_by,
    )


# ── _validate_local_pdf_path：安全审计 B-11 路径越界防护 ─────────────


class TestValidateLocalPdfPath:
    """``_validate_local_pdf_path`` 的准入与越界防护。

    这是 B-11 的落地点：``source_path`` 是直读服务器文件系统的入口，只要放行
    MEDIA_ROOT / 浏览根之外的路径，登录用户就能拆解并回读任意 PDF。所以每条
    拒绝分支都是安全边界，不是「顺手加的健壮性」。
    """

    def test_拒绝空路径(self) -> None:
        with pytest.raises(ValidationException):
            _service()._validate_local_pdf_path("   ")

    def test_拒绝smb共享路径(self) -> None:
        """smb:// 会触发系统级凭据挂载，不是本机可读路径，直接拒。"""
        with pytest.raises(ValidationException):
            _service()._validate_local_pdf_path("smb://nas/share/a.pdf")

    def test_拒绝相对路径(self) -> None:
        """相对路径的解析基准是进程 cwd，等于把工作目录内容暴露成可拆解目标。"""
        with pytest.raises(ValidationException):
            _service()._validate_local_pdf_path("docs/a.pdf")

    def test_resolve报错时拒绝而不是崩(self, tmp_path: Path) -> None:
        """``Path.resolve()`` 在符号链接环等场景抛 OSError；必须转成业务异常。"""
        with patch.object(Path, "resolve", side_effect=OSError("symlink loop")):
            with pytest.raises(ValidationException) as exc_info:
                _service()._validate_local_pdf_path(str(tmp_path / "a.pdf"))
        assert "路径无法访问" in exc_info.value.message

    def test_拒绝不存在的路径(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationException) as exc_info:
            _service()._validate_local_pdf_path(str(tmp_path / "not-here.pdf"))
        assert "路径不存在" in exc_info.value.message

    def test_拒绝目录(self, tmp_path: Path) -> None:
        """目录能通过 exists()，但 ``read_bytes()`` 会失败——必须在准入时就拦。"""
        directory = tmp_path / "material"
        directory.mkdir()
        with pytest.raises(ValidationException) as exc_info:
            _service()._validate_local_pdf_path(str(directory))
        assert "路径不是文件" in exc_info.value.message

    def test_拒绝非pdf扩展名(self, tmp_path: Path) -> None:
        other = tmp_path / "word.docx"
        other.write_bytes(b"%PDF-1.4 but named docx")
        with pytest.raises(ValidationException) as exc_info:
            _service()._validate_local_pdf_path(str(other))
        assert "仅支持 PDF 文件" in exc_info.value.message

    def test_拒绝不可读文件(self, tmp_path: Path) -> None:
        """不可读必须在这里报业务异常，否则会在后面 ``read_bytes()`` 抛未捕获 OSError。"""
        pdf = _make_pdf(tmp_path / "locked.pdf")
        with patch.object(job_service_module.os, "access", return_value=False):
            with pytest.raises(ValidationException) as exc_info:
                _service()._validate_local_pdf_path(str(pdf))
        assert "文件不可读" in exc_info.value.message

    def test_拒绝MEDIA_ROOT之外的路径(self, tmp_path: Path) -> None:
        """B-11 的核心断言：MEDIA_ROOT / 浏览根之外的 PDF 一律拒绝。

        这是「任意登录用户可拆解并回读服务器上任意 PDF」的最后一米：
        前面的扩展名、可读检查都会通过，只有这道边界拦得住。
        """
        outside = _make_pdf(tmp_path / "outside" / "机密卷宗.pdf")
        media_root = tmp_path / "media"
        media_root.mkdir()

        with override_settings(MEDIA_ROOT=media_root, FOLDER_BROWSE_ROOTS=[]):
            with pytest.raises(ValidationException) as exc_info:
                _service()._validate_local_pdf_path(str(outside))
        assert "路径越界" in exc_info.value.message

    def test_浏览根之内的路径放行(self, tmp_path: Path) -> None:
        """配置了 FOLDER_BROWSE_ROOTS 时，根内文件必须能过——否则功能本身不可用。"""
        browse_root = tmp_path / "browse"
        pdf = _make_pdf(browse_root / "卷宗" / "起诉状.pdf")
        media_root = tmp_path / "media"
        media_root.mkdir()

        with override_settings(MEDIA_ROOT=media_root, FOLDER_BROWSE_ROOTS=[str(browse_root)]):
            resolved = _service()._validate_local_pdf_path(str(pdf))

        assert resolved == pdf.resolve()

    def test_MEDIA_ROOT之内的路径放行(self, tmp_path: Path) -> None:
        """材料包附件就落在 MEDIA_ROOT 下，这条路必须通。"""
        pdf = _make_pdf(tmp_path / "message_hub" / "manual" / "7" / "卷宗.pdf")
        with override_settings(MEDIA_ROOT=tmp_path, FOLDER_BROWSE_ROOTS=[]):
            assert _service()._validate_local_pdf_path(str(pdf)) == pdf.resolve()


# ── _validate_pdf_file ────────────────────────────────────────────


class TestValidatePdfFile:
    """``_validate_pdf_file`` 的五道准入闸门。

    它决定「什么样的文件才配进任务队列」：空文件、超 1GB、损坏、0 页、超 1000 页
    都会在任务创建时就失败，而不是等 OCR 跑到一半才发现——后者既浪费云端费用，
    又留下一个永远失败的任务。
    """

    def test_返回真实页数(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "sample.pdf", pages=4)
        assert _service()._validate_pdf_file(pdf) == 4

    def test_空文件被拒(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        with pytest.raises(ValidationException) as exc_info:
            _service()._validate_pdf_file(empty)
        assert "PDF 文件为空" in exc_info.value.message

    def test_文件不存在按空文件处理(self, tmp_path: Path) -> None:
        """不存在时 ``stat()`` 会抛 OSError，代码特意先判断 exists() 兜住。"""
        with pytest.raises(ValidationException) as exc_info:
            _service()._validate_pdf_file(tmp_path / "ghost.pdf")
        assert "PDF 文件为空" in exc_info.value.message

    def test_超过大小上限被拒(self, tmp_path: Path) -> None:
        """上限走 ``MAX_FILE_SIZE`` 常量：放宽到 1GB 是业务决定，测试锁住它生效。"""
        pdf = _make_pdf(tmp_path / "big.pdf", pages=1)
        with patch.object(PdfSplitJobService, "MAX_FILE_SIZE", 16):
            with pytest.raises(ValidationException) as exc_info:
                _service()._validate_pdf_file(pdf)
        assert "文件大小超过限制" in exc_info.value.message

    @pytest.mark.parametrize(
        ("name", "payload"),
        [
            ("garbage", b"%PDF-1.4 this is not really a pdf"),
            ("plain-text", b"hello world, not a pdf at all"),
            ("empty-structure", b"%PDF-1.7\n%%EOF\n"),
        ],
    )
    def test_损坏的pdf转成业务异常而不是500(self, tmp_path: Path, name: str, payload: bytes) -> None:
        """损坏的 PDF 必须变成 ValidationException（→400「PDF 文件损坏」）。

        ⚠️ 这条用例是真 bug 的回归点：pymupdf 2.x 对这三种形态统统抛
        ``FileDataError``，而它继承 **RuntimeError**、不是 ValueError。此前只捕
        ``(TypeError, ValueError)``，一个都接不住 → 异常穿透到全局兜底 handler，
        用户看到的是 500「系统错误,请稍后重试」+ 一段底层 traceback。
        断言「抛的是 ValidationException」本身就排除了 FileDataError 漏出的可能。
        """
        broken = tmp_path / f"broken-{name}.pdf"
        broken.write_bytes(payload)

        with pytest.raises(ValidationException) as exc_info:
            _service()._validate_pdf_file(broken)

        assert "PDF 无法打开" in exc_info.value.message
        assert exc_info.value.errors == {"file": "PDF 文件损坏或格式不正确"}

    def test_零页被拒(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "blank.pdf", pages=1)
        empty_doc = MagicMock()
        empty_doc.page_count = 0
        empty_doc.__enter__ = MagicMock(return_value=empty_doc)
        empty_doc.__exit__ = MagicMock(return_value=False)
        with patch.object(job_service_module.fitz, "open", return_value=empty_doc):
            with pytest.raises(ValidationException) as exc_info:
                _service()._validate_pdf_file(pdf)
        assert "PDF 没有页面" in exc_info.value.message

    def test_超过页数上限被拒(self, tmp_path: Path) -> None:
        """上限 1000 页是业务口径（整卷 500 页也常见）；用它防止误传超大文件。"""
        pdf = _make_pdf(tmp_path / "many.pdf", pages=1)
        big_doc = MagicMock()
        big_doc.page_count = 1001
        big_doc.__enter__ = MagicMock(return_value=big_doc)
        big_doc.__exit__ = MagicMock(return_value=False)
        with patch.object(job_service_module.fitz, "open", return_value=big_doc):
            with pytest.raises(ValidationException) as exc_info:
                _service()._validate_pdf_file(pdf)
        assert "PDF 页数超过限制" in exc_info.value.message


# ── _save_uploaded_pdf ────────────────────────────────────────────


class TestSaveUploadedPdf:
    """``_save_uploaded_pdf`` 落盘前的三道校验 + 真实落盘。"""

    def test_真实落盘并返回净化后的文件名(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "src.pdf", pages=1)
        target = tmp_path / "jobs" / "j1" / "source" / "original.pdf"
        returned = _service()._save_uploaded_pdf(_upload(pdf, name="卷宗 副本.pdf"), target)

        assert target.exists(), "上传内容必须真实写到任务目录，后续校验/OCR 都读它"
        assert target.read_bytes() == pdf.read_bytes()
        # 文件名会过 sanitize_upload_filename（空白转下划线），DB 里的
        # source_original_name 与 materials 侧同名，find_reusable_job 才匹配得上
        assert returned == "卷宗_副本.pdf"

    def test_非pdf扩展名被拒(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "src.pdf", pages=1)
        target = tmp_path / "jobs" / "j1" / "source" / "original.pdf"
        with pytest.raises(ValidationException) as exc_info:
            _service()._save_uploaded_pdf(_upload(pdf, name="伪装.pdf.exe"), target)
        assert "仅支持 PDF 文件" in exc_info.value.message
        assert not target.exists(), "校验失败不得先落盘"

    def test_空文件被拒(self, tmp_path: Path) -> None:
        target = tmp_path / "jobs" / "j1" / "source" / "original.pdf"
        empty = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        with pytest.raises(ValidationException) as exc_info:
            _service()._save_uploaded_pdf(empty, target)
        assert "上传文件为空" in exc_info.value.message

    def test_超过大小上限被拒(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "src.pdf", pages=1)
        target = tmp_path / "jobs" / "j1" / "source" / "original.pdf"
        with patch.object(PdfSplitJobService, "MAX_FILE_SIZE", 16):
            with pytest.raises(ValidationException) as exc_info:
                _service()._save_uploaded_pdf(_upload(pdf), target)
        assert "文件大小超过限制" in exc_info.value.message


# ── create_job ────────────────────────────────────────────────────


class TestCreateJob:
    """``create_job``：任务入口的正常路径与两条回滚路径。

    关键设计取舍（见源码注释）：任务提交失败时**必须删掉刚建的任务行和任务目录**，
    否则会留下一个没有 task_id、永远不会被 worker 捡起的僵尸任务，前端要么一直
    pending，要么被 ``find_inflight_job`` 接管后永远轮询不到结果。
    """

    def test_file与source_path二选一_都不给被拒(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            with _patched_submits() as submit:
                _service().create_job(file=None, source_path=None, template_key="filing_materials_v1")
        assert "二选一" in exc_info.value.message
        submit.assert_not_called()

    def test_file与source_path二选一_都给也被拒(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "src.pdf", pages=1)
        with override_settings(MEDIA_ROOT=tmp_path):
            with pytest.raises(ValidationException) as exc_info:
                with _patched_submits():
                    _service().create_job(
                        file=_upload(pdf),
                        source_path=str(pdf),
                        template_key="filing_materials_v1",
                    )
        assert "二选一" in exc_info.value.message

    def test_上传文件走两阶段任务链(self, tmp_path: Path) -> None:
        """内容分析模式必须提交 **extract** 阶段（不是老的整任务），
        这是 600s worker 超时被拆链的落地点。"""
        pdf = _make_pdf(tmp_path / "卷宗.pdf", pages=3)
        with _patched_submits() as submit_factory:
            submit_factory.return_value.submit.return_value = "task-extract-1"
            job = _service().create_job(
                file=_upload(pdf),
                source_path=None,
                template_key="filing_materials_v1",
            )

        from apps.pdf_splitting.services.split.two_stage import EXTRACT_STAGE_TIMEOUT_SECONDS, TASK_EXTRACT

        submit_factory.return_value.submit.assert_called_once()
        args = submit_factory.return_value.submit.call_args
        assert args.args[0] == TASK_EXTRACT
        assert args.kwargs["args"] == [str(job.id)]
        assert args.kwargs["task_name"] == f"pdf_split_extract_{job.id}"
        # 首次提交也必须带阶段预算：裸 submit 会退回集群默认 600s，
        # 拆链只给第二段全新预算，第一段仍在旧限额里被硬杀。
        assert args.kwargs["timeout"] == EXTRACT_STAGE_TIMEOUT_SECONDS

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.PENDING
        assert job.total_pages == 3
        assert job.source_type == PdfSplitSourceType.UPLOAD
        assert job.source_original_name == "示例卷宗.pdf"
        assert job.task_id == "task-extract-1"
        assert job.started_at is not None
        assert job.summary_payload["template_label"]
        # 源文件副本真实落在任务目录下（后续阶段都读它）
        from apps.pdf_splitting.services.storage import PdfSplitStorage

        assert PdfSplitStorage(job.id).source_pdf_path.exists()

    def test_按页拆分走单一导出前的整任务(self, tmp_path: Path) -> None:
        """非内容分析模式不拆链，直接提交整任务——否则按页拆分要多排一个空阶段。"""
        pdf = _make_pdf(tmp_path / "卷宗.pdf", pages=2)
        with _patched_submits() as submit_factory:
            submit_factory.return_value.submit.return_value = "task-whole"
            job = _service().create_job(
                file=_upload(pdf),
                source_path=None,
                template_key="filing_materials_v1",
                split_mode=PdfSplitMode.PAGE_SPLIT,
            )

        assert submit_factory.return_value.submit.call_args.args[0] == "apps.pdf_splitting.tasks.execute_pdf_split_job"
        job.refresh_from_db()
        assert job.split_mode == PdfSplitMode.PAGE_SPLIT
        assert job.task_id == "task-whole"

    def test_本地路径来源记录真实绝对路径(self, tmp_path: Path) -> None:
        media_root = tmp_path / "media"
        pdf = _make_pdf(media_root / "inbox" / "起诉状.pdf", pages=2)
        with override_settings(MEDIA_ROOT=media_root, FOLDER_BROWSE_ROOTS=[]):
            with _patched_submits() as submit_factory:
                submit_factory.return_value.submit.return_value = "task-local"
                job = _service().create_job(
                    file=None,
                    source_path=str(pdf),
                    template_key="filing_materials_v1",
                )

        job.refresh_from_db()
        assert job.source_type == PdfSplitSourceType.LOCAL_PATH
        assert job.source_abs_path == pdf.resolve().as_posix()
        assert job.source_original_name == "起诉状.pdf"
        assert job.source_relpath.startswith("pdf_splitting/jobs/")

    def test_未认证用户不记created_by(self, tmp_path: Path) -> None:
        """匿名/内部调用（脚本、管理命令）传进来的 user 若未认证，不得写进外键。"""
        pdf = _make_pdf(tmp_path / "卷宗.pdf", pages=1)
        anonymous = MagicMock()
        anonymous.is_authenticated = False
        with _patched_submits() as submit_factory:
            submit_factory.return_value.submit.return_value = "t"
            job = _service().create_job(
                file=_upload(pdf), source_path=None, template_key="filing_materials_v1", created_by=anonymous
            )
        assert job.created_by_id is None

    def test_认证用户记created_by(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "卷宗.pdf", pages=1)
        lawyer = LawyerFactory()
        with _patched_submits() as submit_factory:
            submit_factory.return_value.submit.return_value = "t"
            job = _service().create_job(
                file=_upload(pdf), source_path=None, template_key="filing_materials_v1", created_by=lawyer
            )
        job.refresh_from_db()
        assert job.created_by_id == lawyer.pk

    def test_任务提交失败时回滚任务行与目录(self, tmp_path: Path) -> None:
        """提交失败必须回滚：留下没有 task_id 的任务行 = 前端永远 pending 的僵尸。"""
        pdf = _make_pdf(tmp_path / "卷宗.pdf", pages=1)
        with _patched_submits() as submit_factory:
            submit_factory.return_value.submit.side_effect = RuntimeError("broker down")
            with pytest.raises(RuntimeError, match="broker down"):
                _service().create_job(file=_upload(pdf), source_path=None, template_key="filing_materials_v1")

        assert PdfSplitJob.objects.count() == 0, "提交失败不得留下僵尸任务行"
        jobs_dir = tmp_path / "pdf_splitting" / "jobs"
        leftover = list(jobs_dir.iterdir()) if jobs_dir.exists() else []
        assert leftover == [], "任务目录（含源文件副本）必须一并清掉"

    def test_损坏pdf被拒且不留下任何残留(self, tmp_path: Path) -> None:
        """端到端：损坏 PDF 上传必须 400（ValidationException）并回滚干净。

        这条同时锁两件事：①损坏文件不能变成 500（见 TestValidatePdfFile 的
        parametrize 用例）；②校验失败时既不能有任务行，也不能留下写了一半的
        任务目录（含那份源文件副本）。
        """
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"%PDF-1.4 not really a pdf")
        with _patched_submits() as submit_factory:
            with pytest.raises(ValidationException) as exc_info:
                _service().create_job(
                    file=SimpleUploadedFile("坏文件.pdf", broken.read_bytes(), content_type="application/pdf"),
                    source_path=None,
                    template_key="filing_materials_v1",
                )
        assert "PDF 无法打开" in exc_info.value.message
        submit_factory.assert_not_called()
        assert PdfSplitJob.objects.count() == 0
        jobs_dir = tmp_path / "pdf_splitting" / "jobs"
        leftover = list(jobs_dir.iterdir()) if jobs_dir.exists() else []
        assert leftover == [], "校验失败的目录必须被 storage.cleanup() 回收"


# ── find_reusable_job ─────────────────────────────────────────────


class TestFindReusableJob:
    """``find_reusable_job`` 的匹配口径。

    这个方法的成败直接等于钱：命中 → 律师直接拿到已有分段；miss → 164 页云端
    OCR + LLM 分段重跑一遍（几分钟 + 几十元）。所以口径必须**既宽到能复用、
    又严到不误用**，而这两条都是这里锁住的契约。
    """

    def test_文件名为空直接返回None(self) -> None:
        _make_job(name="任何.pdf")
        assert _service().find_reusable_job(source_name="", user=LawyerFactory()) is None

    def test_同名同页数且已出结果才命中(self) -> None:
        owner = LawyerFactory()
        job = _make_job(name="借贷纠纷.pdf", pages=5, status=PdfSplitJobStatus.COMPLETED, created_by=owner)
        found = _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=5, user=owner)
        assert found is not None and found.pk == job.pk

    @pytest.mark.parametrize("status", [PdfSplitJobStatus.PENDING, PdfSplitJobStatus.PROCESSING])
    def test_未出结果的任务不复用(self, status: str) -> None:
        """进行中的任务由 ``find_inflight_job`` 接管；这里返回它等于把半成品当结论。"""
        owner = LawyerFactory()
        _make_job(name="借贷纠纷.pdf", pages=5, status=status, created_by=owner)
        assert _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=5, user=owner) is None

    def test_页数不同不复用(self) -> None:
        """同名不同页 = 另一份文件。误用会让律师拿到别人卷宗的分段。"""
        owner = LawyerFactory()
        _make_job(name="借贷纠纷.pdf", pages=5, created_by=owner)
        assert _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=9, user=owner) is None

    def test_未传页数时不校验页数(self) -> None:
        """调用方拿不到页数时（附件元信息缺 page_count）只按文件名匹配，
        否则「能复用却显示要重跑」。"""
        owner = LawyerFactory()
        job = _make_job(name="借贷纠纷.pdf", pages=5, created_by=owner)
        found = _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=None, user=owner)
        assert found is not None and found.pk == job.pk

    def test_未传user一律不复用(self) -> None:
        """S17-01（2026-11-23 二轮审计）：端点是无 body 的 GET，API 层没有材料包归属校验。

        原口径「刻意不按 created_by 过滤」让「知道文件名 + 页数」的人都能拉到他人案件的
        `segments[].content_md`。新契约：拿不到用户上下文时**一律 miss**（miss 的代价是重跑，
        比越权读小得多）。
        """
        _make_job(name="借贷纠纷.pdf", pages=5, status=PdfSplitJobStatus.COMPLETED)
        assert _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=5, user=None) is None

    def test_跨属主不复用(self) -> None:
        """他人创建的任务不再复用（原口径会命中 → 水平越权读）。"""
        assistant = LawyerFactory()
        principal = LawyerFactory()
        _make_job(name="借贷纠纷.pdf", pages=5, status=PdfSplitJobStatus.COMPLETED, created_by=assistant)

        found = _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=5, user=principal)

        assert found is None, "他人创建的任务不得复用：会泄露对方案件的分段正文"

    def test_管理员可复用他人任务(self) -> None:
        """保留管理侧的运维能力（排障时用管理员身份接管复用）。"""
        assistant = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        job = _make_job(name="借贷纠纷.pdf", pages=5, status=PdfSplitJobStatus.COMPLETED, created_by=assistant)

        found = _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=5, user=admin)

        assert found is not None and found.pk == job.pk

    def test_取最新的一份(self) -> None:
        """同一文件被故意重跑过几次时，律师要看的是最终结论（最新那次）。"""
        owner = LawyerFactory()
        _make_job(name="借贷纠纷.pdf", pages=5, status=PdfSplitJobStatus.REVIEW_REQUIRED, created_by=owner)
        newest = _make_job(name="借贷纠纷.pdf", pages=5, status=PdfSplitJobStatus.COMPLETED, created_by=owner)

        found = _service().find_reusable_job(source_name="借贷纠纷.pdf", total_pages=5, user=owner)

        assert found is not None and found.pk == newest.pk


# ── 状态机：mark_completed / mark_failed / request_cancel ─────────


class TestMarkCompletedFailed:
    """状态收口写的是真实 DB，不是 mock 的 update kwargs。"""

    def test_mark_completed写满进度并清错误(self) -> None:
        job = _make_job(status=PdfSplitJobStatus.EXPORTING)
        PdfSplitJob.objects.filter(pk=job.pk).update(error_message="中间失败过")

        _service().mark_completed(job_id=job.id, export_zip_relpath="pdf_splitting/jobs/x/split.zip")

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.COMPLETED
        assert job.progress == 100
        assert job.export_zip_relpath == "pdf_splitting/jobs/x/split.zip"
        assert job.finished_at is not None
        assert job.error_message == "", "完成时必须清掉中途的错误信息，否则前端一直显示红字"

    def test_mark_failed截断超长错误(self) -> None:
        """error_message 是 TextField 但前端只显示摘要；截到 4000 防止整段 traceback 入库。"""
        job = _make_job(status=PdfSplitJobStatus.PROCESSING)
        _service().mark_failed(job_id=job.id, error_message="错" * 5000)

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.FAILED
        assert len(job.error_message) == 4000
        assert job.finished_at is not None

    def test_mark_failed不存在的任务不抛(self) -> None:
        """任务可能已被并发删掉；收口方法用 filter().update() 而不是 get()，
        正是为了不因 NotFound 把 worker 的 finally 再炸一次。"""
        _service().mark_failed(job_id=uuid.uuid4(), error_message="无所谓")
        assert PdfSplitJob.objects.count() == 0


class TestRequestCancel:
    """``request_cancel`` 的协作式取消。

    只有**还没被 worker 捡起**（pending 且队列里删得掉 / 没有在跑）的任务才直接置
    cancelled；已在跑的只能打 ``cancel_requested`` 标记，由 worker 自己在检查点退出
    ——强行改状态会让它跑完后覆盖回 completed，出现「取消了却又变成完成」。
    """

    def test_终态任务原样返回(self) -> None:
        job = _make_job(status=PdfSplitJobStatus.COMPLETED)
        returned = _service().request_cancel(job_id=job.id)
        job.refresh_from_db()
        assert returned.status == PdfSplitJobStatus.COMPLETED
        assert job.cancel_requested is False

    def test_pending任务直接置为已取消(self) -> None:
        job = _make_job(status=PdfSplitJobStatus.PENDING)
        _service().request_cancel(job_id=job.id)
        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.CANCELLED
        assert job.cancel_requested is True
        assert job.finished_at is not None

    def test_正在跑的任务只打标记(self) -> None:
        """worker 已经在跑时不能直接改状态：它跑完会把状态覆盖回自己的结论。"""
        job = _make_job(status=PdfSplitJobStatus.PROCESSING)
        PdfSplitJob.objects.filter(pk=job.pk).update(task_id="task-running")

        with _patched_submits() as submit_factory:
            submit_factory.return_value.cancel.return_value = {"queue_deleted": 0, "running": True}
            _service().request_cancel(job_id=job.id)

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.PROCESSING
        assert job.cancel_requested is True
        assert job.finished_at is None

    def test_取消失败也要打上标记(self) -> None:
        """队列不可用时取消接口本身不能 500：标记照打，由 worker 检查点兜底。"""
        job = _make_job(status=PdfSplitJobStatus.PROCESSING)
        PdfSplitJob.objects.filter(pk=job.pk).update(task_id="task-x")

        with _patched_submits() as submit_factory:
            submit_factory.return_value.cancel.side_effect = RuntimeError("broker down")
            _service().request_cancel(job_id=job.id)

        job.refresh_from_db()
        assert job.cancel_requested is True
        assert job.status == PdfSplitJobStatus.PROCESSING

    def test_他人任务按不存在处理(self) -> None:
        """取消是写操作，口径与 get_job 一致：非本人任务按不存在。"""
        owner = LawyerFactory()
        stranger = LawyerFactory()
        job = _make_job(status=PdfSplitJobStatus.PENDING, created_by=owner)

        with pytest.raises(NotFoundError):
            _service().request_cancel(job_id=job.id, user=stranger)

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.PENDING


# ── load_segments_* 降级链 ────────────────────────────────────────


class TestLoadSegmentsDegradation:
    """``segments_md.json`` 的三条读回通道。

    旧任务没有这个产物、产物也可能被写坏（磁盘满/进程被杀写了一半）。三个 loader
    都必须**回空表而不是抛异常**：它们服务于任务详情接口，读不出来顶多让前端少了
    正文/坐标/质量提示，绝不能让人打不开一个已经跑完的任务。
    """

    def test_文件不存在回空表(self, tmp_path: Path) -> None:
        missing = tmp_path / "segments_md.json"
        assert load_segments_md(missing) == {}
        assert load_segments_positioned(missing) == {}
        assert load_segments_quality_flags(missing) == {}

    def test_json损坏回空表(self, tmp_path: Path) -> None:
        broken = tmp_path / "segments_md.json"
        broken.write_text("{ 半个 json", encoding="utf-8")
        assert load_segments_md(broken) == {}
        assert load_segments_positioned(broken) == {}
        assert load_segments_quality_flags(broken) == {}

    def test_顶层不是数组回空表(self, tmp_path: Path) -> None:
        """写成了 dict 而不是 list 时不能迭代出键名当分段。"""
        wrong = tmp_path / "segments_md.json"
        wrong.write_text(json.dumps({"segments": []}), encoding="utf-8")
        assert load_segments_md(wrong) == {}
        assert load_segments_positioned(wrong) == {}
        assert load_segments_quality_flags(wrong) == {}

    def test_条目不是字典时跳过(self, tmp_path: Path) -> None:
        mixed = tmp_path / "segments_md.json"
        mixed.write_text(
            json.dumps(["坏条目", 42, {"order": 1, "markdown": "正文"}], ensure_ascii=False),
            encoding="utf-8",
        )
        assert load_segments_md(mixed) == {1: "正文"}

    def test_order不是整数时跳过(self, tmp_path: Path) -> None:
        """order 是下游 API 的排序键；转不成整数就只能丢掉这一条，不能整表作废。"""
        mixed = tmp_path / "segments_md.json"
        mixed.write_text(
            json.dumps(
                [
                    {"order": "第一段", "markdown": "无效序"},
                    {"order": None, "positioned": [{"bbox": [1, 2, 3, 4]}]},
                    {"order": "2", "markdown": "有效序", "positioned": [{"bbox": [1, 2, 3, 4]}]},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        assert load_segments_md(mixed) == {2: "有效序"}
        assert load_segments_positioned(mixed) == {2: [{"bbox": [1, 2, 3, 4]}]}

    def test_positioned条目只留字典(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "positioned": [{"text": "块"}, "坏块", 7]}]),
            encoding="utf-8",
        )
        assert load_segments_positioned(path) == {1: [{"text": "块"}]}

    def test_quality_flags只留非空字符串(self, tmp_path: Path) -> None:
        """质量提示要直接展示给律师；空串/非字符串会把提示渲染成空白胶囊。"""
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "quality_flags": ["疑似错字", "", None, 3]}]),
            encoding="utf-8",
        )
        assert load_segments_quality_flags(path) == {1: ["疑似错字"]}

    def test_quality_flags不是数组时整条丢弃(self, tmp_path: Path) -> None:
        """写成字符串时不能逐字符迭代成 ['疑','似',...]——那会让前端显示一堆单字胶囊。"""
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "quality_flags": "疑似错字"}, {"order": 2, "quality_flags": ["正常"]}]),
            encoding="utf-8",
        )
        assert load_segments_quality_flags(path) == {2: ["正常"]}

    def test_positioned不是数组时整条丢弃(self, tmp_path: Path) -> None:
        path = tmp_path / "segments_md.json"
        path.write_text(
            json.dumps([{"order": 1, "positioned": {"bbox": [1, 2, 3, 4]}}, {"order": 2, "positioned": []}]),
            encoding="utf-8",
        )
        assert load_segments_positioned(path) == {2: []}

    def test_markdown缺失时回空串而不是丢弃该段(self, tmp_path: Path) -> None:
        """order 存在但没写 markdown 时，该段仍要有条目：前端靠 order 对齐分段，
        缺条目会让正文与分段错位（比空正文更危险）。"""
        path = tmp_path / "segments_md.json"
        path.write_text(json.dumps([{"order": 3}]), encoding="utf-8")
        assert load_segments_md(path) == {3: ""}
