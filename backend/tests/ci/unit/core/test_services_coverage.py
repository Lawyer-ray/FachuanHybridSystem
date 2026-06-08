"""core 模块单元测试（system_update_service, conversation_service, s3_provider, folder_binding_crud）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest


# ── system_update_service ───────────────────────────────────────


class TestSystemUpdateService:
    def test_build_state(self) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        svc = object.__new__(SystemUpdateService)
        svc._repo_root = Path("/tmp/test_repo")
        svc._now_iso = lambda: "2024-01-01T00:00:00"

        state = svc._build_state(
            run_id="abc", status="running", message="msg",
            triggered_by="user", steps=[]
        )
        assert state["run_id"] == "abc"
        assert state["status"] == "running"
        assert state["message"] == "msg"

    def test_build_state_with_options(self) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        svc = object.__new__(SystemUpdateService)
        svc._repo_root = Path("/tmp/test_repo")
        svc._now_iso = lambda: "2024-01-01T00:00:00"

        state = svc._build_state(
            run_id="abc", status="success", message="done",
            triggered_by="user", steps=[], options={"enable_post_update_setup": True}
        )
        assert state["options"]["enable_post_update_setup"] is True

    @patch("apps.core.services.system_update_service.cache")
    def test_get_state_idle(self, mock_cache: MagicMock) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        mock_cache.get.return_value = None
        svc = object.__new__(SystemUpdateService)
        svc._repo_root = Path("/tmp/test_repo")
        svc._now_iso = lambda: "2024-01-01T00:00:00"
        state = svc.get_state()
        assert state["status"] == "idle"

    @patch("apps.core.services.system_update_service.cache")
    def test_get_state_from_cache(self, mock_cache: MagicMock) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        mock_cache.get.return_value = {"status": "running", "run_id": "abc"}
        svc = object.__new__(SystemUpdateService)
        svc._repo_root = Path("/tmp/test_repo")
        svc._now_iso = lambda: "2024-01-01T00:00:00"
        state = svc.get_state()
        assert state["status"] == "running"

    def test_now_iso_format(self) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        result = SystemUpdateService._now_iso()
        assert "T" in result

    def test_resolve_backend_root_with_backend(self) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "backend").mkdir()
            result = SystemUpdateService._resolve_backend_root(repo)
            assert result == repo / "backend"

    def test_resolve_backend_root_without_backend(self) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            result = SystemUpdateService._resolve_backend_root(repo)
            assert result == repo

    @patch("apps.core.services.system_update_service.cache")
    def test_release_lock(self, mock_cache: MagicMock) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        mock_cache.get.return_value = "run_123"
        svc = object.__new__(SystemUpdateService)
        svc._release_lock("run_123")
        mock_cache.delete.assert_called_once()

    @patch("apps.core.services.system_update_service.cache")
    def test_release_lock_mismatch(self, mock_cache: MagicMock) -> None:
        from apps.core.services.system_update_service import SystemUpdateService

        mock_cache.get.return_value = "other_run"
        svc = object.__new__(SystemUpdateService)
        svc._release_lock("run_123")
        mock_cache.delete.assert_not_called()

    def test_append_step(self) -> None:
        from apps.core.services.system_update_service import SystemUpdateService
        from apps.core.infrastructure.subprocess_runner import SubprocessOutput

        svc = object.__new__(SystemUpdateService)
        svc._now_iso = lambda: "2024-01-01T00:00:00"
        steps: list = []
        output = SubprocessOutput(stdout="ok", stderr="", returncode=0)
        svc._append_step(steps, name="test_step", output=output)
        assert len(steps) == 1
        assert steps[0]["name"] == "test_step"
        assert steps[0]["status"] == "success"


# ── conversation_service (existing tests cover dataclasses, so test remaining) ──


class TestConversationServiceAdditional:
    def test_generate_session_id_format(self) -> None:
        from apps.core.services.conversation_service import ConversationService

        svc = ConversationService(repository=MagicMock())
        sid = svc._generate_session_id()
        assert sid.startswith("session_")
        assert len(sid) == 20

    def test_user_id_default_empty(self) -> None:
        from apps.core.services.conversation_service import ConversationService

        svc = ConversationService(repository=MagicMock())
        assert svc.user_id == ""

    def test_user_id_custom(self) -> None:
        from apps.core.services.conversation_service import ConversationService

        svc = ConversationService(user_id="u1", repository=MagicMock())
        assert svc.user_id == "u1"

    def test_clear_history(self) -> None:
        from apps.core.services.conversation_service import ConversationService

        mock_repo = MagicMock()
        svc = ConversationService(repository=mock_repo)
        svc._memory = MagicMock()
        svc.clear_history()
        mock_repo.delete_by_session_id.assert_called_once()
        svc._memory.clear.assert_called_once()

    def test_get_history(self) -> None:
        from apps.core.services.conversation_service import ConversationService

        mock_repo = MagicMock()
        mock_repo.get_by_session_id.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        svc = ConversationService(repository=mock_repo)
        result = svc.get_history(limit=10)
        assert isinstance(result, list)

    def test_add_system_message(self) -> None:
        from apps.core.services.conversation_service import ConversationService

        mock_repo = MagicMock()
        mock_repo.create.return_value = MagicMock()
        svc = ConversationService(repository=mock_repo)
        svc.add_system_message("system msg")
        mock_repo.create.assert_called_once()


# ── s3_provider ─────────────────────────────────────────────────


class TestS3Provider:
    def test_full_key_no_root(self) -> None:
        from apps.core.cloud_storage.s3_provider import S3Provider

        provider = object.__new__(S3Provider)
        provider._root = ""
        assert provider._full_key("path/to/file") == "path/to/file"

    def test_full_key_with_root(self) -> None:
        from apps.core.cloud_storage.s3_provider import S3Provider

        provider = object.__new__(S3Provider)
        provider._root = "root"
        assert provider._full_key("path/to/file") == "root/path/to/file"

    def test_full_key_strips_slashes(self) -> None:
        from apps.core.cloud_storage.s3_provider import S3Provider

        provider = object.__new__(S3Provider)
        provider._root = "root"
        assert provider._full_key("/path/to/file/") == "root/path/to/file"

    def test_full_key_empty_path(self) -> None:
        from apps.core.cloud_storage.s3_provider import S3Provider

        provider = object.__new__(S3Provider)
        provider._root = ""
        assert provider._full_key("") == ""

    def test_full_key_root_only(self) -> None:
        from apps.core.cloud_storage.s3_provider import S3Provider

        provider = object.__new__(S3Provider)
        provider._root = "bucket_root"
        assert provider._full_key("") == "bucket_root"


# ── folder_binding_crud_service ─────────────────────────────────


class TestFolderBindingCrudService:
    def test_compute_relative_path_no_contract(self) -> None:
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = object.__new__(FolderBindingCrudService)
        owner = MagicMock()
        owner.contract = None
        result = svc._compute_relative_path(owner, "/some/path")
        assert result is None

    def test_compute_relative_path_no_binding(self) -> None:
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = object.__new__(FolderBindingCrudService)
        owner = MagicMock()
        owner.contract.folder_binding = None
        result = svc._compute_relative_path(owner, "/some/path")
        assert result is None

    def test_compute_relative_path_no_folder_path(self) -> None:
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = object.__new__(FolderBindingCrudService)
        owner = MagicMock()
        owner.contract.folder_binding.folder_path = ""
        result = svc._compute_relative_path(owner, "/some/path")
        assert result is None

    def test_get_owner_type(self) -> None:
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = object.__new__(FolderBindingCrudService)
        owner = MagicMock()
        owner.case_type = "civil"
        assert svc._get_owner_type(owner) == "civil"

    def test_get_owner_type_empty(self) -> None:
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = object.__new__(FolderBindingCrudService)
        owner = MagicMock()
        owner.case_type = None
        assert svc._get_owner_type(owner) == ""

    def test_resolve_subdir_path_returns_none(self) -> None:
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = object.__new__(FolderBindingCrudService)
        assert svc._resolve_subdir_path(owner_type="civil", subdir_key="test") is None


# ── wechat_mp auth_handler (fix import) ─────────────────────────


class TestWechatMpAuthHandler2:
    @pytest.mark.asyncio
    async def test_check_login_status_on_login_page(self) -> None:
        from apps.wechat_mp.services.auth_handler import check_login_status

        mock_page = MagicMock()
        mock_page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage?act=login"
        result = await check_login_status(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_check_login_status_no_indicators(self) -> None:
        from apps.wechat_mp.services.auth_handler import check_login_status

        mock_page = MagicMock()
        mock_page.url = "https://mp.weixin.qq.com/cgi-bin/home"

        async def mock_query_selector(selector: str):
            return None

        mock_page.query_selector = mock_query_selector
        result = await check_login_status(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_capture_qr_code_element_found(self) -> None:
        from apps.wechat_mp.services.auth_handler import capture_qr_code

        mock_element = MagicMock()

        async def mock_screenshot():
            return b"qr_bytes"

        mock_element.screenshot = mock_screenshot

        async def mock_query_selector(selector: str):
            return mock_element

        mock_page = MagicMock()
        mock_page.query_selector = mock_query_selector
        result = await capture_qr_code(mock_page)
        assert result == b"qr_bytes"

    @pytest.mark.asyncio
    async def test_capture_qr_code_not_found(self) -> None:
        from apps.wechat_mp.services.auth_handler import capture_qr_code

        call_count = 0

        async def mock_query_selector(selector: str):
            return None

        async def mock_screenshot():
            return b"full_page"

        mock_page = MagicMock()
        mock_page.query_selector = mock_query_selector
        mock_page.screenshot = mock_screenshot
        result = await capture_qr_code(mock_page)
        assert result == b"full_page"
