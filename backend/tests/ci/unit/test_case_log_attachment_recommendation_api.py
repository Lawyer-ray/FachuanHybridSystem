from __future__ import annotations

from pathlib import Path

import pytest

from apps.automation.models import CourtSMS
from apps.cases.models import Case, CaseLog
from apps.cases.services.template.folder_binding_service import CaseFolderBindingService
from apps.organization.models import LawFirm, Lawyer


@pytest.mark.django_db
def test_court_sms_related_log_recommendation_uses_court_sms_scene(tmp_path: Path) -> None:
    firm = LawFirm.objects.create(name="测试律所")
    actor = Lawyer.objects.create_user(username="court-sms-log-api", password="testpass123", law_firm=firm, is_admin=True)
    case = Case.objects.create(name="测试案件", case_type="civil")
    log = CaseLog.objects.create(case=case, actor=actor, content="法院短信日志")
    CourtSMS.objects.create(content="法院送达", received_at="2026-05-14T10:00:00+08:00", case=case, case_log=log)

    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "4-法院送达材料" / "3-对方当事人提交材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=case.id,
        file_name="对方证据目录.pdf",
        source_scene="court_sms_attachment",
    )

    assert result["recommended_subdir"] == "4-法院送达材料/3-对方当事人提交材料"
    assert result["reason"] == "court_sms_opponent_material_match"
