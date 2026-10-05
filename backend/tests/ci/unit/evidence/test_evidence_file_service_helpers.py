"""EvidenceFileService 私有辅助方法测试。

覆盖 _get_page_count 的 PDF/非 PDF 分支、_compute_hash 的
chunks 与 read 双形态、_schedule_ocr 的成功与异常吞并。
"""

from __future__ import annotations

import hashlib
import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.evidence.services.core.evidence_file_service import EvidenceFileService


class TestGetPageCount:
    def test_pdf_delegates_to_pdf_utils(self) -> None:
        svc = EvidenceFileService()
        with patch(
            "apps.evidence.services.infrastructure.pdf_utils.get_pdf_page_count",
            return_value=7,
        ) as mock_count:
            assert svc._get_page_count(ext=".pdf", file=MagicMock()) == 7
        mock_count.assert_called_once()

    def test_non_pdf_returns_one(self) -> None:
        svc = EvidenceFileService()
        with patch("apps.evidence.services.infrastructure.pdf_utils.get_pdf_page_count") as mock_count:
            assert svc._get_page_count(ext=".jpg", file=MagicMock()) == 1
            assert svc._get_page_count(ext=".docx", file=MagicMock()) == 1
        mock_count.assert_not_called()


class TestComputeHash:
    def test_uploadedfile_with_chunks(self) -> None:
        payload = b"evidence-file-content"
        f = SimpleUploadedFile("a.pdf", payload)
        expected = hashlib.sha256(payload).hexdigest()

        assert EvidenceFileService._compute_hash(f) == expected
        # 计算后文件指针复位
        assert f.tell() == 0

    def test_plain_file_object_with_read(self) -> None:
        payload = b"plain-read-form"
        f = io.BytesIO(payload)
        expected = hashlib.sha256(payload).hexdigest()

        assert EvidenceFileService._compute_hash(f) == expected
        assert f.tell() == 0


class TestScheduleOcr:
    def test_submits_task(self) -> None:
        with patch("apps.core.tasking.submit_task") as mock_submit:
            EvidenceFileService._schedule_ocr(123)
        mock_submit.assert_called_once_with("apps.evidence.tasks.ocr_evidence_item_task", 123)

    def test_type_error_swallowed(self) -> None:
        with patch("apps.core.tasking.submit_task", side_effect=TypeError("bad arg")):
            assert EvidenceFileService._schedule_ocr(1) is None  # 吞并不上抛

    def test_value_error_swallowed(self) -> None:
        with patch("apps.core.tasking.submit_task", side_effect=ValueError("bad value")):
            assert EvidenceFileService._schedule_ocr(2) is None  # 吞并不上抛

    def test_unexpected_error_propagates(self) -> None:
        with patch("apps.core.tasking.submit_task", side_effect=RuntimeError("queue down")):
            with pytest.raises(RuntimeError):
                EvidenceFileService._schedule_ocr(3)


@pytest.mark.django_db
class TestUploadValidationBranches:
    """upload_file 的扩展名/大小校验分支（pragma no cover 标注，直接驱动以锁行为）。"""

    def _item(self):
        item = MagicMock()
        item.file = None
        return item

    def test_unsupported_format_rejected(self) -> None:
        svc = EvidenceFileService()
        f = SimpleUploadedFile("x.zip", b"zip")
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc_info:
            svc.upload_file(item=self._item(), file=f)  # type: ignore[arg-type]
        assert exc_info.value.code == "UNSUPPORTED_FILE_FORMAT"

    def test_oversize_rejected(self) -> None:
        svc = EvidenceFileService()
        f = MagicMock()
        f.name = "big.pdf"
        f.size = svc.MAX_FILE_SIZE + 1
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc_info:
            svc.upload_file(item=self._item(), file=f)  # type: ignore[arg-type]
        assert exc_info.value.code == "FILE_TOO_LARGE"
