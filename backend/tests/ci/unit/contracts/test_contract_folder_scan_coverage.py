"""contracts.services.contract.integrations.folder_scan_service 补充覆盖测试。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException

# ── _normalize_scan_subfolder ─────────────────────────────────────


class TestNormalizeScanSubfolder:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    def test_empty_returns_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("") == ""

    def test_slash_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/")

    def test_dot_only_returns_empty(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder(".") == ""

    def test_relative_path(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_nested_relative_path(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("a/b/c") == "a/b/c"

    def test_absolute_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("/absolute/path")

    def test_home_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("~/documents")

    def test_windows_path_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._normalize_scan_subfolder("C:/Users/test")

    def test_dotdot_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="非法"):
            svc._normalize_scan_subfolder("../etc/passwd")

    def test_middle_dotdot_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="非法"):
            svc._normalize_scan_subfolder("sub/../../../etc")

    def test_backslash_normalized(self):
        svc = self._make_service()
        assert svc._normalize_scan_subfolder("sub\\folder") == "sub/folder"


# ── _is_within_root ───────────────────────────────────────────────


class TestIsWithinRoot:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    def test_within_root(self):
        svc = self._make_service()
        root = Path("/home/user/projects")
        target = Path("/home/user/projects/subfolder")
        assert svc._is_within_root(root, target) is True

    def test_outside_root(self):
        svc = self._make_service()
        root = Path("/home/user/projects")
        target = Path("/home/other/projects")
        assert svc._is_within_root(root, target) is False

    def test_same_path(self):
        svc = self._make_service()
        root = Path("/home/user/projects")
        assert svc._is_within_root(root, root) is True


# ── _extract_scan_subfolder ───────────────────────────────────────


class TestExtractScanSubfolder:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    def test_none_payload(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder(None) == ""

    def test_empty_payload(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({}) == ""

    def test_with_scan_scope(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({"scan_scope": {"scan_subfolder": "sub"}}) == "sub"

    def test_whitespace_stripped(self):
        svc = self._make_service()
        assert svc._extract_scan_subfolder({"scan_scope": {"scan_subfolder": "  sub  "}}) == "sub"


# ── _ensure_contract_exists ───────────────────────────────────────


class TestEnsureContractExists:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_exists(self, mock_contract):
        svc = self._make_service()
        mock_contract.objects.filter.return_value.exists.return_value = True
        # 合同存在时静默通过（返回 None）
        assert svc._ensure_contract_exists(1) is None

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_not_found(self, mock_contract):
        svc = self._make_service()
        mock_contract.objects.filter.return_value.exists.return_value = False
        with pytest.raises(NotFoundError):
            svc._ensure_contract_exists(999)


# ── _relative_path_str ────────────────────────────────────────────


class TestRelativePathStr:
    def _make_service(self):
        from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor

        return CandidatePostProcessor(scan_service=MagicMock())

    def test_unresolvable_path(self):
        svc = self._make_service()
        result = svc._relative_path_str(
            source_path="/completely/different/path/file.pdf",
            scan_root=Path("/home/user/projects"),
        )
        # If ValueError or RuntimeError, returns ""
        assert isinstance(result, str)


# ── build_status_payload ──────────────────────────────────────────


class TestBuildStatusPayload:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    def test_basic_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = "session-1"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 10, "deduped_files": 8, "classified_files": 7},
            "candidates": [{"filename": "test.pdf"}],
            "archive_category": "litigation",
            "archive_item_options": [],
            "work_log_suggestions": [],
        }

        payload = svc.build_status_payload(session=session)
        assert payload["session_id"] == "session-1"
        assert payload["status"] == "completed"
        assert payload["summary"]["total_files"] == 10
        assert len(payload["candidates"]) == 1

    def test_empty_payload(self):
        svc = self._make_service()
        session = MagicMock()
        session.id = "session-2"
        session.status = "pending"
        session.progress = 0
        session.current_file = ""
        session.error_message = ""
        session.result_payload = None

        payload = svc.build_status_payload(session=session)
        assert payload["summary"]["total_files"] == 0


# ── _resolve_scan_scope ───────────────────────────────────────────


class TestResolveScanScope:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    def test_empty_subfolder(self):
        svc = self._make_service()
        result = svc._resolve_scan_scope("/home/user/projects", "")
        assert result["root_folder"] != ""
        assert result["scan_subfolder"] == ""

    def test_cloud_empty_subfolder(self):
        svc = self._make_service()
        provider = MagicMock()
        result = svc._resolve_scan_scope("/bucket/root", "", storage_provider=provider)
        assert result["root_folder"] == "/bucket/root"
        assert result["scan_subfolder"] == ""

    def test_cloud_with_subfolder(self):
        svc = self._make_service()
        provider = MagicMock()
        provider.exists.return_value = True
        result = svc._resolve_scan_scope("/bucket/root", "sub", storage_provider=provider)
        assert result["scan_subfolder"] == "sub"

    def test_cloud_subfolder_not_exists_raises(self):
        svc = self._make_service()
        provider = MagicMock()
        # 判不可访问需 is_dir()（PROPFIND）与 exists() 兜底都为 False，
        # 坚果云 HEAD 对目录 403 时 is_dir() 仍可命中
        provider.is_dir.return_value = False
        provider.exists.return_value = False
        with pytest.raises(ValidationException, match="不可访问"):
            svc._resolve_scan_scope("/bucket/root", "nonexistent", storage_provider=provider)

    def test_cloud_traversal_raises(self):
        svc = self._make_service()
        provider = MagicMock()
        with pytest.raises(ValidationException):
            svc._resolve_scan_scope("/bucket/root", "../escape", storage_provider=provider)


# ── _get_accessible_binding ───────────────────────────────────────


class TestGetAccessibleBinding:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderBinding")
    def test_no_binding_raises(self, mock_binding):
        svc = self._make_service()
        mock_binding.objects.filter.return_value.first.return_value = None
        with pytest.raises(ValidationException, match="未绑定"):
            svc._get_accessible_binding(1)


# ── _make_provider_for_binding ────────────────────────────────────


class TestMakeProviderForBinding:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    def test_local_returns_none(self):
        svc = self._make_service()
        binding = MagicMock()
        binding.storage_type = "local"
        assert svc._make_provider_for_binding(binding) is None

    @patch("apps.cloud_storage.factory.create_provider_for_binding")
    def test_cloud_returns_provider(self, mock_create):
        svc = self._make_service()
        binding = MagicMock()
        binding.storage_type = "oss"
        provider = MagicMock()
        mock_create.return_value = provider
        result = svc._make_provider_for_binding(binding)
        assert result is provider


# ── get_session / get_latest_session ──────────────────────────────


class TestGetSession:
    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        return ContractFolderScanService()

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_not_found_raises(self, mock_session):
        import uuid

        svc = self._make_service()
        mock_session.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_session.objects.get.side_effect = mock_session.DoesNotExist
        with pytest.raises(NotFoundError):
            svc.get_session(contract_id=1, session_id=uuid.uuid4())

    @patch("apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession")
    def test_get_latest_session_none(self, mock_session):
        svc = self._make_service()
        mock_session.objects.filter.return_value.order_by.return_value.first.return_value = None
        assert svc.get_latest_session(contract_id=1) is None


# ── _normalize_docx_name (module-level) ───────────────────────────


class TestNormalizeDocxName:
    def test_strips_whitespace(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name

        assert _normalize_docx_name("  hello  world  ") == "helloworld"

    def test_lowercase(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name

        assert _normalize_docx_name("TEST.DOCX") == "test.docx"

    def test_empty(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name

        assert _normalize_docx_name("") == ""

    def test_none(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import _normalize_docx_name

        assert _normalize_docx_name(None) == ""  # type: ignore[arg-type]


# ── _QUALITY_CARD_TITLE constant ──────────────────────────────────


class TestConstants:
    def test_quality_card_title(self):
        from apps.contracts.services.contract.integrations._import_pipeline import ImportPipeline

        assert "监督卡" in ImportPipeline._QUALITY_CARD_TITLE

    def test_active_statuses(self):
        from apps.contracts.models import ContractFolderScanStatus
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        assert ContractFolderScanStatus.PENDING in ContractFolderScanService._ACTIVE_STATUSES
        assert ContractFolderScanStatus.RUNNING in ContractFolderScanService._ACTIVE_STATUSES
        assert ContractFolderScanStatus.CLASSIFYING in ContractFolderScanService._ACTIVE_STATUSES


# ── run_contract_folder_scan_task ──────────────────────────────────


class TestRunContractFolderScanTask:
    def test_delegates_to_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import run_contract_folder_scan_task

        with patch(
            "apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanService"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            run_contract_folder_scan_task("session-id-123")
            mock_instance.run_scan_task.assert_called_once_with(session_id="session-id-123")


# ── run_scan_task 进度竞态 ─────────────────────────────────────────
# 回归：文件遍历结束的 "completed" 进度回调不得提前把会话置 COMPLETED，
# 否则轮询端停止轮询拿到空 payload，误报「未找到可导入的文件」


class TestRunScanTaskNoPrematureCompleted:
    def _run(self, updates: list[dict[str, Any]]) -> None:
        from apps.contracts.models import ContractFolderScanStatus
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService

        session = MagicMock()
        session.id = "sess-1"
        session.contract_id = 8
        session.result_payload = {"scan_scope": {"scan_subfolder": ""}}
        session.contract = MagicMock(case_type="civil_litigation")

        svc = ContractFolderScanService()

        def fake_scan_folder(**kwargs: Any) -> dict[str, Any]:
            progress_callback = kwargs["progress_callback"]
            progress_callback("scanning", 5, None)
            progress_callback("extracting", 40, "a.pdf")
            progress_callback("completed", 100, None)
            return {
                "candidates": [],
                "summary": {"total_files": 2, "deduped_files": 2, "classified_files": 2},
            }

        scan_service = MagicMock()
        scan_service.scan_folder.side_effect = fake_scan_folder
        svc._scan_service = scan_service
        svc._post_processor = MagicMock()
        svc._post_processor.post_process_candidates.return_value = [{"filename": "a.pdf", "source_path": "/tmp/a.pdf"}]
        svc._get_accessible_binding = MagicMock(return_value=MagicMock())
        svc._make_provider_for_binding = MagicMock(return_value=None)
        svc._resolve_scan_scope = MagicMock(return_value={"scan_folder": "/tmp/x", "scan_subfolder": ""})

        with (
            patch(
                "apps.contracts.services.contract.integrations.folder_scan_service.ContractFolderScanSession"
            ) as mock_session_model,
            patch(
                "apps.contracts.services.contract.integrations.folder_scan_service.get_archive_category",
                return_value="litigation",
            ),
            patch(
                "apps.contracts.services.contract.integrations.folder_scan_service.collect_work_log_suggestions",
                return_value=[],
            ),
            patch(
                "apps.contracts.services.contract.integrations.folder_scan_service.extract_case_info_from_candidates",
                return_value=[],
            ),
            patch(
                "apps.contracts.services.contract.integrations.folder_scan_service.collect_archive_item_options",
                return_value=[],
            ),
        ):
            mock_session_model.objects.select_related.return_value.filter.return_value.first.return_value = session
            mock_session_model.objects.filter.return_value.update.side_effect = lambda **kw: updates.append(kw) or 1
            svc.run_scan_task(session_id="sess-1")

    def test_file_walk_completed_keeps_running(self) -> None:
        from apps.contracts.models import ContractFolderScanStatus

        updates: list[dict[str, Any]] = []
        self._run(updates)

        walk_end = [u for u in updates if u.get("progress") == 99]
        assert walk_end, "文件遍历结束应写入 99% 进度"
        assert walk_end[0].get("status") == ContractFolderScanStatus.RUNNING

    def test_completed_only_written_with_payload(self) -> None:
        from apps.contracts.models import ContractFolderScanStatus

        updates: list[dict[str, Any]] = []
        self._run(updates)

        completed_updates = [u for u in updates if u.get("status") == ContractFolderScanStatus.COMPLETED]
        assert len(completed_updates) == 1, "COMPLETED 只能由最终原子落库写入一次"
        payload = completed_updates[0].get("result_payload") or {}
        assert payload.get("candidates") == [{"filename": "a.pdf", "source_path": "/tmp/a.pdf"}]
