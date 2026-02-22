"""
DocumentAttachmentService 服务单元测试
"""

import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
from pathlib import Path


class TestDocumentAttachmentService:
    def test_add_to_case_log_uses_shutil_copy2(self, settings):
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings.MEDIA_ROOT = tmp_dir

            src_file = Path(tmp_dir) / "通知书（测试案件）_20260121收.pdf"
            src_file.write_text("test")

            sms = SimpleNamespace(
                id=28,
                case_log=SimpleNamespace(id=123),
                case=SimpleNamespace(name="测试案件"),
            )

            case_service = MagicMock()
            case_service.add_case_log_attachment_internal.return_value = True

            service = DocumentAttachmentService(case_service=case_service)

            with patch("shutil.copy2") as copy2_mock:
                ok = service.add_to_case_log(sms, [str(src_file)])  # type: ignore[arg-type]

            assert ok is True
            copy2_mock.assert_called_once()
            case_service.add_case_log_attachment_internal.assert_called_once()
