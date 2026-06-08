"""
Unit tests for contracts/services/archive/generation/folder_builder.py.

Covers:
  - generate_archive_folder (no folder path, local success)
  - _write_template_doc_to_folder (no item code, no material)
  - _compile_final_archive_pdf (no case materials pdf)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.archive.generation.folder_builder import (
    _compile_final_archive_pdf,
    _write_template_doc_to_folder,
    generate_archive_folder,
)


def _make_contract(id: int = 1, name: str = "TestContract") -> MagicMock:
    c = MagicMock()
    c.id = id
    c.name = name
    c.case_type = "civil"
    return c


class TestGenerateArchiveFolder:
    def test_no_folder_path(self) -> None:
        contract = _make_contract()
        binding = MagicMock()
        binding.folder_path = ""
        binding.storage_type = "local"
        contract.folder_binding = binding
        result = generate_archive_folder(contract)
        assert result["success"] is False
        assert "未绑定" in result["error"]

    def test_local_folder_not_exists(self, tmp_path: Path) -> None:
        contract = _make_contract()
        binding = MagicMock()
        binding.folder_path = str(tmp_path / "nonexistent")
        binding.storage_type = "local"
        contract.folder_binding = binding
        result = generate_archive_folder(contract)
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_local_success(self, tmp_path: Path) -> None:
        contract = _make_contract()
        binding = MagicMock()
        binding.folder_path = str(tmp_path)
        binding.storage_type = "local"
        contract.folder_binding = binding

        with patch(
            "apps.contracts.services.archive.generation.folder_builder._generate_archive_folder_inner"
        ) as mock_inner:
            mock_inner.return_value = {
                "success": True,
                "archive_dir": str(tmp_path / "归档文件夹"),
                "generated_docs": [],
                "errors": [],
                "folder_path": str(tmp_path),
                "doc_results": [],
            }
            result = generate_archive_folder(contract)
        assert result["success"] is True


class TestWriteTemplateDocToFolder:
    def test_no_item_code(self, tmp_path: Path) -> None:
        contract = _make_contract()
        with patch(
            "apps.contracts.services.archive.generation.folder_builder.get_archive_category",
            return_value="litigation",
        ):
            with patch(
                "apps.contracts.services.archive.generation.folder_builder.ARCHIVE_CHECKLIST",
                {"litigation": []},
            ):
                with pytest.raises(ValueError, match="未找到模板子类型"):
                    _write_template_doc_to_folder(
                        contract=contract,
                        template_subtype="unknown_subtype",
                        seq_num=1,
                        doc_name="Test",
                        archive_dir=tmp_path,
                    )

    def test_no_material(self, tmp_path: Path) -> None:
        contract = _make_contract()
        with patch(
            "apps.contracts.services.archive.generation.folder_builder.get_archive_category",
            return_value="litigation",
        ):
            with patch(
                "apps.contracts.services.archive.generation.folder_builder.ARCHIVE_CHECKLIST",
                {"litigation": [{"template": "case_cover", "code": "lt_1"}]},
            ):
                with patch("apps.contracts.services.archive.generation.folder_builder.FinalizedMaterial") as mock_model:
                    mock_model.objects.filter.return_value.first.return_value = None
                    with pytest.raises(ValueError, match="尚未生成"):
                        _write_template_doc_to_folder(
                            contract=contract,
                            template_subtype="case_cover",
                            seq_num=1,
                            doc_name="案卷封面",
                            archive_dir=tmp_path,
                        )


class TestCompileFinalArchivePdf:
    def test_no_case_materials_pdf(self, tmp_path: Path) -> None:
        contract = _make_contract()
        result = _compile_final_archive_pdf(contract, tmp_path, case_materials_pdf_exists=False)
        assert result["written"] is False
        assert result["skipped"] is True
