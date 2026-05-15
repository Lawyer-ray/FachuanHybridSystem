from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.cases.services.log.case_log_attachment_storage_service import CaseLogAttachmentStorageService
from apps.cases.services.template.folder_binding_service import CaseFolderBindingService


def test_save_attachment_passes_recommendation_context_into_recommendation() -> None:
    business_storage = Mock()
    business_storage.save_uploaded_file.return_value = SimpleNamespace(
        legacy_file_path="D:/cases/test.pdf",
        root_type="case_folder",
        subdir_path="4-法院送达材料/3-对方当事人提交材料",
        relative_file_path="4-法院送达材料/3-对方当事人提交材料/test.pdf",
        original_filename="对方证据目录.pdf",
    )
    service = CaseLogAttachmentStorageService(business_storage_service=business_storage)

    recommend_mock = Mock(return_value={"recommended_subdir": "4-法院送达材料/3-对方当事人提交材料"})
    with patch.object(service, "recommend_attachment_subdir", recommend_mock):
        uploaded_file = SimpleNamespace(name="原始上传名.pdf")
        service.save_attachment(
            uploaded_file,
            case_id=10,
            target_subdir="",
            source_scene="court_sms_attachment",
            recommendation_file_name="对方证据目录.pdf",
        )

    kwargs = recommend_mock.call_args.kwargs
    assert kwargs["source_scene"] == "court_sms_attachment"
    assert kwargs["recommendation_file_name"] == "对方证据目录.pdf"


@pytest.mark.django_db
def test_recommend_bound_subdir_for_court_sms_acceptance(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "04-一审" / "04-法院送达材料" / "01-受理通知书").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: SimpleNamespace(current_stage="first_trial", case_type="civil")  # type: ignore[method-assign]
    service._resolve_business_root_from_binding = lambda owner_id, root: root  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="案件受理通知书.pdf",
        source_scene="court_sms_attachment",
    )

    assert result["recommended_subdir"] == "04-一审/04-法院送达材料/01-受理通知书"
    assert result["matched_existing_subdir"] == "04-一审/04-法院送达材料/01-受理通知书"
    assert result["reason"] == "court_sms_acceptance_match"


@pytest.mark.django_db
def test_recommend_bound_subdir_for_court_sms_opponent_strong_keywords(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "法院送达材料" / "对方当事人提交材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: SimpleNamespace(current_stage="first_trial", case_type="civil")  # type: ignore[method-assign]
    service._resolve_business_root_from_binding = lambda owner_id, root: root  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="对方证据目录.pdf",
        source_scene="court_sms_attachment",
    )

    assert result["recommended_subdir"] == "一审/法院送达材料/对方当事人提交材料"
    assert result["matched_existing_subdir"] == "一审/法院送达材料/对方当事人提交材料"
    assert result["reason"] == "court_sms_opponent_material_match"


@pytest.mark.django_db
def test_recommend_bound_subdir_for_court_sms_opponent_weak_keywords_after_notice_check(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "法院送达材料" / "对方当事人提交材料").mkdir(parents=True)
    (root / "一审" / "法院送达材料" / "裁定书、判决书、通知书").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: SimpleNamespace(current_stage="first_trial", case_type="civil")  # type: ignore[method-assign]
    service._resolve_business_root_from_binding = lambda owner_id, root: root  # type: ignore[method-assign]

    weak_result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="书面意见.pdf",
        source_scene="court_sms_attachment",
    )
    notice_result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="开庭通知书.pdf",
        source_scene="court_sms_attachment",
    )

    assert weak_result["recommended_subdir"] == "一审/法院送达材料/对方当事人提交材料"
    assert weak_result["reason"] == "court_sms_opponent_material_weak_match"
    assert notice_result["recommended_subdir"] == "一审/法院送达材料/裁定书、判决书、通知书"
    assert notice_result["reason"] == "court_sms_judgment_notice_match"


@pytest.mark.django_db
def test_recommend_bound_subdir_for_court_sms_creates_stage_based_path_when_missing(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    root.mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: SimpleNamespace(current_stage="first_trial", case_type="civil")  # type: ignore[method-assign]
    service._resolve_business_root_from_binding = lambda owner_id, root: root  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="案件受理通知书.pdf",
        source_scene="court_sms_attachment",
    )

    assert result["recommended_subdir"] == "一审/法院送达材料/受理通知书"
    assert result["matched_existing_subdir"] == ""
    assert result["reason"] == "court_sms_acceptance_match"


@pytest.mark.django_db
def test_recommend_bound_subdir_for_court_sms_uses_execution_stage_directory(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "03-执行" / "法院送达材料" / "其他材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: SimpleNamespace(current_stage="enforcement", case_type="execution")  # type: ignore[method-assign]
    service._resolve_business_root_from_binding = lambda owner_id, root: root  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="廉政监督卡.pdf",
        source_scene="court_sms_attachment",
    )

    assert result["recommended_subdir"] == "03-执行/法院送达材料/其他材料"
    assert result["matched_existing_subdir"] == "03-执行/法院送达材料/其他材料"
    assert result["reason"] == "court_sms_other_fallback"
