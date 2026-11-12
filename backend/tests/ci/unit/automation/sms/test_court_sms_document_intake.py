"""客户转交材料入库服务（court_sms_document_intake.py）单元测试。

覆盖要点：
- 落盘走 storage_service.save_uploaded_file（清洗/白名单/大小上限）；
- 部分文件不受支持时整批不失败，逐条回报跳过原因；
- 全部不可用时拒绝建记录（不产生空记录）；
- 入库后状态直接进 MATCHING（跳过解析/下载），无下载链接；
- content 占位清单包含文件名，保证归档可读；
- 重复入库去重（同一路径不重复登记）；
- 只清理本通道目录下的文件，不越权删下载原件。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


def _pdf(name: str = "判决书.pdf") -> SimpleUploadedFile:
    # %PDF- 魔数 + 最小内容，足以通过可执行文件魔数检测
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


def _png(name: str = "证据.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, content_type="image/png")


@pytest.mark.django_db
class TestSaveMaterials:
    def _make_sms(self, **kwargs):
        from apps.automation.models import CourtSMS, CourtSMSStatus

        defaults = {
            "content": "",
            "received_at": __import__("django.utils.timezone", fromlist=["timezone"]).now(),
            "status": CourtSMSStatus.PENDING,
        }
        defaults.update(kwargs)
        return CourtSMS.objects.create(**defaults)

    def test_saves_files_and_moves_to_matching(self, tmp_path, settings):
        """成功入库：路径写进 document_file_paths，状态由 PENDING 提到 MATCHING。"""
        from apps.automation.models import CourtSMSStatus
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        settings.MEDIA_ROOT = tmp_path
        sms = self._make_sms()

        result = CourtSMSDocumentIntakeService().save_materials(sms.id, [_pdf(), _png()])

        assert len(result["saved"]) == 2
        assert result["skipped"] == []

        sms.refresh_from_db()
        assert len(sms.document_file_paths) == 2
        assert sms.status == CourtSMSStatus.MATCHING
        # 存的是 media 绝对路径，重命名后回写引用才不会漂移
        assert all(p.startswith(str(tmp_path)) for p in sms.document_file_paths)
        # 无下载链接 → 下游自动跳过下载阶段
        assert sms.download_links == []

    def test_rejects_when_all_files_unsupported(self, tmp_path, settings):
        """全部格式不符时拒绝建记录，不产生空任务。"""
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService
        from apps.core.exceptions import ValidationException

        settings.MEDIA_ROOT = tmp_path
        sms = self._make_sms()
        bad = SimpleUploadedFile("笔记.txt", b"hello", content_type="text/plain")

        with pytest.raises(ValidationException) as exc:
            CourtSMSDocumentIntakeService().save_materials(sms.id, [bad])

        assert "都不受支持" in str(exc.value.message)
        sms.refresh_from_db()
        assert sms.document_file_paths == []

    def test_rejects_empty_batch(self):
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc:
            CourtSMSDocumentIntakeService().save_materials(1, [])

        assert "至少拖入一个" in str(exc.value.message)

    def test_partial_failure_keeps_good_files(self, tmp_path, settings):
        """混合批次：合法的照常入库，非法的进 skipped 并带原因。"""
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        settings.MEDIA_ROOT = tmp_path
        sms = self._make_sms()
        good = _pdf()
        bad = SimpleUploadedFile("录屏.mov", b"\x00" * 8, content_type="video/quicktime")

        result = CourtSMSDocumentIntakeService().save_materials(sms.id, [good, bad])

        assert len(result["saved"]) == 1
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["name"] == "录屏.mov"
        assert result["skipped"][0]["reason"]

        sms.refresh_from_db()
        assert len(sms.document_file_paths) == 1

    def test_duplicate_save_is_deduplicated(self, tmp_path, settings):
        """同一路径重复登记不会重复进列表。"""
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        settings.MEDIA_ROOT = tmp_path
        sms = self._make_sms()
        intake = CourtSMSDocumentIntakeService()

        intake.save_materials(sms.id, [_pdf()])
        sms.refresh_from_db()
        first_paths = list(sms.document_file_paths)
        assert len(first_paths) == 1

        # 用存储侧返回的相对路径把同一条引用再合并一次：这才是真实重复入参的
        # 形状（「既有绝对路径」与「新来的相对路径」指向同一文件），并且必须
        # 真的合并掉一条——早前的版本传空列表，等于断言「空合并不改变列表」，
        # 去重逻辑一条都没覆盖到。
        relative_paths = [str(Path(p).relative_to(tmp_path)) for p in first_paths]
        intake._attach_paths(sms.id, relative_paths, ["判决书.pdf"])

        sms.refresh_from_db()
        assert list(sms.document_file_paths) == first_paths

    def test_raises_when_sms_missing(self, tmp_path, settings):
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService
        from apps.core.exceptions import ValidationException

        settings.MEDIA_ROOT = tmp_path
        with pytest.raises(ValidationException) as exc:
            CourtSMSDocumentIntakeService().save_materials(999_999, [_pdf()])

        assert "短信记录不存在" in str(exc.value.message)


@pytest.mark.django_db
class TestContentPlaceholder:
    def test_placeholder_lists_filenames(self):
        """占位正文含全部文件名，归档 markdown 不会是「(空)」。"""
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        content = CourtSMSDocumentIntakeService().build_content_placeholder(["判决书.pdf", "证据.png"])

        assert "客户转交材料" in content
        assert "判决书.pdf" in content
        assert "证据.png" in content
        assert "2 个文件" in content

    def test_placeholder_handles_empty_list(self):
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        content = CourtSMSDocumentIntakeService().build_content_placeholder([])

        assert "0 个文件" in content


class TestMeaningfulFilename:
    @pytest.mark.parametrize(
        "name",
        ["微信图片_20251110103000.jpg", "mmexport1699999999.png", "image001.jpg", "IMG_20251110_1030.heic"],
    )
    def test_wechat_style_names_are_not_meaningful(self, name):
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        assert CourtSMSDocumentIntakeService.is_meaningful_filename(name) is False

    @pytest.mark.parametrize("name", ["民事判决书.pdf", "（20XX）粤01民初某某号判决书.pdf", "送达回证.png"])
    def test_business_names_are_meaningful(self, name):
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        assert CourtSMSDocumentIntakeService.is_meaningful_filename(name) is True


@pytest.mark.django_db
class TestCleanupSafety:
    def test_cleanup_skips_paths_outside_intake_dir(self, tmp_path, settings):
        """下载原件（不在 automation/uploads 下）绝不能被本通道删掉。"""
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        settings.MEDIA_ROOT = tmp_path
        outsider = tmp_path / "court_documents" / "原件.pdf"
        outsider.parent.mkdir(parents=True, exist_ok=True)
        outsider.write_bytes(b"%PDF-1.4")

        removed = CourtSMSDocumentIntakeService().cleanup_paths([str(outsider)])

        assert removed == 0
        assert outsider.exists()

    def test_cleanup_removes_intake_files(self, tmp_path, settings):
        from apps.automation.services.sms.court_sms_document_intake import CourtSMSDocumentIntakeService

        settings.MEDIA_ROOT = tmp_path
        intake_dir = tmp_path / "automation" / "uploads"
        intake_dir.mkdir(parents=True, exist_ok=True)
        target = intake_dir / "材料.pdf"
        target.write_bytes(b"%PDF-1.4")

        removed = CourtSMSDocumentIntakeService().cleanup_paths([str(target)])

        assert removed == 1
        assert not target.exists()


@pytest.mark.django_db
class TestSubmitSmsWithMaterials:
    """service.submit_sms 的文件通道行为。"""

    def test_empty_content_and_no_materials_still_rejected(self):
        from apps.automation.services.sms.court_sms_service import CourtSMSService
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc:
            CourtSMSService().submit_sms("")

        assert "不能为空" in str(exc.value.message)

    @patch("apps.automation.services.sms.court_sms_service.submit_task")
    def test_materials_alone_create_record_and_queue_task(self, mock_submit, tmp_path, settings):
        """只有文件、没有短信原文也能提交：建记录 + 落盘 + 入队。"""
        from apps.automation.models import CourtSMS, CourtSMSStatus
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        settings.MEDIA_ROOT = tmp_path
        mock_submit.return_value = "task-materials"

        sms = CourtSMSService().submit_sms("", materials=[_pdf("客户转来判决书.pdf")])

        assert sms.id
        assert "客户转来判决书.pdf" in sms.content
        assert sms.status == CourtSMSStatus.MATCHING
        assert len(sms.document_file_paths) == 1
        assert sms.material_intake_result is not None  # type: ignore[attr-defined]
        assert sms.material_intake_result["saved"] == ["客户转来判决书.pdf"]  # type: ignore[attr-defined]
        mock_submit.assert_called_once()

        assert CourtSMS.objects.filter(id=sms.id).exists()

    @patch("apps.automation.services.sms.court_sms_service.submit_task")
    def test_sms_channel_returns_none_intake(self, mock_submit):
        """短信通道提交不返回材料明细（保 API 语义一致）。"""
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        mock_submit.return_value = "task-sms"
        sms = CourtSMSService().submit_sms("【某法院】开庭通知")

        assert sms.material_intake_result is None  # type: ignore[attr-defined]

    @patch("apps.automation.services.sms.court_sms_service.submit_task")
    def test_duplicate_material_batch_returns_existing(self, mock_submit, tmp_path, settings):
        """同一批材料在去重窗口内重复提交 → 幂等返回既有记录，不重复建。"""
        from datetime import datetime, timedelta

        from apps.automation.models import CourtSMS
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        settings.MEDIA_ROOT = tmp_path
        mock_submit.return_value = "task-dup"
        received = datetime(2025, 6, 1, 10, 0, 0)
        svc = CourtSMSService()

        first = svc.submit_sms("", received_at=received, materials=[_pdf("同一份.pdf")])
        second = svc.submit_sms("", received_at=received + timedelta(seconds=20), materials=[_pdf("同一份.pdf")])

        assert second.id == first.id
        assert CourtSMS.objects.count() == 1


@pytest.mark.django_db
class TestProcessPipelineForMaterialChannel:
    """验证文件通道能被既有状态机消费（不需要下载阶段）。"""

    def test_parsing_waits_when_matching_without_links(self, tmp_path, settings):
        """无下载链接 + 已有材料 → 直接进匹配，不会被解析阶段覆盖状态。"""
        from apps.automation.models import CourtSMS, CourtSMSStatus
        from apps.automation.services.sms.court_sms_service import CourtSMSService

        settings.MEDIA_ROOT = tmp_path
        sms = CourtSMS.objects.create(
            content="【客户转交材料】1 个文件：判决书.pdf",
            received_at=__import__("django.utils.timezone", fromlist=["timezone"]).now(),
            status=CourtSMSStatus.MATCHING,
            document_file_paths=[],
        )
        parser = MagicMock()
        svc = CourtSMSService(parser=parser, matcher=MagicMock())

        result = svc._process_downloading_or_matching(sms)

        # 无链接 → matching；不建下载任务，不调解析器
        assert result.status == CourtSMSStatus.MATCHING
        assert result.scraper_task is None
