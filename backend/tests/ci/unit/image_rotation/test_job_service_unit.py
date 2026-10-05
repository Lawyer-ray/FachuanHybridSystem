"""ImageRotationJobService 单元测试 — 任务创建/查询/删除与 OCR 重识别编排。

存储经 autouse fixture 把 MEDIA_ROOT 指到临时目录；OCR / 重命名服务注入 mock。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.exceptions import NotFoundError
from apps.image_rotation.models import ImageRotationJob, ImageRotationJobStatus, ImageRotationPage
from apps.image_rotation.services.job_service import ImageRotationJobService, _guess_ext
from apps.testing.factories import LawyerFactory


@pytest.fixture(autouse=True)
def _media_root(tmp_path: Any) -> Any:
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        yield


def test_guess_ext_case_insensitive() -> None:
    assert _guess_ext("PHOTO.TIF") == ".tif"
    assert _guess_ext("photo.heic") == ".jpg"


def _meta(filename: str, page_number: int = 0, **kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "filename": filename,
        "detected_rotation": 90,
        "detection_confidence": 0.87,
        "source_type": "image",
        "page_number": page_number,
    }
    base.update(kwargs)
    return base


def _png(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\nfake", content_type="image/png")


@pytest.mark.django_db
class TestCreateJob:
    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="数量不匹配"):
            ImageRotationJobService.create_job(
                name="任务",
                pages_meta=[_meta("a.png")],
                source_files=[_png("a.png"), _png("b.png")],
            )

    def test_creates_job_and_pages(self) -> None:
        job = ImageRotationJobService.create_job(
            name="扫描件",
            pages_meta=[_meta("a.png", page_number=0), _meta("b.jpg", page_number=1, detected_rotation=180)],
            source_files=[_png("a.png"), _png("b.jpg")],
        )

        assert job.name == "扫描件"
        assert job.status == ImageRotationJobStatus.COMPLETED
        assert job.total_pages == 2
        pages = list(job.pages.order_by("page_number"))
        assert [p.original_filename for p in pages] == ["a.png", "b.jpg"]
        assert [p.detected_rotation for p in pages] == [90, 180]
        assert pages[0].detection_confidence == pytest.approx(0.87)
        # 源文件已写入存储（UUID 名 + 扩展名）
        assert pages[0].source_image.name.endswith(".png")
        assert pages[0].source_image.size > 0

    def test_default_page_number_uses_index(self) -> None:
        job = ImageRotationJobService.create_job(
            name="", pages_meta=[{"filename": "x.png"}], source_files=[_png("x.png")]
        )
        page = job.pages.get()
        assert page.page_number == 0
        assert page.detected_rotation == 0
        assert page.source_type == "image"


@pytest.mark.django_db
class TestQueryAndDelete:
    def test_get_job_not_found_raises(self) -> None:
        with pytest.raises(NotFoundError, match="不存在"):
            ImageRotationJobService.get_job("00000000-0000-0000-0000-000000000000")

    def test_get_job_and_detail(self) -> None:
        job = ImageRotationJobService.create_job(
            name="详情",
            pages_meta=[_meta("a.png"), _meta("b.png", page_number=1)],
            source_files=[_png("a.png"), _png("b.png")],
        )
        found, pages = ImageRotationJobService.get_job_detail(job.id)
        assert found.pk == job.pk
        assert len(pages) == 2

    def test_list_jobs_pagination_and_owner_filter(self) -> None:
        ImageRotationJobService.create_job(name="j1", pages_meta=[], source_files=[])
        ImageRotationJobService.create_job(name="j2", pages_meta=[], source_files=[])
        result = ImageRotationJobService.list_jobs(page=1, page_size=1)
        assert result["total"] == 2
        assert result["total_pages"] == 2
        assert len(result["items"]) == 1
        # created_by 过滤：其他用户的任务列表为空
        other = LawyerFactory()
        assert ImageRotationJobService.list_jobs(created_by=other)["total"] == 0

    def test_delete_job_removes_row(self) -> None:
        job = ImageRotationJobService.create_job(name="del", pages_meta=[], source_files=[])
        ImageRotationJobService.delete_job(job.id)
        assert not ImageRotationJob.objects.filter(pk=job.pk).exists()


@pytest.mark.django_db
class TestRunOcr:
    def _job(self) -> ImageRotationJob:
        return ImageRotationJobService.create_job(
            name="ocr",
            pages_meta=[_meta("a.png"), _meta("b.png", page_number=1)],
            source_files=[_png("a.png"), _png("b.png")],
        )

    def test_ocr_and_rename_applied(self) -> None:
        job = self._job()
        ocr = MagicMock()
        ocr.extract_text.return_value = SimpleNamespace(text="（2026）粤0604民初1号 传票")
        suggestion = SimpleNamespace(success=True, suggested_filename="传票_a.png")
        with patch("apps.image_rotation.services.auto_rename_service.AutoRenameService") as rename_cls:
            rename_cls.return_value.suggest_rename.return_value = suggestion
            pages = ImageRotationJobService.run_ocr(job.id, ocr_service=ocr)

        assert ocr.extract_text.call_count == 2
        for page in pages:
            page.refresh_from_db()
            assert page.ocr_text == "（2026）粤0604民初1号 传票"
            assert page.suggested_filename == "传票_a.png"

    def test_rename_suggestion_failure_keeps_filename(self) -> None:
        job = self._job()
        ocr = MagicMock()
        ocr.extract_text.return_value = SimpleNamespace(text="有效文本")
        suggestion = SimpleNamespace(success=False, suggested_filename="")
        with patch("apps.image_rotation.services.auto_rename_service.AutoRenameService") as rename_cls:
            rename_cls.return_value.suggest_rename.return_value = suggestion
            pages = ImageRotationJobService.run_ocr(job.id, ocr_service=ocr)

        for page in pages:
            page.refresh_from_db()
            assert page.ocr_text == "有效文本"
            assert page.suggested_filename == ""

    def test_blank_text_skips_rename(self) -> None:
        job = self._job()
        ocr = MagicMock()
        ocr.extract_text.return_value = SimpleNamespace(text="   ")
        with patch("apps.image_rotation.services.auto_rename_service.AutoRenameService") as rename_cls:
            pages = ImageRotationJobService.run_ocr(job.id, ocr_service=ocr)

        rename_cls.return_value.suggest_rename.assert_not_called()
        assert all(p.ocr_text == "   " for p in pages)

    def test_ocr_exception_swallowed_per_page(self) -> None:
        job = self._job()
        ocr = MagicMock()
        ocr.extract_text.side_effect = RuntimeError("引擎崩溃")
        with patch("apps.image_rotation.services.auto_rename_service.AutoRenameService"):
            pages = ImageRotationJobService.run_ocr(job.id, ocr_service=ocr)
        assert len(pages) == 2  # 单页失败不阻断

    def test_cloud_provider_builds_ocr_service(self) -> None:
        job = self._job()
        built = MagicMock()
        built.extract_text.return_value = SimpleNamespace(text="t")
        with (
            patch("apps.image_rotation.services.auto_rename_service.AutoRenameService") as rename_cls,
            patch("apps.automation.services.ocr.ocr_service.OCRService", return_value=built) as m_cls,
        ):
            rename_cls.return_value.suggest_rename.return_value = SimpleNamespace(success=False, suggested_filename="")
            pages = ImageRotationJobService.run_ocr(job.id, provider="siliconflow")

        m_cls.assert_called_once_with(use_v5=True, provider="siliconflow")
        assert built.extract_text.call_count == 2
        assert len(pages) == 2

    def test_local_provider_uses_service_locator(self) -> None:
        job = self._job()
        located = MagicMock()
        located.extract_text.return_value = SimpleNamespace(text="t")
        with (
            patch("apps.image_rotation.services.auto_rename_service.AutoRenameService") as rename_cls,
            patch("apps.core.interfaces.ServiceLocator.get_ocr_service", return_value=located),
        ):
            rename_cls.return_value.suggest_rename.return_value = SimpleNamespace(success=False, suggested_filename="")
            ImageRotationJobService.run_ocr(job.id, provider="local")

        assert located.extract_text.call_count == 2


@pytest.mark.django_db(transaction=True)
class TestAsyncRunOcr:
    @pytest.mark.asyncio
    async def test_arun_ocr_applies_text(self) -> None:
        from asgiref.sync import sync_to_async

        job = await sync_to_async(ImageRotationJobService.create_job)(
            name="async", pages_meta=[_meta("a.png")], source_files=[_png("a.png")]
        )
        ocr = MagicMock()
        ocr.extract_text.return_value = SimpleNamespace(text="异步OCR文本")
        with patch("apps.image_rotation.services.auto_rename_service.AutoRenameService") as rename_cls:
            rename_cls.return_value.suggest_rename.return_value = SimpleNamespace(success=False, suggested_filename="")
            pages = await ImageRotationJobService.arun_ocr(job.id, ocr_service=ocr)

        assert len(pages) == 1
        page = await ImageRotationPage.objects.aget(pk=pages[0].pk)
        assert page.ocr_text == "异步OCR文本"

    @pytest.mark.asyncio
    async def test_arun_ocr_exception_swallowed(self) -> None:
        from asgiref.sync import sync_to_async

        job = await sync_to_async(ImageRotationJobService.create_job)(
            name="async-err", pages_meta=[_meta("a.png")], source_files=[_png("a.png")]
        )
        ocr = MagicMock()
        ocr.extract_text.side_effect = RuntimeError("异步失败")
        with patch("apps.image_rotation.services.auto_rename_service.AutoRenameService"):
            pages = await ImageRotationJobService.arun_ocr(job.id, ocr_service=ocr)
        assert len(pages) == 1
