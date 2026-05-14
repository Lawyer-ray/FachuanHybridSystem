from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from django.utils import timezone

from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService


def test_add_single_attachment_passes_original_file_path_to_case_service(tmp_path: Path) -> None:
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"pdf-bytes")

    case_service = Mock()
    case_service.add_case_log_attachment_internal.return_value = True
    service = DocumentAttachmentService(case_service=case_service)
    sms = SimpleNamespace(
        id=1,
        case_log=SimpleNamespace(id=88),
        case=SimpleNamespace(name="测试案件"),
        received_at=timezone.now(),
    )

    result = service._add_single_attachment(sms, str(source_file))

    assert result is True
    case_service.add_case_log_attachment_internal.assert_called_once_with(
        case_log_id=88,
        file_path=str(source_file),
        file_name="source（测试案件）_20260514收.pdf",
    )
