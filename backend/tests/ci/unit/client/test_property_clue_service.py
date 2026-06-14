"""client/services/property_clue_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.client.services.property_clue_service import PropertyClueService, _VALID_CLUE_TYPES, _CONTENT_TEMPLATES


def _mock_internal_query_service() -> MagicMock:
    svc = MagicMock()
    svc.get_client.return_value = SimpleNamespace(id=1, name="Client")
    return svc


def _make_clue(**kwargs: object) -> MagicMock:
    clue = MagicMock()
    clue.id = kwargs.get("id", 1)
    clue.clue_type = kwargs.get("clue_type", "bank")
    clue.content = kwargs.get("content", "")
    clue.attachments = MagicMock()
    clue.attachments.all.return_value = []
    clue.save = MagicMock()
    clue.delete = MagicMock()
    return clue


# ── _validate_clue_type ───────────────────────────────────────────────


class TestValidateClueType:
    def test_valid_types(self) -> None:
        svc = PropertyClueService()
        for clue_type in _VALID_CLUE_TYPES:
            svc._validate_clue_type(clue_type)

    def test_invalid_type(self) -> None:
        svc = PropertyClueService()
        with pytest.raises(ValidationException):
            svc._validate_clue_type("invalid_type")


# ── _get_client_or_404 ────────────────────────────────────────────────


class TestGetClientOr404:
    def test_not_found(self) -> None:
        mock_iqs = _mock_internal_query_service()
        mock_iqs.get_client.return_value = None
        svc = PropertyClueService(internal_query_service=mock_iqs)
        with pytest.raises(NotFoundError):
            svc._get_client_or_404(999)

    def test_found(self) -> None:
        mock_iqs = _mock_internal_query_service()
        svc = PropertyClueService(internal_query_service=mock_iqs)
        result = svc._get_client_or_404(1)
        assert result.id == 1


# ── get_clue ──────────────────────────────────────────────────────────


class TestGetClue:
    def test_not_found(self) -> None:
        svc = PropertyClueService()
        with patch("apps.client.services.property_clue_service.PropertyClue") as MockClue:
            MockClue.objects.prefetch_related.return_value.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.get_clue(999)

    def test_found(self) -> None:
        svc = PropertyClueService()
        clue = _make_clue()
        with patch("apps.client.services.property_clue_service.PropertyClue") as MockClue:
            MockClue.objects.prefetch_related.return_value.filter.return_value.first.return_value = clue
            assert svc.get_clue(1) is clue


# ── list_clues_by_client ───────────────────────────────────────────────


class TestListCluesByClient:
    def test_client_not_found(self) -> None:
        mock_iqs = _mock_internal_query_service()
        mock_iqs.get_client.return_value = None
        svc = PropertyClueService(internal_query_service=mock_iqs)
        with pytest.raises(NotFoundError):
            svc.list_clues_by_client(999)

    def test_returns_list(self) -> None:
        mock_iqs = _mock_internal_query_service()
        clue = _make_clue()
        svc = PropertyClueService(internal_query_service=mock_iqs)
        with patch("apps.client.services.property_clue_service.PropertyClue") as MockClue:
            MockClue.objects.prefetch_related.return_value.filter.return_value.order_by.return_value = [clue]
            result = svc.list_clues_by_client(1)
            assert len(result) == 1


# ── update_clue ───────────────────────────────────────────────────────


class TestUpdateClue:
    def test_updates_type_and_content(self, db: object) -> None:
        svc = PropertyClueService()
        clue = _make_clue()
        with patch.object(svc, "get_clue", return_value=clue):
            result = svc.update_clue(1, {"clue_type": "wechat", "content": "new"})
            assert result.clue_type == "wechat"
            assert result.content == "new"
            clue.save.assert_called()

    def test_no_changes(self, db: object) -> None:
        svc = PropertyClueService()
        clue = _make_clue()
        with patch.object(svc, "get_clue", return_value=clue):
            svc.update_clue(1, {})
            clue.save.assert_not_called()


# ── delete_clue ───────────────────────────────────────────────────────


class TestDeleteClue:
    def test_success(self, db: object) -> None:
        svc = PropertyClueService()
        clue = _make_clue()
        with patch.object(svc, "get_clue", return_value=clue):
            svc.delete_clue(1)
            clue.delete.assert_called_once()


# ── delete_attachment ──────────────────────────────────────────────────


class TestDeleteAttachment:
    def test_not_found(self, db: object) -> None:
        svc = PropertyClueService()

        class FakeDoesNotExist(Exception):
            pass

        with patch("apps.client.services.property_clue_service.PropertyClueAttachment") as MockAtt:
            MockAtt.DoesNotExist = FakeDoesNotExist
            MockAtt.objects.get.side_effect = FakeDoesNotExist()
            with pytest.raises(NotFoundError):
                svc.delete_attachment(999)

    def test_success(self, db: object) -> None:
        svc = PropertyClueService()
        attachment = MagicMock()
        attachment.file_path = "/path/to/file"
        attachment.delete = MagicMock()
        with patch("apps.client.services.property_clue_service.PropertyClueAttachment") as MockAtt:
            MockAtt.objects.get.return_value = attachment
            svc.delete_attachment(1)
            attachment.delete.assert_called_once()


# ── get_content_template ──────────────────────────────────────────────


class TestGetContentTemplate:
    def test_bank_template(self) -> None:
        svc = PropertyClueService()
        tmpl = svc.get_content_template("bank")
        assert "户名" in tmpl

    def test_unknown_type(self) -> None:
        svc = PropertyClueService()
        assert svc.get_content_template("unknown") == ""


# ── Constants ─────────────────────────────────────────────────────────


class TestConstants:
    def test_clue_types(self) -> None:
        assert "bank" in _VALID_CLUE_TYPES
        assert "wechat" in _VALID_CLUE_TYPES
        assert "alipay" in _VALID_CLUE_TYPES

    def test_content_templates_keys(self) -> None:
        assert "bank" in _CONTENT_TEMPLATES
        assert "wechat" in _CONTENT_TEMPLATES
