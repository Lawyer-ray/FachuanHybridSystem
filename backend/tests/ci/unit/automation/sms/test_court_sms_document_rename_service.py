"""法院短信关联文书重命名服务测试（court_sms_api rename 端点下沉）."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReference
from apps.automation.services.sms.court_sms_document_rename_service import (
    CourtSMSDocumentRenameResult,
    CourtSMSDocumentRenameService,
)
from apps.core.exceptions import NotFoundError, ValidationException


def _make_service(sms: Any, refs: list[CourtSMSDocumentReference]) -> CourtSMSDocumentRenameService:
    repo = MagicMock()
    repo.get_by_id_or_none = MagicMock(return_value=sms)
    ref_svc = MagicMock()
    ref_svc.collect = MagicMock(return_value=refs)
    return CourtSMSDocumentRenameService(repository=repo, reference_service=ref_svc)


def _ref(file_path: Any, court_document_id: int | None = 7) -> CourtSMSDocumentReference:
    return CourtSMSDocumentReference(
        display_name="传票",
        file_path=str(file_path),
        source="court_document",
        court_document_id=court_document_id,
    )


class TestRenameDocumentErrors:
    @pytest.mark.asyncio
    async def test_sms_not_found(self):
        svc = _make_service(None, [])
        with pytest.raises(NotFoundError, match="短信记录不存在"):
            await svc.rename_document(sms_id=999, ref_index=0, new_stem="新名")

    @pytest.mark.asyncio
    async def test_index_out_of_range(self, tmp_path):
        sms = MagicMock(id=1)
        svc = _make_service(sms, [])
        with pytest.raises(ValidationException) as ei:
            await svc.rename_document(sms_id=1, ref_index=3, new_stem="新名")
        assert ei.value.code == "DOC_INDEX_OUT_OF_RANGE"

    @pytest.mark.asyncio
    async def test_file_missing(self, tmp_path):
        sms = MagicMock(id=1)
        missing = tmp_path / "missing.pdf"
        svc = _make_service(sms, [_ref(missing)])
        with pytest.raises(ValidationException) as ei:
            await svc.rename_document(sms_id=1, ref_index=0, new_stem="新名")
        assert ei.value.code == "DOC_FILE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_blank_stem_rejected(self, tmp_path):
        sms = MagicMock(id=1)
        src = tmp_path / "传票.pdf"
        src.write_bytes(b"pdf")
        svc = _make_service(sms, [_ref(src)])
        with pytest.raises(ValidationException) as ei:
            await svc.rename_document(sms_id=1, ref_index=0, new_stem="   ")
        assert ei.value.code == "EMPTY_FILENAME"

    @pytest.mark.asyncio
    async def test_stem_with_dot_rejected(self, tmp_path):
        sms = MagicMock(id=1)
        src = tmp_path / "传票.pdf"
        src.write_bytes(b"pdf")
        svc = _make_service(sms, [_ref(src)])
        with pytest.raises(ValidationException) as ei:
            await svc.rename_document(sms_id=1, ref_index=0, new_stem="新名.pdf")
        assert ei.value.code == "FILENAME_HAS_EXTENSION"

    @pytest.mark.asyncio
    async def test_illegal_chars_only_rejected(self, tmp_path):
        sms = MagicMock(id=1)
        src = tmp_path / "传票.pdf"
        src.write_bytes(b"pdf")
        svc = _make_service(sms, [_ref(src)])
        with pytest.raises(ValidationException) as ei:
            await svc.rename_document(sms_id=1, ref_index=0, new_stem=r'\/:*?"<>|')
        assert ei.value.code == "INVALID_FILENAME"

    @pytest.mark.asyncio
    async def test_target_exists_rejected(self, tmp_path):
        sms = MagicMock(id=1)
        src = tmp_path / "传票.pdf"
        src.write_bytes(b"pdf")
        (tmp_path / "新名.pdf").write_bytes(b"taken")
        svc = _make_service(sms, [_ref(src)])
        with pytest.raises(ValidationException) as ei:
            await svc.rename_document(sms_id=1, ref_index=0, new_stem="新名")
        assert ei.value.code == "TARGET_EXISTS"
        assert src.exists()  # 原文件未被改动


class TestRenameDocumentSuccess:
    @pytest.mark.asyncio
    async def test_unchanged_name_short_circuits(self, tmp_path):
        sms = MagicMock(id=1)
        src = tmp_path / "传票.pdf"
        src.write_bytes(b"pdf")
        svc = _make_service(sms, [_ref(src)])

        with patch.object(CourtSMSDocumentRenameService, "_sync_document_references", new=AsyncMock()) as mock_sync:
            result = await svc.rename_document(sms_id=1, ref_index=0, new_stem="传票")

        assert result == CourtSMSDocumentRenameResult(success=True, message="文件名未变化")
        mock_sync.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_renames_and_syncs_references(self, tmp_path):
        sms = MagicMock(id=1)
        src = tmp_path / "传票.pdf"
        src.write_bytes(b"pdf")
        svc = _make_service(sms, [_ref(src)])

        with patch.object(CourtSMSDocumentRenameService, "_sync_document_references", new=AsyncMock()) as mock_sync:
            result = await svc.rename_document(sms_id=1, ref_index=0, new_stem="开庭传票-新")

        assert result.success is True
        assert result.new_name == "开庭传票-新.pdf"
        assert not src.exists()
        assert (tmp_path / "开庭传票-新.pdf").read_bytes() == b"pdf"
        mock_sync.assert_awaited_once()
        assert mock_sync.await_args is not None
        kwargs = mock_sync.await_args.kwargs
        assert kwargs["court_document_id"] == 7
        assert kwargs["old_abs"].endswith("传票.pdf")
        assert kwargs["new_abs"].endswith("开庭传票-新.pdf")
