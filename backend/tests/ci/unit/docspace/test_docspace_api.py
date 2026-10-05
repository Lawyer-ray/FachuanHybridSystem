"""docspace_api 端点单元测试。

直接调用 async 视图函数，service 层以 mock 替代（HTTP 一律不发）：
覆盖 _validate_upload 的白名单/大小校验、配置读取、上传/新建/列表/
详情/删除/下载/同步各端点的参数组装与响应结构。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import NotFoundError, ValidationException
from apps.docspace.api.docspace_api import (
    _get_document_service,
    _validate_upload,
    create_document,
    delete_document,
    download_document,
    get_docspace_config,
    get_document,
    list_documents,
    sync_document,
    upload_file,
)
from apps.docspace.services.document_service import DocSpaceDocumentService


def _doc(**overrides) -> SimpleNamespace:
    defaults = {
        "id": 11,
        "title": "起诉状.docx",
        "docspace_file_id": 901,
        "docspace_folder_id": 9,
        "file_ext": ".docx",
        "content_length": 2048,
        "web_url": "https://ds.example.com/edit/901",
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _request(user: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(auth=user)


class TestFactory:
    def test_factory_returns_service(self) -> None:
        assert isinstance(_get_document_service(), DocSpaceDocumentService)


class TestValidateUpload:
    def test_valid_extension_passes(self) -> None:
        f = SimpleUploadedFile("a.docx", b"x" * 10)
        assert _validate_upload(f) is None  # 合法文件通过校验

    def test_disallowed_extension_rejected(self) -> None:
        f = SimpleUploadedFile("a.exe", b"x" * 10)
        with pytest.raises(ValidationException) as exc_info:
            _validate_upload(f)
        assert exc_info.value.code == "INVALID_FILE_TYPE"
        assert ".exe" in exc_info.value.message
        assert "允许的格式" in str(exc_info.value.errors.get("file", ""))

    def test_no_extension_rejected(self) -> None:
        f = SimpleUploadedFile("noext", b"x" * 10)
        with pytest.raises(ValidationException, match="无扩展名"):
            _validate_upload(f)

    def test_oversize_rejected_before_read(self) -> None:
        # 不真正构造 50MB 内容：size 属性足以触发上限分支
        f = SimpleNamespace(name="big.pdf", size=60 * 1024 * 1024)
        with pytest.raises(ValidationException) as exc_info:
            _validate_upload(f)  # type: ignore[arg-type]
        assert exc_info.value.code == "FILE_TOO_LARGE"


class TestGetDocspaceConfig:
    def test_returns_portal_and_enabled(self) -> None:
        with (
            patch("apps.docspace.config.get_portal_url", return_value="https://cfg.example.com"),
            patch("apps.docspace.config.is_configured", return_value=True),
        ):
            out = get_docspace_config(MagicMock())
        assert out.portal_url == "https://cfg.example.com"
        assert out.enabled is True


@pytest.mark.asyncio
class TestUploadFileEndpoint:
    async def test_upload_returns_doc_payload(self) -> None:
        f = SimpleUploadedFile("contract.pdf", b"pdf-bytes")
        mock_service = MagicMock()
        mock_service.upload_file = AsyncMock(return_value=_doc(id=21, title="contract.pdf"))

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            out = await upload_file(_request(user="u1"), file=f, folder_id=33)

        assert out.id == 21
        assert out.title == "contract.pdf"
        mock_service.upload_file.assert_awaited_once_with(
            lawyer="u1", content=b"pdf-bytes", filename="contract.pdf", folder_id=33
        )

    async def test_upload_default_folder_when_omitted(self) -> None:
        f = SimpleUploadedFile("m.md", b"# hi")
        mock_service = MagicMock()
        mock_service.upload_file = AsyncMock(return_value=_doc())

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            await upload_file(_request(), file=f, folder_id=None)

        assert mock_service.upload_file.await_args.kwargs["folder_id"] is None
        assert mock_service.upload_file.await_args.kwargs["filename"] == "m.md"

    async def test_upload_invalid_extension_raises(self) -> None:
        f = SimpleUploadedFile("virus.bat", b"x")
        mock_service = MagicMock()
        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            with pytest.raises(ValidationException, match="不支持的文件格式"):
                await upload_file(_request(), file=f, folder_id=None)
        mock_service.upload_file.assert_not_called()


@pytest.mark.asyncio
class TestCreateDocumentEndpoint:
    async def test_create_returns_doc_payload(self) -> None:
        mock_service = MagicMock()
        mock_service.create_document = AsyncMock(return_value=_doc(id=31, title="新建文档.docx"))

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            out = await create_document(_request(user="u2"), title="新建文档.docx")

        assert out.id == 31
        assert out.docspace_file_id == 901
        mock_service.create_document.assert_awaited_once_with(lawyer="u2", title="新建文档.docx")


@pytest.mark.asyncio
class TestListDocumentsEndpoint:
    async def test_list_maps_all_docs(self) -> None:
        mock_service = MagicMock()
        mock_service.list_documents = AsyncMock(return_value=[_doc(id=1), _doc(id=2, title="b.docx")])

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            out = await list_documents(_request(user="u3"))

        assert [d.id for d in out] == [1, 2]
        assert out[1].title == "b.docx"


@pytest.mark.asyncio
class TestGetDocumentEndpoint:
    async def test_get_returns_single_doc(self) -> None:
        mock_service = MagicMock()
        mock_service.get_user_doc = AsyncMock(return_value=_doc(id=41))

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            out = await get_document(_request(), doc_id=41)

        assert out.id == 41
        mock_service.get_user_doc.assert_awaited_once_with(doc_id=41, lawyer=None)

    async def test_get_propagates_not_found(self) -> None:
        mock_service = MagicMock()
        mock_service.get_user_doc = AsyncMock(side_effect=NotFoundError("文档不存在"))

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            with pytest.raises(NotFoundError):
                await get_document(_request(), doc_id=999)


@pytest.mark.asyncio
class TestDeleteDocumentEndpoint:
    async def test_delete_returns_ok(self) -> None:
        mock_service = MagicMock()
        mock_service.delete_document = AsyncMock(return_value=None)

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            out = await delete_document(_request(user="u4"), doc_id=51)

        assert out == {"ok": True}
        mock_service.delete_document.assert_awaited_once_with(doc_id=51, lawyer="u4")


@pytest.mark.asyncio
class TestDownloadDocumentEndpoint:
    async def test_download_streams_attachment(self) -> None:
        from django.http import FileResponse

        mock_service = MagicMock()
        mock_service.download_document = AsyncMock(return_value=(b"docx-binary", "report.docx"))

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            response = await download_document(_request(), doc_id=61)

        assert isinstance(response, FileResponse)
        assert response.filename == "report.docx"
        assert "attachment" in response.headers.get("Content-Disposition", "")
        body = b"".join(response.streaming_content)
        assert body == b"docx-binary"


@pytest.mark.asyncio
class TestSyncDocumentEndpoint:
    async def test_sync_returns_refreshed_doc(self) -> None:
        mock_service = MagicMock()
        mock_service.sync_document = AsyncMock(return_value=_doc(id=71, title="同步后.docx"))

        with patch("apps.docspace.api.docspace_api._get_document_service", return_value=mock_service):
            out = await sync_document(_request(user="u5"), doc_id=71)

        assert out.id == 71
        assert out.title == "同步后.docx"
        mock_service.sync_document.assert_awaited_once_with(doc_id=71, lawyer="u5")
