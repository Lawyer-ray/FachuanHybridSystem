"""文书引用隔离：案件日志附件不得混进「这条短信自己的文书」。

事故（2026-11-14）：`collect()` 无条件把案件日志下的全部附件算作本短信文书。
案件日志会累积同一案件多次送达的全部文书，于是 63 条有文书的短信里 **57 条**
取到的都是同一份别人的判决书 —— 一条「廉政监督卡」短信会去识别那份判决书，
把上诉期/缴费期限写进自己案件的日历。

修法：`collect(include_case_log_attachments=False)` 供送识别使用；
默认 True 只保留给详情展示。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService


def _sms(own_paths: list[str], attachment_path: str) -> MagicMock:
    """构造短信替身：有自有文书 + 案件日志里挂着别人的文书。"""
    attachment = MagicMock()
    attachment.file.path = attachment_path
    attachments = MagicMock()
    attachments.all.return_value = [attachment]

    case_log = MagicMock()
    case_log.attachments = attachments

    sms = MagicMock()
    sms.document_file_paths = own_paths
    sms.scraper_task = None
    sms.case_log = case_log
    return sms


@pytest.fixture
def files(tmp_path: Path) -> tuple[str, str]:
    own = tmp_path / "传票（本案）.pdf"
    own.write_bytes(b"%PDF-1.4 own")
    alien = tmp_path / "民事判决书（别的案）.pdf"
    alien.write_bytes(b"%PDF-1.4 alien")
    return str(own), str(alien)


class TestCaseLogAttachmentsExcludedForRecognition:
    def test_recognition_mode_returns_only_own_documents(self, files: tuple[str, str]) -> None:
        own, alien = files
        refs = CourtSMSDocumentReferenceService().collect(_sms([own], alien), include_case_log_attachments=False)
        paths = [Path(r.file_path).name for r in refs]
        assert paths == ["传票（本案）.pdf"], f"送识别不该拿到别人的文书，实际 {paths}"

    def test_detail_mode_still_includes_case_log(self, files: tuple[str, str]) -> None:
        """详情展示保持原行为（律师看得到同案件文书是有帮助的）。"""
        own, alien = files
        refs = CourtSMSDocumentReferenceService().collect(_sms([own], alien))
        paths = {Path(r.file_path).name for r in refs}
        assert paths == {"传票（本案）.pdf", "民事判决书（别的案）.pdf"}

    def test_recognition_mode_empty_when_no_own_documents(self, files: tuple[str, str]) -> None:
        """短信自己没有可用的文书时，宁可返回空（= 不送识别），也不能拿别人的顶上。"""
        _, alien = files
        refs = CourtSMSDocumentReferenceService().collect(_sms([], alien), include_case_log_attachments=False)
        assert refs == []
