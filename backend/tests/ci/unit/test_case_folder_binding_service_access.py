from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from apps.cases.models import Case, CaseFolderBinding
from apps.cases.services.template.folder_binding_service import CaseFolderBindingService


def _build_staff_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        is_authenticated=True,
        is_admin=False,
        is_superuser=False,
        is_staff=True,
    )


def test_list_bound_subdirs_allows_staff_user_with_bound_case(db, tmp_path: Path) -> None:
    case = Case.objects.create(name="Case A", case_type="civil")
    root = tmp_path / "case_root"
    (root / "stage1" / "evidence").mkdir(parents=True)
    CaseFolderBinding.objects.create(case=case, folder_path=str(root))

    service = CaseFolderBindingService()
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.list_bound_subdirs(owner_id=case.id, user=_build_staff_user())

    assert Path(result["root_path"]).resolve() == root.resolve()
    assert {entry["name"] for entry in result["entries"]} == {"stage1"}


def test_recommend_bound_subdir_allows_staff_user_with_bound_case(db, tmp_path: Path) -> None:
    case = Case.objects.create(name="Case B", case_type="civil")
    root = tmp_path / "case_root"
    (root / "stage1" / "evidence").mkdir(parents=True)
    CaseFolderBinding.objects.create(case=case, folder_path=str(root))

    service = CaseFolderBindingService()
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=case.id,
        user=_build_staff_user(),
        source_subfolder="stage1/evidence",
    )

    assert result["recommended_subdir"] == "stage1/evidence"
    assert result["matched_existing_subdir"] == "stage1/evidence"
    assert result["reason"] == "source_subfolder_match"
