"""补充覆盖测试: chat_records/services/core/screenshot_service.py (40 missing)

覆盖: get_screenshot, _validate_upload_file, _compute_hashes,
update_screenshot, delete_screenshot 等分支。
"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.chat_records.services.core.screenshot_service import ScreenshotService


def _make_file(content_type: str = "image/png", size: int = 100, content: bytes = b"fake") -> MagicMock:
    f = MagicMock()
    f.content_type = content_type
    f.size = size
    f.read.return_value = content
    f.seek.return_value = None
    return f


class TestGetScreenshot:
    @pytest.mark.django_db
    def test_not_found(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        with patch("apps.chat_records.services.core.screenshot_service.ChatRecordScreenshot") as MockSS:
            MockSS.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockSS.objects.select_related.return_value.get.side_effect = MockSS.DoesNotExist()
            with pytest.raises(NotFoundError):
                svc.get_screenshot(user=MagicMock(), screenshot_id="nonexistent")


class TestValidateUploadFile:
    def test_non_image_raises(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file(content_type="text/plain")
        with pytest.raises(ValidationException, match="仅支持"):
            svc._validate_upload_file(f)

    def test_oversized_raises(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file(content_type="image/png", size=25 * 1024 * 1024)
        with pytest.raises(ValidationException, match="过大"):
            svc._validate_upload_file(f)

    def test_valid_file(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file(content_type="image/jpeg", size=100)
        svc._validate_upload_file(f)  # Should not raise

    def test_empty_content_type(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file(content_type="")
        with pytest.raises(ValidationException, match="仅支持"):
            svc._validate_upload_file(f)

    def test_none_content_type(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = MagicMock()
        f.content_type = None
        f.size = 100
        with pytest.raises(ValidationException, match="仅支持"):
            svc._validate_upload_file(f)


class TestComputeHashes:
    def test_no_deduplication(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file()
        result = svc._compute_hashes(f, deduplicate=False, selection_service=MagicMock())
        assert result == ("", "")

    def test_with_content(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file(content=b"test content")
        mock_sel = MagicMock()
        mock_sel.calc_dhash_hex.return_value = "dhash123"
        sha, dhash = svc._compute_hashes(f, deduplicate=True, selection_service=mock_sel)
        assert len(sha) == 64  # SHA256 hex
        assert dhash == "dhash123"

    def test_empty_content(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = _make_file(content=b"")
        result = svc._compute_hashes(f, deduplicate=True, selection_service=MagicMock())
        assert result == ("", "")

    def test_read_failure_raises(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        f = MagicMock()
        f.read.side_effect = ValueError("seek failed")
        with pytest.raises(ValidationException, match="读取失败"):
            svc._compute_hashes(f, deduplicate=True, selection_service=MagicMock())


class TestUpdateScreenshot:
    @pytest.mark.django_db
    def test_no_updates_returns_same(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        mock_screenshot = MagicMock()
        mock_screenshot.title = "old"
        mock_screenshot.note = "old note"
        with patch.object(svc, "get_screenshot", return_value=mock_screenshot):
            result = svc.update_screenshot(user=MagicMock(), screenshot_id="x")
            assert result is mock_screenshot
            mock_screenshot.save.assert_not_called()

    @pytest.mark.django_db
    def test_update_title(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        mock_screenshot = MagicMock()
        mock_screenshot.title = "old"
        with patch.object(svc, "get_screenshot", return_value=mock_screenshot):
            result = svc.update_screenshot(user=MagicMock(), screenshot_id="x", title="new title")
            assert mock_screenshot.title == "new title"
            mock_screenshot.save.assert_called_once()

    @pytest.mark.django_db
    def test_update_note(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        mock_screenshot = MagicMock()
        mock_screenshot.note = "old note"
        with patch.object(svc, "get_screenshot", return_value=mock_screenshot):
            result = svc.update_screenshot(user=MagicMock(), screenshot_id="x", note="new note")
            assert mock_screenshot.note == "new note"


class TestDeleteScreenshot:
    @pytest.mark.django_db
    def test_delete_success(self) -> None:
        svc = ScreenshotService(project_service=MagicMock())
        mock_screenshot = MagicMock()
        with patch.object(svc, "get_screenshot", return_value=mock_screenshot):
            result = svc.delete_screenshot(user=MagicMock(), screenshot_id="x")
            assert result == {"success": True}
            mock_screenshot.delete.assert_called_once()
