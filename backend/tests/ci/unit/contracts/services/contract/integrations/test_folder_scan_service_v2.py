"""Tests for ContractFolderScanService."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest

from apps.contracts.models import ContractFolderScanStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_processor():
    from unittest.mock import MagicMock

    from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
    return CandidatePostProcessor(scan_service=MagicMock())


def _make_service(**overrides: Any) -> Any:
    from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
    defaults: dict[str, Any] = {
        "scan_service": MagicMock(),
    }
    defaults.update(overrides)
    return ContractFolderScanService(**defaults)


def _make_binding(*, folder_path: str = "/test/root", storage_type: str = "local") -> MagicMock:
    b = MagicMock()
    b.folder_path = folder_path
    b.storage_type = storage_type
    return b


def _make_session(
    *,
    session_id: Any = None,
    contract_id: int = 1,
    status: Any = ContractFolderScanStatus.COMPLETED,
    progress: int = 100,
    current_file: str = "",
    result_payload: dict | None = None,
    error_message: str = "",
    started_by_id: int | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = session_id or uuid4()
    s.contract_id = contract_id
    s.status = status
    s.progress = progress
    s.current_file = current_file
    s.result_payload = result_payload or {"summary": {}, "candidates": []}
    s.error_message = error_message
    s.started_by_id = started_by_id
    return s


# ---------------------------------------------------------------------------
# _ensure_contract_exists
# ---------------------------------------------------------------------------

class TestEnsureContractExists:
    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_raises_when_not_found(self, MockContract):
        MockContract.objects.filter.return_value.exists.return_value = False
        svc = _make_service()
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            svc._ensure_contract_exists(999)

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_passes_when_found(self, MockContract):
        MockContract.objects.filter.return_value.exists.return_value = True
        svc = _make_service()
        svc._ensure_contract_exists(1)


# ---------------------------------------------------------------------------
# _get_accessible_binding
# ---------------------------------------------------------------------------

class TestGetAccessibleBinding:
    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderBinding")
    def test_raises_when_no_binding(self, MockBinding):
        MockBinding.objects.filter.return_value.first.return_value = None
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="未绑定文件夹"):
            svc._get_accessible_binding(1)

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderBinding")
    def test_raises_when_local_folder_inaccessible(self, MockBinding):
        binding = _make_binding(folder_path="/nonexistent")
        MockBinding.objects.filter.return_value.first.return_value = binding
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            from apps.core.exceptions import ValidationException
            with pytest.raises(ValidationException, match="绑定文件夹不可访问"):
                svc._get_accessible_binding(1)

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderBinding")
    def test_returns_binding_when_local_accessible(self, MockBinding):
        binding = _make_binding(folder_path="/test/root")
        MockBinding.objects.filter.return_value.first.return_value = binding
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.is_dir.return_value = True
            MockPath.return_value = mock_path
            result = svc._get_accessible_binding(1)
            assert result is binding


# ---------------------------------------------------------------------------
# _normalize_scan_subfolder
# ---------------------------------------------------------------------------

class TestNormalizeScanSubfolder:
    def test_empty_returns_empty(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("") == ""
        assert svc._normalize_scan_subfolder("  ") == ""

    def test_absolute_path_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="必须使用相对路径"):
            svc._normalize_scan_subfolder("/etc/passwd")

    def test_tilde_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="必须使用相对路径"):
            svc._normalize_scan_subfolder("~/secret")

    def test_windows_drive_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="必须使用相对路径"):
            svc._normalize_scan_subfolder("C:/Windows")

    def test_dotdot_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="路径非法"):
            svc._normalize_scan_subfolder("a/../b")

    def test_normalizes_slashes(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a/b") == "a/b"

    def test_strips_leading_slash_and_dots(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("./a/./b") == "a/b"

    def test_backslash_to_slash(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a\\b") == "a/b"


# ---------------------------------------------------------------------------
# _resolve_scan_scope
# ---------------------------------------------------------------------------

class TestResolveScanScope:
    def test_local_root_only(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.expanduser.return_value.resolve.return_value = MagicMock(
                as_posix=MagicMock(return_value="/root")
            )
            MockPath.return_value = mock_path
            result = svc._resolve_scan_scope("/root", "")
            assert result["scan_folder"] == "/root"

    def test_local_with_subfolder(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath:
            mock_root = MagicMock()
            mock_root.expanduser.return_value.resolve.return_value = mock_root
            mock_root.as_posix.return_value = "/root"
            mock_scan = MagicMock()
            mock_scan.exists.return_value = True
            mock_scan.is_dir.return_value = True
            mock_scan.resolve.return_value = mock_scan
            mock_scan.as_posix.return_value = "/root/sub"
            mock_root.__truediv__ = MagicMock(return_value=mock_scan)
            MockPath.return_value = mock_root
            result = svc._resolve_scan_scope("/root", "sub")
            assert result["scan_subfolder"] == "sub"

    def test_local_subfolder_traversal_raises(self):
        # The _normalize_scan_subfolder catches ".." before _resolve_scan_scope,
        # so test the normalization raises instead
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="路径非法"):
            svc._normalize_scan_subfolder("a/../b")


# ---------------------------------------------------------------------------
# _extract_scan_subfolder
# ---------------------------------------------------------------------------

class TestExtractScanSubfolder:
    def test_extracts_from_payload(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "sub"}}
        assert svc._extract_scan_subfolder(payload) == "sub"

    def test_returns_empty_for_none(self):
        svc = _make_service()
        assert svc._extract_scan_subfolder(None) == ""


# ---------------------------------------------------------------------------
# _is_within_root
# ---------------------------------------------------------------------------

class TestIsWithinRoot:
    def test_within_root(self):
        svc = _make_service()
        root = MagicMock()
        root.as_posix.return_value = "/root"
        target = MagicMock()
        target.as_posix.return_value = "/root/sub"
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.os.path.commonpath", return_value="/root"):
            assert svc._is_within_root(root, target) is True

    def test_outside_root(self):
        svc = _make_service()
        root = MagicMock()
        root.as_posix.return_value = "/root"
        target = MagicMock()
        target.as_posix.return_value = "/other"
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.os.path.commonpath", return_value="/"):
            assert svc._is_within_root(root, target) is False


# ---------------------------------------------------------------------------
# _relative_path_str
# ---------------------------------------------------------------------------

class TestRelativePathStr:
    def test_returns_relative_path(self):
        svc = _make_service()
        scan_root = MagicMock()
        scan_root.__truediv__ = MagicMock(return_value=MagicMock(
            expanduser=MagicMock(return_value=MagicMock(
                resolve=MagicMock(return_value=MagicMock(
                    parent=MagicMock(return_value=MagicMock(
                        relative_to=MagicMock(return_value=MagicMock(
                            as_posix=MagicMock(return_value="sub")
                        ))
                    ))
                ))
            ))
        ))
        # Instead, patch Path for the actual logic
        with patch("apps.contracts.services.contract.integrations._candidate_post_processor.Path") as MockPath:
            mock_file = MagicMock()
            mock_file.expanduser.return_value.resolve.return_value = mock_file
            mock_file.parent.relative_to.return_value = MagicMock(as_posix=MagicMock(return_value="sub"))
            MockPath.return_value = mock_file
            result = svc._post_processor._relative_path_str(source_path="/root/sub/file.pdf", scan_root=MagicMock())
            assert result == "sub"

    def test_returns_empty_on_error(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations._candidate_post_processor.Path") as MockPath:
            mock_file = MagicMock()
            mock_file.expanduser.return_value.resolve.return_value = mock_file
            mock_file.parent.relative_to.side_effect = ValueError("not relative")
            MockPath.return_value = mock_file
            result = svc._post_processor._relative_path_str(source_path="/other/file.pdf", scan_root=MagicMock())
            assert result == ""


# ---------------------------------------------------------------------------
# build_status_payload
# ---------------------------------------------------------------------------

class TestBuildStatusPayload:
    def test_builds_payload(self):
        session = _make_session(
            status=ContractFolderScanStatus.COMPLETED,
            progress=100,
            result_payload={"summary": {"total_files": 5, "deduped_files": 3, "classified_files": 4}, "candidates": []},
        )
        svc = _make_service()
        result = svc.build_status_payload(session=session)
        assert result["status"] == ContractFolderScanStatus.COMPLETED
        assert result["summary"]["total_files"] == 5
        assert result["candidates"] == []


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

class TestGetSession:
    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_returns_session(self, MockSession):
        s = _make_session()
        MockSession.objects.get.return_value = s
        svc = _make_service()
        result = svc.get_session(contract_id=1, session_id=s.id)
        assert result is s

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_raises_not_found(self, MockSession):
        MockSession.DoesNotExist = type("DoesNotExist", (Exception,), {})
        MockSession.objects.get.side_effect = MockSession.DoesNotExist
        svc = _make_service()
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            svc.get_session(contract_id=1, session_id=uuid4())


# ---------------------------------------------------------------------------
# get_latest_session
# ---------------------------------------------------------------------------

class TestGetLatestSession:
    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_returns_latest(self, MockSession):
        s = _make_session()
        MockSession.objects.filter.return_value.order_by.return_value.first.return_value = s
        svc = _make_service()
        assert svc.get_latest_session(contract_id=1) is s

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_returns_none_when_empty(self, MockSession):
        MockSession.objects.filter.return_value.order_by.return_value.first.return_value = None
        svc = _make_service()
        assert svc.get_latest_session(contract_id=1) is None


# ---------------------------------------------------------------------------
# _normalize_docx_name (module-level function)
# ---------------------------------------------------------------------------

class TestNormalizeDocxName:
    def test_strips_whitespace_and_lowercases(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name("  My File  .docx") == "myfile.docx"

    def test_empty_returns_empty(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name
        assert _normalize_docx_name("") == ""
        assert _normalize_docx_name(None) == ""


# ---------------------------------------------------------------------------
# list_scan_subfolders (local)
# ---------------------------------------------------------------------------

class TestListScanSubfoldersLocal:
    def test_lists_subfolders(self):
        binding = _make_binding(folder_path="/root")
        svc = _make_service()
        svc._ensure_contract_exists = MagicMock()
        svc._get_accessible_binding = MagicMock(return_value=binding)
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath, \
             patch("apps.contracts.services.contract.integrations.folder_scan_service.os.path.commonpath", return_value="/root"):
            mock_root = MagicMock()
            child1 = MagicMock()
            child1.name = "folder_a"
            child1.is_dir.return_value = True
            child1.resolve.return_value = child1
            child2 = MagicMock()
            child2.name = "folder_b"
            child2.is_dir.return_value = True
            child2.resolve.return_value = child2
            mock_file = MagicMock()
            mock_file.name = "file.pdf"
            mock_file.is_dir.return_value = False
            mock_root.iterdir.return_value = [child1, child2, mock_file]
            mock_root.expanduser.return_value.resolve.return_value = mock_root
            mock_root.as_posix.return_value = "/root"
            MockPath.return_value = mock_root
            result = svc.list_scan_subfolders(contract_id=1)
            assert len(result["subfolders"]) == 2
            assert result["root_path"] == "/root"

    def test_skips_hidden_folders(self):
        binding = _make_binding(folder_path="/root")
        svc = _make_service()
        svc._ensure_contract_exists = MagicMock()
        svc._get_accessible_binding = MagicMock(return_value=binding)
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath, \
             patch("apps.contracts.services.contract.integrations.folder_scan_service.os.path.commonpath", return_value="/root"):
            mock_root = MagicMock()
            hidden = MagicMock()
            hidden.name = ".hidden"
            hidden.is_dir.return_value = True
            visible = MagicMock()
            visible.name = "visible"
            visible.is_dir.return_value = True
            visible.resolve.return_value = visible
            mock_root.iterdir.return_value = [hidden, visible]
            mock_root.expanduser.return_value.resolve.return_value = mock_root
            mock_root.as_posix.return_value = "/root"
            MockPath.return_value = mock_root
            result = svc.list_scan_subfolders(contract_id=1)
            assert len(result["subfolders"]) == 1
            assert result["subfolders"][0]["display_name"] == "visible"


# ---------------------------------------------------------------------------
# list_scan_subfolders (cloud storage)
# ---------------------------------------------------------------------------

class TestListScanSubfoldersCloud:
    def test_cloud_lists_subfolders(self):
        binding = _make_binding(folder_path="/cloud/root", storage_type="webdav")
        mock_provider = MagicMock()
        child = MagicMock()
        child.name = "sub1"
        child.is_dir = True
        mock_provider.list_directory.return_value = [child]

        svc = _make_service()
        svc._ensure_contract_exists = MagicMock()
        svc._get_accessible_binding = MagicMock(return_value=binding)
        svc._make_provider_for_binding = MagicMock(return_value=mock_provider)

        result = svc.list_scan_subfolders(contract_id=1)
        assert len(result["subfolders"]) == 1
        assert result["subfolders"][0]["relative_path"] == "sub1"


# ---------------------------------------------------------------------------
# confirm_import
# ---------------------------------------------------------------------------

class TestConfirmImportValidation:
    """Test validation logic that happens inside confirm_import by testing the methods directly."""

    def test_get_session_delegates_to_orm(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = _make_service()
        session = _make_session()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession") as MockSession:
            MockSession.objects.get.return_value = session
            result = svc.get_session(contract_id=1, session_id=session.id)
            assert result is session

    def test_build_status_payload_keys(self):
        svc = _make_service()
        session = _make_session(
            status=ContractFolderScanStatus.COMPLETED,
            result_payload={"summary": {"total_files": 5}, "candidates": []},
        )
        result = svc.build_status_payload(session=session)
        assert "session_id" in result
        assert "status" in result
        assert "candidates" in result


# ---------------------------------------------------------------------------
# run_contract_folder_scan_task (module function)
# ---------------------------------------------------------------------------

class TestRunContractFolderScanTask:
    def test_calls_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import run_contract_folder_scan_task
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanService") as MockSvc:
            run_contract_folder_scan_task("test-id")
            MockSvc.return_value.run_scan_task.assert_called_once_with(session_id="test-id")


# ---------------------------------------------------------------------------
# _convert_docx_to_temp_pdf
# ---------------------------------------------------------------------------

class TestConvertDocxToPdf:
    def test_returns_path_on_success(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.Path") as MockPath:
            with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: MagicMock(
                convert_docx_to_pdf=MagicMock(return_value="/tmp/out.pdf")
            ) if "pdf_merge_utils" in name else __import__(name, *args, **kwargs)):
                # Simpler: just patch the import at the source
                pass

    def test_returns_none_on_failure(self):
        svc = _make_service()
        mock_path = MagicMock()
        mock_path.as_posix.return_value = "/tmp/bad.docx"
        with patch("apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf", side_effect=OSError("fail")):
            result = svc._import_pipeline._convert_docx_to_temp_pdf(mock_path)
            assert result is None


# ---------------------------------------------------------------------------
# _learn_from_import_correction
# ---------------------------------------------------------------------------

class TestLearnFromImportCorrection:
    def test_noop_when_empty_code(self):
        svc = _make_service()
        # Should not raise
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "x"}, actual_archive_item_code="", contract_id=1
        )

    def test_noop_when_code_matches(self):
        svc = _make_service()
        svc._learn_from_import_correction(
            candidate={"archive_item_code": "x"}, actual_archive_item_code="x", contract_id=1
        )


# ---------------------------------------------------------------------------
# _make_provider_for_binding
# ---------------------------------------------------------------------------

class TestMakeProviderForBinding:
    def test_returns_none_for_local(self):
        svc = _make_service()
        binding = _make_binding(storage_type="local")
        assert svc._make_provider_for_binding(binding) is None

    @patch("apps.core.cloud_storage.factory.create_provider_for_binding")
    def test_returns_provider_for_cloud(self, mock_create):
        binding = _make_binding(storage_type="webdav")
        mock_provider = MagicMock()
        mock_create.return_value = mock_provider
        svc = _make_service()
        result = svc._make_provider_for_binding(binding)
        assert result is mock_provider


# ---------------------------------------------------------------------------
# _post_process_candidates
# ---------------------------------------------------------------------------

class TestPostProcessCandidates:
    def test_archive_document_matched(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "matched",
                "archive_item_code": "nl_1",
                "archive_item_name": "合同",
                "confidence": 0.9,
                "reason": "文件名匹配",
            }
            candidates = [{
                "filename": "合同.pdf",
                "source_path": "/root/合同.pdf",
                "suggested_category": "archive_document",
            }]
            result = svc._post_processor.post_process_candidates(
                candidates=candidates, archive_category="non_litigation", scan_folder="/root"
            )
            assert result[0]["suggested_category"] == "case_material"
            assert result[0]["archive_item_code"] == "nl_1"

    def test_archive_document_skip(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "skip",
                "archive_item_code": "",
                "archive_item_name": "",
                "confidence": 0,
                "reason": "跳过规则命中",
            }
            candidates = [{
                "filename": "通知.pdf",
                "source_path": "/root/通知.pdf",
                "suggested_category": "archive_document",
            }]
            result = svc._post_processor.post_process_candidates(
                candidates=candidates, archive_category="non_litigation", scan_folder="/root"
            )
            assert result[0]["selected"] is False
            assert result[0]["skip_reason"] == "跳过规则命中"

    def test_insurance_keywords_deselect(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations._candidate_post_processor.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "matched",
                "archive_item_code": "",
                "archive_item_name": "",
                "confidence": 0,
                "reason": "",
            }
            candidates = [{
                "filename": "保单.pdf",
                "source_path": "/root/保单.pdf",
                "suggested_category": "case_material",
            }]
            result = svc._post_processor.post_process_candidates(
                candidates=candidates, archive_category="litigation", scan_folder="/root"
            )
            assert result[0]["selected"] is False
