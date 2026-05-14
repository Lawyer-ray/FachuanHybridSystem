from __future__ import annotations

from pathlib import Path

from apps.contracts.models.archive_classification_rule import ArchiveClassificationRule
from apps.contracts.models.contract import Contract
from apps.contracts.services.folder.folder_binding_service import FolderBindingService


def test_recommend_bound_subdir_for_archive_item_matches_existing_path(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "归档清单" / "起诉状材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_archive_item(owner_id=1, archive_item_name="起诉状")

    assert result["recommended_subdir"] == "归档清单/起诉状材料"
    assert result["matched_existing_subdir"] == "归档清单/起诉状材料"
    assert result["reason"] == "matched_existing_subdir"


def test_recommend_bound_subdir_for_archive_item_falls_back_to_default(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "其他目录").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_archive_item(owner_id=1, archive_item_name="证据目录")

    assert result["recommended_subdir"] == "归档清单/证据目录"
    assert result["matched_existing_subdir"] == ""
    assert result["reason"] == "default_archive_item_subdir"


def test_recommend_bound_subdir_uses_rule_keywords(db, tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "案件材料" / "证据清单目录").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    ArchiveClassificationRule.objects.create(
        archive_category="litigation",
        filename_keyword="证据清单",
        archive_item_code="lt_10",
        hit_count=5,
        source="manual",
    )

    result = service.recommend_bound_subdir_for_archive_item(
        owner_id=1,
        archive_item_name="材料目录",
        archive_item_code="lt_10",
        case_type="civil",
    )

    assert result["recommended_subdir"] == "案件材料/证据清单目录"
    assert result["matched_existing_subdir"] == "案件材料/证据清单目录"
    assert result["reason"] == "matched_existing_subdir_with_rules"


def test_recommend_bound_subdir_for_material_category_prefers_contract_folder(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "合同附件" / "合同正本").mkdir(parents=True)
    (root / "归档文书").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=1,
        material_category="contract_original",
    )

    assert result["recommended_subdir"] == "合同附件/合同正本"
    assert result["matched_existing_subdir"] == "合同附件/合同正本"
    assert result["reason"] == "preferred_material_category_subdir"


def test_recommend_bound_subdir_for_contract_original_prefers_standard_business_path(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "1-律师资料" / "1-合同").mkdir(parents=True)
    (root / "合同附件" / "合同正本").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=1,
        material_category="contract_original",
    )

    assert result["recommended_subdir"] == "1-律师资料/1-合同"
    assert result["matched_existing_subdir"] == "1-律师资料/1-合同"
    assert result["reason"] == "preferred_material_category_subdir"


def test_recommend_bound_subdir_for_authorization_material_prefers_case_delegate_path(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "一审" / "1-立案材料" / "3-委托材料").mkdir(parents=True)
    (root / "归档清单" / "授权委托证明材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=1,
        material_category="authorization_material",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/3-委托材料"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/3-委托材料"
    assert result["reason"] == "preferred_material_category_subdir"


def test_recommend_bound_subdir_for_archive_upload_prefers_archive_root(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "归档清单").mkdir(parents=True)
    (root / "归档文书").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=1,
        material_category="archive_upload",
    )

    assert result["recommended_subdir"] == "归档清单"
    assert result["matched_existing_subdir"] == "归档清单"
    assert result["reason"] == "preferred_material_category_subdir"


def test_recommend_bound_subdir_for_material_category_prefers_preservation_folder_by_file_name(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "一审" / "1-立案材料" / "1-起诉状和反诉答辩状").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "8-保全申请书及保函").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=1,
        material_category="case_material",
        file_name="财产保全申请书吴杰案.pdf",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/8-保全申请书及保函"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/8-保全申请书及保函"
    assert result["reason"] in {"file_name_rule_match", "file_name_keyword_match"}


def test_recommend_bound_subdir_for_material_category_prefers_deeper_invoice_child_by_file_name(tmp_path: Path) -> None:
    service = FolderBindingService()
    root = tmp_path / "contract_root"
    (root / "1-律师资料" / "3-发票" / "专票").mkdir(parents=True)
    (root / "1-律师资料" / "3-发票" / "普票").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=1,
        material_category="invoice",
        file_name="增值税专用发票.pdf",
    )

    assert result["recommended_subdir"] == "1-律师资料/3-发票/专票"
    assert result["matched_existing_subdir"] == "1-律师资料/3-发票/专票"
    assert result["reason"] == "file_name_keyword_match"


def test_recommend_bound_subdir_uses_generated_contract_business_root(db, tmp_path: Path) -> None:
    service = FolderBindingService()
    contract = Contract.objects.create(name="合同1", case_type="civil")
    root = tmp_path / "contract_root"
    business_root = root / "2026.05.10-[民商事]合同1"
    (business_root / "1-律师资料" / "1-合同").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_material_category(
        owner_id=contract.id,
        material_category="contract_original",
    )

    assert result["recommended_subdir"] == "1-律师资料/1-合同"
    assert result["matched_existing_subdir"] == "1-律师资料/1-合同"
    assert result["reason"] == "preferred_material_category_subdir"


def test_list_bound_subdirs_uses_generated_contract_business_root(db, tmp_path: Path) -> None:
    service = FolderBindingService()
    contract = Contract.objects.create(name="合同1", case_type="civil")
    root = tmp_path / "contract_root"
    business_root = root / "2026.05.10-[民商事]合同1"
    (business_root / "1-律师资料" / "1-合同").mkdir(parents=True)
    (business_root / "归档文件夹").mkdir(parents=True)

    class Binding:
        folder_path = str(root)

    service.get_binding = lambda owner_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]

    result = service.list_bound_subdirs(owner_id=contract.id)

    assert Path(result["root_path"]).resolve() == business_root.resolve()
    assert result["current_path"] == ""
    assert {entry["name"] for entry in result["entries"]} == {"1-律师资料", "归档文件夹"}
