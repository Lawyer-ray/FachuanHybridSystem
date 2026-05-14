from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
        source_scene="court_sms_attachment",
        recommendation_file_name="source.pdf",
    )


def test_add_single_attachment_prefers_original_recommendation_name(tmp_path: Path) -> None:
    source_file = tmp_path / "renamed.pdf"
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

    result = service._add_single_attachment(
        sms,
        str(source_file),
        recommendation_file_name="对方证据目录.pdf",
    )

    assert result is True
    case_service.add_case_log_attachment_internal.assert_called_once_with(
        case_log_id=88,
        file_path=str(source_file),
        file_name="renamed（测试案件）_20260514收.pdf",
        source_scene="court_sms_attachment",
        recommendation_file_name="对方证据目录.pdf",
    )


def test_build_recommendation_names_by_path_uses_court_document_name() -> None:
    service = DocumentAttachmentService(case_service=Mock())
    sms = SimpleNamespace(
        scraper_task=SimpleNamespace(
            documents=SimpleNamespace(
                filter=lambda **kwargs: [
                    SimpleNamespace(
                        local_file_path="D:/tmp/doc1.pdf",
                        c_wsmc="案件受理通知书",
                        c_wjgs="pdf",
                    )
                ]
            )
        )
    )

    with patch("apps.automation.services.sms.document_attachment_service.Path.exists", return_value=True):
        mapping = service.build_recommendation_names_by_path(sms)

    assert mapping[str(Path("D:/tmp/doc1.pdf").resolve())] == "案件受理通知书.pdf"


def test_build_recommendation_names_for_paths_maps_original_name_to_renamed_path() -> None:
    service = DocumentAttachmentService(case_service=Mock())
    sms = SimpleNamespace(
        scraper_task=SimpleNamespace(
            result={"files": ["D:/tmp/original.pdf"]},
            documents=SimpleNamespace(
                filter=lambda **kwargs: [
                    SimpleNamespace(
                        local_file_path="D:/tmp/original.pdf",
                        c_wsmc="对方证据目录",
                        c_wjgs="pdf",
                    )
                ]
            ),
        )
    )

    with patch("apps.automation.services.sms.document_attachment_service.Path.exists", return_value=True):
        mapping = service.build_recommendation_names_for_paths(
            sms,
            ["D:/tmp/renamed.pdf"],
            original_paths=["D:/tmp/original.pdf"],
        )

    assert mapping[str(Path("D:/tmp/renamed.pdf").resolve())] == "对方证据目录.pdf"
def test_build_recommendation_names_for_paths_prefers_saved_mapping() -> None:
    service = DocumentAttachmentService(case_service=Mock())
    sms = SimpleNamespace(
        scraper_task=SimpleNamespace(
            result={
                "recommendation_names_by_path": {
                    "D:/tmp/renamed.pdf": "鍙楃悊閫氱煡涔?pdf",
                }
            },
            documents=SimpleNamespace(filter=lambda **kwargs: []),
        )
    )

    with patch("apps.automation.services.sms.document_attachment_service.Path.exists", return_value=True):
        mapping = service.build_recommendation_names_for_paths(sms, ["D:/tmp/renamed.pdf"])

    assert mapping[str(Path("D:/tmp/renamed.pdf").resolve())] == "鍙楃悊閫氱煡涔?pdf"


def test_add_to_case_log_uses_saved_recommendation_mapping(tmp_path: Path) -> None:
    source_file = tmp_path / "renamed.pdf"
    source_file.write_bytes(b"pdf-bytes")

    case_service = Mock()
    case_service.add_case_log_attachment_internal.return_value = True
    service = DocumentAttachmentService(case_service=case_service)
    sms = SimpleNamespace(
        id=1,
        case_log=SimpleNamespace(id=88),
        case=SimpleNamespace(name="娴嬭瘯妗堜欢"),
        received_at=timezone.now(),
        scraper_task=SimpleNamespace(
            result={
                "recommendation_names_by_path": {
                    str(source_file): "瀵规柟璇佹嵁鐩綍.pdf",
                }
            }
        ),
    )

    result = service.add_to_case_log(sms, [str(source_file)])

    assert result is True
    kwargs = case_service.add_case_log_attachment_internal.call_args.kwargs
    assert kwargs["case_log_id"] == 88
    assert kwargs["file_path"] == str(source_file)
    assert kwargs["source_scene"] == "court_sms_attachment"
    assert kwargs["recommendation_file_name"] == "瀵规柟璇佹嵁鐩綍.pdf"
