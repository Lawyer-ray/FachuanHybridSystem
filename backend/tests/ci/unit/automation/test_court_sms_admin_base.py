from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from apps.automation.admin.sms.court_sms_admin_base import CourtSMSAdminBase
from apps.automation.models import CourtSMS
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReference


def test_documents_display_includes_archive_diagnostics() -> None:
    admin_instance = CourtSMSAdminBase(CourtSMS, None)
    sms = SimpleNamespace(id=12)
    references = [
        CourtSMSDocumentReference(
            display_name="判决书.pdf",
            file_path="D:/mock/judgment.pdf",
            source="case_log_attachment",
            original_name="广东省广州市天河区人民法院判决书.pdf",
            archived_subdir="4-法院送达材料/5-其他材料",
            recommended_subdir="4-法院送达材料/4-裁定书、判决书、通知书",
            recommendation_reason="court_sms_judgment_notice_match",
        )
    ]

    with patch(
        "apps.automation.admin.sms.court_sms_admin_base.CourtSMSDocumentReferenceService.collect",
        return_value=references,
    ), patch(
        "apps.automation.admin.sms.court_sms_admin_base.reverse",
        side_effect=lambda name, args: f"/mock/{name}/{'/'.join(str(arg) for arg in args)}",
    ):
        html = str(admin_instance.documents_display(sms))

    assert "原始文书名" in html
    assert "当前归档子目录" in html
    assert "系统推荐子目录" in html
    assert "推荐依据" in html
    assert "4-法院送达材料/4-裁定书、判决书、通知书" in html
    assert "裁定/判决/通知规则命中" in html
