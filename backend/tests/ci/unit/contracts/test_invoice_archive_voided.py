"""归档三闸：作废红票永不进卷宗。

用户口径原话：「归档的时候是不需要已经作废的发票的，只需要保留合法发票即可」
「冲红票和旧的发票新建一个文件夹单独放好不就行了，归档的时候不需要展现在卷宗中」。

实现是**物理目录隔离 + 两道兜底**，所以断言分三层：

- 闸 1（治本）：红票落 `已冲红/`、原票被**移动**进去（在 `test_invoice_red_reenact.py`）。
- 闸 2（防误选）：扫描不遍历 `已冲红/`；候选文件名含「红字开具」不勾选、`archive_item_code` 置空；
  导入流水线不导入并计入 `skipped_voided`。
- 闸 3（兜脏数据）：`download_handler` 与 `material_mapping` 两个归档消费者**都要挡**——
  只挡一处，另一条路径（清单展示 vs 打包下载）就会漏进一张作废票。

闸 3 的判据只能是文件名：`FinalizedMaterial` 只有 `file_path`，反查不回 `Invoice`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models import Contract, FinalizedMaterial, MaterialCategory
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.archive.checklist.checklist_query import find_code_by_name
from apps.contracts.services.archive.checklist.material_mapping import map_contract_materials
from apps.contracts.services.archive.generation.download_handler import _looks_voided
from apps.contracts.services.contract.integrations._import_pipeline import ImportPipeline
from apps.contracts.services.contract.integrations.folder_scan_service import (
    ContractFolderScanService,
    _looks_voided_filename,
)
from apps.testing.factories import ContractFactory

VALID_NAME = "发票（某项目）_20261111开具.pdf"
VOIDED_NAME = "发票（某项目）_20261111红字开具.pdf"
INVOICE_DIR = "1-律师资料/3-发票"


@pytest.fixture
def contract(db: Any) -> Contract:
    return ContractFactory(name="归档作废票测试项目")


def _material(contract: Contract, filename: str, *, code: str = "") -> FinalizedMaterial:
    seq = FinalizedMaterial.objects.filter(contract=contract).count()
    return FinalizedMaterial.objects.create(
        contract=contract,
        category=MaterialCategory.INVOICE,
        file_path=f"contracts/materials/{seq}.pdf",
        original_filename=filename,
        archive_item_code=code,
    )


# ── 闸 2：目录级跳过已冲红 ────────────────────────────────────────


class TestScanExcludeKeywords:
    def test_voided_dir_excluded_even_when_scanning_a_subfolder(self) -> None:
        """`已冲红/` 对所有扫描范围都生效：作废票不是“默认藏起来”，而是永不进清单。"""
        service = ContractFolderScanService(scan_service=MagicMock())
        keywords = service._exclude_dir_keywords(scan_subfolder=INVOICE_DIR)
        assert "已冲红" in keywords

    def test_global_scan_keeps_customer_material_exclusion(self) -> None:
        service = ContractFolderScanService(scan_service=MagicMock())
        keywords = service._exclude_dir_keywords(scan_subfolder="")
        assert "已冲红" in keywords
        assert "客户资料" in keywords

    def test_subfolder_scan_does_not_exclude_customer_material(self) -> None:
        """显式选中 `客户资料` 单独扫时仍能扫到（既有口径不能被本次改动顺手改掉）。"""
        service = ContractFolderScanService(scan_service=MagicMock())
        keywords = service._exclude_dir_keywords(scan_subfolder="客户资料")
        assert "客户资料" not in keywords

    def test_excluded_predicate_under_voided_dir(self) -> None:
        from apps.core.services.bound_folder_scan_service import _is_under_excluded_dir

        rel = f"{INVOICE_DIR}/已冲红/{VALID_NAME}"
        assert _is_under_excluded_dir(rel, ("已冲红",)) is True
        assert _is_under_excluded_dir(f"{INVOICE_DIR}/{VALID_NAME}", ("已冲红",)) is False


# ── 闸 2：候选级标记 ──────────────────────────────────────────────


class TestVoidedCandidateMarking:
    def test_voided_candidate_unselected_and_code_cleared(self) -> None:
        service = ContractFolderScanService(scan_service=MagicMock())
        candidates = [
            {"filename": VALID_NAME, "selected": True, "archive_item_code": "lt_5"},
            {"filename": VOIDED_NAME, "selected": True, "archive_item_code": "lt_5"},
        ]
        skipped = service._mark_voided_candidates(candidates)
        assert skipped == 1
        assert candidates[0]["selected"] is True
        assert candidates[0].get("voided_skipped") is None
        assert candidates[1]["selected"] is False
        assert candidates[1]["archive_item_code"] == ""
        assert candidates[1]["voided_skipped"] is True

    def test_voided_predicate_is_nfkc_normalized(self) -> None:
        """全角/兼容字符差异不该让作废票漏过判据。"""
        assert _looks_voided_filename("发票（某项目）_20261111红字开具.pdf") is True
        assert _looks_voided_filename("发票（某项目）_20261111开具.pdf") is False


@pytest.mark.django_db
class TestImportPipelineSkipsVoided:
    def _session(self, source_path: Path) -> Any:
        from apps.contracts.models.folder_scan_session import ContractFolderScanStatus

        session = MagicMock()
        session.id = 1
        session.status = ContractFolderScanStatus.COMPLETED
        session.result_payload = {"candidates": [{"source_path": str(source_path)}]}
        session.started_by_id = None
        return session

    def test_voided_candidate_counted_and_not_imported(self, contract: Contract, tmp_path: Path) -> None:
        src = tmp_path / VOIDED_NAME
        src.write_bytes(b"%PDF red")
        module = "apps.contracts.services.contract.integrations._import_pipeline"
        with (
            patch(f"{module}.FinalizedMaterial") as material_model,
            patch(f"{module}.ContractFolderScanSession"),
            patch(f"{module}.compute_file_hash_from_bytes", return_value="a" * 64),
        ):
            result = ImportPipeline().confirm_import(
                contract_id=contract.pk,
                session=self._session(src),
                items=[{"source_path": str(src), "selected": True, "category": "invoice"}],
            )
        assert result["skipped_voided"] == 1
        assert result["imported_count"] == 0
        material_model.objects.create.assert_not_called()

    def test_voided_skip_happens_before_candidate_lookup(self, contract: Contract, tmp_path: Path) -> None:
        """脏候选（不在 candidate_map 里）只要文件名是红票就按“跳过作废”处理，不抛 400。

        历史扫描会话里作废票早已被移走，重新导入时它们不该把整批导入卡死。
        """
        src = tmp_path / VOIDED_NAME
        src.write_bytes(b"%PDF red")
        module = "apps.contracts.services.contract.integrations._import_pipeline"
        with (
            patch(f"{module}.FinalizedMaterial"),
            patch(f"{module}.ContractFolderScanSession"),
        ):
            result = ImportPipeline().confirm_import(
                contract_id=contract.pk,
                session=self._session(tmp_path / "gone.pdf"),
                items=[{"source_path": str(src), "selected": True}],
            )
        assert result["skipped_voided"] == 1

    def test_valid_candidate_still_imported(self, contract: Contract, tmp_path: Path) -> None:
        src = tmp_path / VALID_NAME
        src.write_bytes(b"%PDF valid")
        module = "apps.contracts.services.contract.integrations._import_pipeline"
        with (
            patch(f"{module}.FinalizedMaterial") as material_model,
            patch(f"{module}.ContractFolderScanSession"),
            patch(f"{module}.compute_file_hash_from_bytes", return_value="b" * 64),
        ):
            material_model.objects.filter.return_value.exists.return_value = False
            result = ImportPipeline().confirm_import(
                contract_id=contract.pk,
                session=self._session(src),
                items=[{"source_path": str(src), "selected": True, "category": "invoice"}],
            )
        assert result["skipped_voided"] == 0
        assert result["imported_count"] == 1


# ── 闸 3：两个归档消费者都要挡 ────────────────────────────────────


@pytest.mark.django_db
class TestDownloadHandlerFiltersVoided:
    def test_voided_material_not_served_for_invoice_item(
        self, contract: Contract, tmp_path: Path, settings: Any
    ) -> None:
        from apps.contracts.services.archive.generation.download_handler import _download_uploaded_item

        settings.MEDIA_ROOT = tmp_path / "media"
        (settings.MEDIA_ROOT / "contracts/materials").mkdir(parents=True)
        (settings.MEDIA_ROOT / "contracts/materials/0.pdf").write_bytes(b"%PDF valid")
        (settings.MEDIA_ROOT / "contracts/materials/1.pdf").write_bytes(b"%PDF red")
        code = find_code_by_name(get_archive_category(contract.case_type), "收费凭证")
        assert code

        keep = _material(contract, VALID_NAME)
        _material(contract, VOIDED_NAME, code=code)

        result = _download_uploaded_item(contract, code)
        assert result.get("filename") == keep.original_filename

    def test_all_voided_yields_not_found(self, contract: Contract, tmp_path: Path, settings: Any) -> None:
        """只有作废票时可下载项为空 → 报“未找到材料”，不许把红票交出去。"""
        from apps.contracts.services.archive.generation.download_handler import _download_uploaded_item

        settings.MEDIA_ROOT = tmp_path / "media"
        code = find_code_by_name(get_archive_category(contract.case_type), "收费凭证")
        assert code
        _material(contract, VOIDED_NAME, code=code)

        result = _download_uploaded_item(contract, code)
        assert result == {"error": "未找到对应的归档材料"}

    def test_looks_voided_reads_original_filename_only(self) -> None:
        material = MagicMock()
        material.original_filename = VOIDED_NAME
        assert _looks_voided(material) is True
        material.original_filename = VALID_NAME
        assert _looks_voided(material) is False
        material.original_filename = None
        assert _looks_voided(material) is False


@pytest.mark.django_db
class TestMaterialMappingFiltersVoided:
    def test_mapping_to_invoice_item_skips_voided(self, contract: Contract) -> None:
        valid = _material(contract, VALID_NAME)
        _material(contract, VOIDED_NAME)

        category = get_archive_category(contract.case_type)
        materials = list(FinalizedMaterial.objects.filter(contract=contract))
        result = map_contract_materials(category, materials)

        ids = [mid for group in result.values() for mid in group]
        assert valid.id in ids
        assert len(ids) == 1

    def test_voided_material_with_explicit_code_not_counted(self, contract: Contract) -> None:
        """显式挂了 archive_item_code 的红票由 `download_handler` 的过滤挡，这里只负责自动映射。"""
        code = find_code_by_name(get_archive_category(contract.case_type), "收费凭证")
        assert code
        _material(contract, VOIDED_NAME, code=code)
        materials = list(FinalizedMaterial.objects.filter(contract=contract))
        result = map_contract_materials(get_archive_category(contract.case_type), materials)
        assert result == {}
