"""Long-tail coverage tests for automation, filesystem, and other modules."""
from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# tests for apps.core.llm.fallback_policy (30 missing)
# ---------------------------------------------------------------------------


class TestLLMFallbackPolicy:
    def _make_backend(self, available=True, base_url="http://x", api_key="k", model="m"):
        b = MagicMock()
        b.is_available.return_value = available
        type(b).base_url = PropertyMock(return_value=base_url)
        type(b).api_key = PropertyMock(return_value=api_key)
        type(b).default_model = PropertyMock(return_value=model)
        return b

    def _make_router(self, backends: list[tuple[str, Any]]):
        router = MagicMock()
        router.get_backends_by_priority.return_value = backends
        router.get_backend.side_effect = lambda name: dict(backends)[name]
        return router

    def test_execute_direct_backend(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b = self._make_backend()
        router = self._make_router([("openai_compatible", b)])
        policy = LLMFallbackPolicy(router=router)

        result = policy.execute(operation=lambda b: "ok", backend="openai_compatible", fallback=False)
        assert result == "ok"

    def test_execute_fallback_first_success(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b = self._make_backend()
        router = self._make_router([("openai_compatible", b)])
        policy = LLMFallbackPolicy(router=router)

        result = policy.execute(operation=lambda b: "ok")
        assert result == "ok"

    def test_execute_all_unavailable(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        b1 = self._make_backend(available=False, api_key="")
        b2 = self._make_backend(available=False, base_url="")
        router = self._make_router([("b1", b1), ("b2", b2)])
        policy = LLMFallbackPolicy(router=router)

        with pytest.raises(LLMBackendUnavailableError):
            policy.execute(operation=lambda b: "ok")

    def test_execute_auth_error_raises_immediately(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMAuthenticationError

        b = self._make_backend()
        b.side_effect = None
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        with pytest.raises(LLMAuthenticationError):
            policy.execute(operation=lambda b: (_ for _ in ()).throw(LLMAuthenticationError()))

    def test_execute_retriable_with_fallback(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMTimeoutError

        b1 = self._make_backend()
        b2 = self._make_backend()
        router = self._make_router([("b1", b1), ("b2", b2)])
        policy = LLMFallbackPolicy(router=router)

        call_count = 0

        def op(backend):
            nonlocal call_count
            call_count += 1
            if backend is b1:
                raise LLMTimeoutError(timeout_seconds=10)
            return "ok"

        result = policy.execute(operation=op)
        assert result == "ok"
        assert call_count == 2

    def test_execute_retriable_no_fallback_raises(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMTimeoutError

        b = self._make_backend()
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        with pytest.raises(LLMTimeoutError):
            policy.execute(operation=lambda b: (_ for _ in ()).throw(LLMTimeoutError(timeout_seconds=10)), fallback=False)

    def test_execute_unknown_error_no_fallback_wraps(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMAPIError

        b = self._make_backend()
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        with pytest.raises(LLMAPIError):
            policy.execute(operation=lambda b: (_ for _ in ()).throw(RuntimeError("boom")), fallback=False)

    def test_execute_unknown_error_with_fallback_continues(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        b1 = self._make_backend()
        b2 = self._make_backend(available=False, api_key="")
        router = self._make_router([("b1", b1), ("b2", b2)])
        policy = LLMFallbackPolicy(router=router)

        with pytest.raises(LLMBackendUnavailableError):
            policy.execute(operation=lambda b: (_ for _ in ()).throw(RuntimeError("boom")))

    @pytest.mark.asyncio
    async def test_execute_async_success(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b = self._make_backend()
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        async def op(backend):
            return "async_ok"

        result = await policy.execute_async(operation=op)
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_execute_async_direct(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b = self._make_backend()
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        async def op(backend):
            return "direct"

        result = await policy.execute_async(operation=op, backend="b1", fallback=False)
        assert result == "direct"

    @pytest.mark.asyncio
    async def test_execute_async_all_unavailable(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMBackendUnavailableError

        b = self._make_backend(available=False, api_key="")
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        async def op(backend):
            return "never"

        with pytest.raises(LLMBackendUnavailableError):
            await policy.execute_async(operation=op)

    @pytest.mark.asyncio
    async def test_execute_async_auth_error(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy
        from apps.core.llm.exceptions import LLMAuthenticationError

        b = self._make_backend()
        router = self._make_router([("b1", b)])
        policy = LLMFallbackPolicy(router=router)

        async def op(backend):
            raise LLMAuthenticationError()

        with pytest.raises(LLMAuthenticationError):
            await policy.execute_async(operation=op)


# ---------------------------------------------------------------------------
# tests for apps.automation.services.chat.owner_config_manager (48 missing)
# ---------------------------------------------------------------------------


class TestOwnerConfigManager:
    def _make_manager(self, **config_overrides):
        from apps.automation.services.chat.owner_config_manager import OwnerConfigManager

        with patch.object(OwnerConfigManager, "_load_config", return_value={
            "TEST_MODE": False,
            "OWNER_VALIDATION_ENABLED": True,
            "OWNER_RETRY_ENABLED": True,
            "OWNER_MAX_RETRIES": 3,
            "DEFAULT_OWNER_ID": None,
            "TEST_OWNER_ID": None,
            "TIMEOUT": 30,
            **config_overrides,
        }):
            return OwnerConfigManager()

    def test_validate_owner_id_valid_open_id(self):
        m = self._make_manager()
        hex32 = "a" * 32
        assert m.validate_owner_id(f"ou_{hex32}") is True

    def test_validate_owner_id_valid_union_id(self):
        m = self._make_manager()
        hex32 = "b" * 32
        assert m.validate_owner_id(f"on_{hex32}") is True

    def test_validate_owner_id_invalid(self):
        m = self._make_manager()
        assert m.validate_owner_id("bad_id") is False
        assert m.validate_owner_id("") is False
        assert m.validate_owner_id(None) is False
        assert m.validate_owner_id("ou_short") is False

    def test_validate_owner_id_strict_raises(self):
        from apps.core.exceptions import ValidationException

        m = self._make_manager()
        with pytest.raises(ValidationException):
            m.validate_owner_id_strict("invalid")

    def test_validate_owner_id_strict_valid(self):
        m = self._make_manager()
        hex32 = "c" * 32
        m.validate_owner_id_strict(f"ou_{hex32}")  # no raise

    def test_get_effective_owner_specified_valid(self):
        m = self._make_manager()
        hex32 = "d" * 32
        result = m.get_effective_owner_id(f"ou_{hex32}")
        assert result == f"ou_{hex32}"

    def test_get_effective_owner_specified_invalid_fallback(self):
        m = self._make_manager(DEFAULT_OWNER_ID="ou_" + "e" * 32)
        result = m.get_effective_owner_id("bad")
        assert result == "ou_" + "e" * 32

    def test_get_effective_owner_no_validation(self):
        m = self._make_manager(OWNER_VALIDATION_ENABLED=False)
        result = m.get_effective_owner_id("anything")
        assert result == "anything"

    def test_get_effective_owner_none(self):
        m = self._make_manager()
        result = m.get_effective_owner_id(None)
        assert result is None

    def test_get_default_owner_id_from_config(self):
        m = self._make_manager(DEFAULT_OWNER_ID="ou_" + "f" * 32)
        assert m.get_default_owner_id() == "ou_" + "f" * 32

    def test_get_default_owner_id_test_env(self):
        m = self._make_manager(TEST_MODE=True, TEST_OWNER_ID="ou_" + "a" * 32)
        assert m.get_default_owner_id() == "ou_" + "a" * 32

    def test_get_default_owner_id_none(self):
        m = self._make_manager()
        assert m.get_default_owner_id() is None

    def test_handle_empty_owner_id_none(self):
        m = self._make_manager(DEFAULT_OWNER_ID="ou_" + "b" * 32)
        assert m.handle_empty_owner_id(None) == "ou_" + "b" * 32

    def test_handle_empty_owner_id_empty_str(self):
        m = self._make_manager(DEFAULT_OWNER_ID="ou_" + "c" * 32)
        assert m.handle_empty_owner_id("") == "ou_" + "c" * 32

    def test_handle_empty_owner_id_whitespace(self):
        m = self._make_manager()
        assert m.handle_empty_owner_id("   ") is None

    def test_handle_empty_owner_id_valid(self):
        m = self._make_manager()
        assert m.handle_empty_owner_id("ou_" + "d" * 32) == "ou_" + "d" * 32

    def test_is_test_environment(self):
        m = self._make_manager(TEST_MODE=True)
        assert m.is_test_environment() is True

    def test_is_validation_enabled(self):
        m = self._make_manager(OWNER_VALIDATION_ENABLED=False)
        assert m.is_validation_enabled() is False

    def test_is_retry_enabled(self):
        m = self._make_manager(OWNER_RETRY_ENABLED=False)
        assert m.is_retry_enabled() is False

    def test_get_max_retries(self):
        m = self._make_manager(OWNER_MAX_RETRIES=5)
        assert m.get_max_retries() == 5

    def test_get_config_summary(self):
        m = self._make_manager(DEFAULT_OWNER_ID="ou_" + "e" * 32)
        summary = m.get_config_summary()
        assert summary["has_default_owner"] is True
        assert summary["default_owner_id_prefix"] == "ou_"

    def test_get_config_summary_no_owner(self):
        m = self._make_manager()
        summary = m.get_config_summary()
        assert summary["has_default_owner"] is False
        assert summary["default_owner_id_prefix"] is None


# ---------------------------------------------------------------------------
# tests for apps.core.filesystem.browse_policy (50 missing)
# ---------------------------------------------------------------------------


class TestFolderBrowsePolicy:
    def _make_policy(self, roots=None, fallback=None):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        return FolderBrowsePolicy(
            roots_setting_name=roots or "FOLDER_BROWSE_ROOTS",
            fallback_roots_setting_name=fallback,
        )

    def test_get_browse_roots_downloads(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        dl = tmp_path / "Downloads"
        dl.mkdir()
        with patch("apps.core.filesystem.browse_policy.settings") as mock_settings:
            mock_settings.FOLDER_BROWSE_ROOTS = []
            with patch("apps.core.filesystem.browse_policy.Path") as MockPath:
                mock_dl = MagicMock()
                mock_dl.expanduser.return_value = mock_dl
                mock_dl.isdir.return_value = True
                MockPath.return_value = mock_dl
                MockPath.__truediv__ = lambda self, other: mock_dl

                policy = self._make_policy()
                roots = policy.get_browse_roots()
                assert len(roots) >= 1

    def test_resolve_under_allowed_roots_network_path(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy
        from apps.core.exceptions import ValidationException

        validator = MagicMock()
        validator.is_network_path.return_value = True
        policy = FolderBrowsePolicy(validator=validator)
        with pytest.raises(ValidationException, match="网络路径"):
            policy.resolve_under_allowed_roots("//server/share")

    def test_resolve_under_allowed_roots_no_roots(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy
        from apps.core.exceptions import ValidationException

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)
        with patch.object(policy, "get_browse_roots", return_value=[]):
            with pytest.raises(ValidationException, match="未配置"):
                policy.resolve_under_allowed_roots("/some/path")

    def test_resolve_under_allowed_roots_not_dir(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy
        from apps.core.exceptions import ValidationException

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)
        with patch.object(policy, "get_browse_roots", return_value=[MagicMock()]):
            with patch("apps.core.filesystem.browse_policy.Path") as MockPath:
                mock_target = MagicMock()
                mock_target.isdir.return_value = False
                MockPath.return_value = mock_target
                with pytest.raises(ValidationException, match="目标不是文件夹"):
                    policy.resolve_under_allowed_roots("/some/path")

    def test_resolve_under_allowed_roots_not_under_root(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy
        from apps.core.exceptions import ValidationException

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)

        root = MagicMock()
        root.__truediv__ = MagicMock()
        with patch.object(policy, "get_browse_roots", return_value=[root]):
            with patch("apps.core.filesystem.browse_policy.Path") as MockPath:
                mock_target = MagicMock()
                mock_target.isdir.return_value = True
                mock_target.relative_to.side_effect = ValueError
                mock_target.expanduser.return_value = mock_target
                mock_target.resolve.return_value = mock_target
                MockPath.return_value = mock_target
                with pytest.raises(ValidationException, match="目标路径不在允许范围内"):
                    policy.resolve_under_allowed_roots("/forbidden/path")

    def test_resolve_under_allowed_roots_success(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        target_dir = tmp_path / "allowed"
        target_dir.mkdir()

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)
        with patch.object(policy, "get_browse_roots", return_value=[tmp_path]):
            result = policy.resolve_under_allowed_roots(str(target_dir))
            assert result is not None

    def test_list_subdirs_with_hidden(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)
        with patch.object(policy, "get_browse_roots", return_value=[tmp_path]):
            all_dirs = policy.list_subdirs(str(tmp_path), include_hidden=True)
            names = [d["name"] for d in all_dirs]
            assert ".hidden" in names
            assert "visible" in names

    def test_list_subdirs_exclude_hidden(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)
        with patch.object(policy, "get_browse_roots", return_value=[tmp_path]):
            visible_dirs = policy.list_subdirs(str(tmp_path), include_hidden=False)
            names = [d["name"] for d in visible_dirs]
            assert ".hidden" not in names
            assert "visible" in names

    def test_list_subdirs_permission_error(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy
        from apps.core.exceptions import ValidationException

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)

        with patch.object(policy, "resolve_under_allowed_roots") as mock_resolve:
            mock_target = MagicMock()
            mock_target.iterdir.side_effect = PermissionError("no access")
            mock_resolve.return_value = mock_target
            with pytest.raises(ValidationException, match="无权限"):
                policy.list_subdirs("/some/path")

    def test_list_subdirs_child_oserror(self, tmp_path):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        validator = MagicMock()
        validator.is_network_path.return_value = False
        policy = FolderBrowsePolicy(validator=validator)

        bad_child = MagicMock()
        bad_child.isdir.side_effect = OSError("bad")
        good_child = MagicMock()
        good_child.isdir.return_value = True
        good_child.name = "good"

        with patch.object(policy, "resolve_under_allowed_roots") as mock_resolve:
            mock_target = MagicMock()
            mock_target.iterdir.return_value = [bad_child, good_child]
            mock_resolve.return_value = mock_target
            result = policy.list_subdirs("/some/path")
            assert len(result) == 1
            assert result[0]["name"] == "good"

    def test_get_user_downloads_path_oserror(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = self._make_policy()
        with patch("apps.core.filesystem.browse_policy.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.expanduser.side_effect = OSError("no home")
            MockPath.return_value = mock_path
            result = policy._get_user_downloads_path()
            assert result is None

    def test_get_user_downloads_path_not_dir(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = self._make_policy()
        with patch("apps.core.filesystem.browse_policy.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.expanduser.return_value = mock_path
            mock_path.isdir.return_value = False
            MockPath.return_value = mock_path
            result = policy._get_user_downloads_path()
            assert result is None


# ---------------------------------------------------------------------------
# tests for apps.documents.services.infrastructure.pdf_merge_service (49 missing)
# ---------------------------------------------------------------------------


class TestPDFMergeValidator:
    def test_get_items_empty_raises(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        from apps.core.exceptions import ValidationException

        validator = PDFMergeValidator()
        evidence_list = MagicMock()
        evidence_list.items.filter.return_value.exclude.return_value.order_by.return_value.exists.return_value = False
        evidence_list.pk = 1
        with pytest.raises(ValidationException, match="没有任何文件"):
            validator.get_items(evidence_list)

    def test_assert_supported_format_valid(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator

        validator = PDFMergeValidator()
        validator.assert_supported_format(".pdf", "/test.pdf")  # no raise

    def test_assert_supported_format_invalid(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeValidator
        from apps.core.exceptions import BusinessException

        validator = PDFMergeValidator()
        with pytest.raises(BusinessException, match="不支持"):
            validator.assert_supported_format(".xyz", "/test.xyz")


class TestPDFMergeWorkflow:
    def test_validator_lazy_init(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        workflow = PDFMergeWorkflow()
        assert workflow.validator is not None

    def test_validator_provided(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow, PDFMergeValidator

        v = PDFMergeValidator()
        workflow = PDFMergeWorkflow(validator=v)
        assert workflow.validator is v

    def test_generate_merged_filename_evidence_list(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        workflow = PDFMergeWorkflow()
        el = MagicMock()
        el.case.name = "张三诉李四"
        el.title = "证据清单"
        el.export_version = 1

        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20240101"
            result = workflow._generate_merged_filename(el)
            assert "证据明细" in result
            assert "张三诉李四" in result
            assert "V1" in result

    def test_generate_merged_filename_supplementary(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        workflow = PDFMergeWorkflow()
        el = MagicMock()
        el.case.name = "案件"
        el.title = "补充证据清单A"
        el.export_version = 2

        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20240101"
            result = workflow._generate_merged_filename(el)
            assert "A" in result

    def test_generate_merged_filename_other_title(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeWorkflow

        workflow = PDFMergeWorkflow()
        el = MagicMock()
        el.case.name = "案件"
        el.title = "其他证据"
        el.export_version = 3

        with patch("apps.documents.services.infrastructure.pdf_merge_service.timezone") as mock_tz:
            mock_tz.now.return_value.strftime.return_value = "20240101"
            result = workflow._generate_merged_filename(el)
            # "其他证据" doesn't start with 证据清单 or 补充证据清单, so list_suffix is empty
            assert "证据明细(" in result


class TestPDFMergeService:
    def test_workflow_lazy_init(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        assert svc.workflow is not None

    def test_workflow_provided(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService, PDFMergeWorkflow

        w = PDFMergeWorkflow()
        svc = PDFMergeService(workflow=w)
        assert svc.workflow is w

    def test_add_page_numbers(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        with patch("apps.documents.services.infrastructure.pdf_merge_service.add_page_numbers_util", return_value=b"pdf"):
            result = svc.add_page_numbers(io.BytesIO(b"test"), start_page=1)
            assert result == b"pdf"

    def test_convert_to_pdf(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        with patch.object(svc.workflow, "convert_to_pdf", return_value="/out.pdf"):
            assert svc.convert_to_pdf("/in.docx") == "/out.pdf"

    def test_get_pdf_page_count(self):
        from apps.documents.services.infrastructure.pdf_merge_service import PDFMergeService

        svc = PDFMergeService()
        with patch.object(svc.workflow, "get_pdf_page_count", return_value=5):
            assert svc.get_pdf_page_count(io.BytesIO(b"test")) == 5


# ---------------------------------------------------------------------------
# tests for apps.evidence_sorting.services.exporter (45 missing)
# ---------------------------------------------------------------------------


class TestExporterService:
    def _make_exporter(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        return ExporterService()

    def test_get_ext_with_dot(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        assert ExporterService._get_ext("file.jpg") == ".jpg"
        assert ExporterService._get_ext("file.tar.gz") == ".gz"

    def test_get_ext_no_dot(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        assert ExporterService._get_ext("noext") == ".jpg"

    def test_write_image_normal(self):
        import base64

        from apps.evidence_sorting.services.exporter import ExporterService

        zf = MagicMock()
        data = base64.b64encode(b"image_data").decode()
        ExporterService._write_image(zf, "test.jpg", data)
        zf.writestr.assert_called_once_with("test.jpg", b"image_data")

    def test_write_image_with_data_url_prefix(self):
        import base64

        from apps.evidence_sorting.services.exporter import ExporterService

        zf = MagicMock()
        data = "data:image/jpeg;base64," + base64.b64encode(b"image_data").decode()
        ExporterService._write_image(zf, "test.jpg", data)
        zf.writestr.assert_called_once_with("test.jpg", b"image_data")

    def test_write_image_decode_error(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        zf = MagicMock()
        ExporterService._write_image(zf, "test.jpg", "not_base64!!!")
        zf.writestr.assert_not_called()

    def test_build_filename(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        name = ExporterService._build_filename()
        assert name.startswith("evidence_sorting_")
        assert name.endswith(".zip")

    def test_build_delivery_filename_basic(self):
        from apps.evidence_sorting.services.exporter import ExporterService, DeliveryNote, STATUS_UNMATCHED

        svc = self._make_exporter()
        dn = MagicMock(spec=DeliveryNote)
        dn.date = "20240101"
        dn.amount = "100"
        dn.filename = "test.jpg"
        dn.match_status = "matched"
        dn.ocr_text = "出库单"
        dn.remark = ""

        name = svc._build_delivery_filename(dn, {})
        assert "20240101" in name
        assert "出库单" in name

    def test_build_delivery_filename_no_date(self):
        from apps.evidence_sorting.services.exporter import ExporterService, DeliveryNote

        svc = self._make_exporter()
        dn = MagicMock(spec=DeliveryNote)
        dn.date = None
        dn.amount = None
        dn.filename = "test.jpg"
        dn.match_status = "matched"
        dn.ocr_text = "出仓单明细"
        dn.remark = ""

        name = svc._build_delivery_filename(dn, {})
        assert "未知日期" in name

    def test_build_delivery_filename_unmatched_with_remark(self):
        from apps.evidence_sorting.services.exporter import ExporterService, DeliveryNote, STATUS_UNMATCHED

        svc = self._make_exporter()
        dn = MagicMock(spec=DeliveryNote)
        dn.date = "20240101"
        dn.amount = None
        dn.filename = "test.jpg"
        dn.match_status = STATUS_UNMATCHED
        dn.ocr_text = "出库单"
        dn.remark = "备注"

        name = svc._build_delivery_filename(dn, {})
        assert "备注" in name

    def test_build_delivery_filename_same_date_seq(self):
        from apps.evidence_sorting.services.exporter import ExporterService, DeliveryNote

        svc = self._make_exporter()
        dn = MagicMock(spec=DeliveryNote)
        dn.date = "20240101"
        dn.amount = None
        dn.filename = "test.jpg"
        dn.match_status = "matched"
        dn.ocr_text = "出库单"
        dn.remark = ""

        counter = {"20240101": 1}
        name = svc._build_delivery_filename(dn, counter)
        assert "_2" in name

    def test_write_category(self):
        from apps.evidence_sorting.services.exporter import ExporterService
        import base64

        svc = self._make_exporter()
        zf = MagicMock()
        data = base64.b64encode(b"img").decode()
        items = [{"filename": "a.jpg", "image_data": data}, {"filename": "b.jpg", "image_data": ""}]
        svc._write_category(zf, "收款情况", items)
        zf.writestr.assert_called_once()

    def test_ensure_output_dir_no_media_root(self):
        from apps.evidence_sorting.services.exporter import ExporterService

        with patch("django.conf.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = None
            with pytest.raises(RuntimeError, match="MEDIA_ROOT"):
                ExporterService._ensure_output_dir()

    def test_ensure_output_dir_success(self, tmp_path):
        from apps.evidence_sorting.services.exporter import ExporterService

        with patch("django.conf.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            result = ExporterService._ensure_output_dir()
            assert result.exists()
