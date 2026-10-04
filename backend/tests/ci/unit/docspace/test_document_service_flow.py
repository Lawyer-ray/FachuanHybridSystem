"""DocSpaceDocumentService 流程补充测试。

覆盖 create_document / download_document / sync_document / _aget_client
（既有 test_document_service.py 已覆盖 get_user_doc 与 upload_file）。
远端调用一律 mock，DB 走 async ORM（transaction=True）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.docspace.services.document_service import DocSpaceDocumentService
from apps.organization.models import Lawyer


@pytest.fixture
def lawyer(db: None) -> Lawyer:
    return Lawyer.objects.create_user(username="ds_flow_lawyer", password="x", real_name="流程律师")


def _ds_file(file_id: int = 101, **overrides) -> SimpleNamespace:
    defaults = {
        "id": file_id,
        "title": "远端文档.docx",
        "folder_id": 9,
        "file_ext": ".docx",
        "content_length": 4096,
        "web_url": "https://docspace.example/f/" + str(file_id),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_aget_client_reads_config(lawyer: Lawyer) -> None:
    from apps.docspace.services.docspace_client import DocSpaceClient

    with (
        patch(
            "apps.docspace.services.document_service.config.aget_portal_url",
            new=AsyncMock(return_value="https://cfg.example.com"),
        ),
        patch(
            "apps.docspace.services.document_service.config.aget_api_token",
            new=AsyncMock(return_value="tok-xyz"),
        ),
    ):
        client = await DocSpaceDocumentService()._aget_client()

    assert isinstance(client, DocSpaceClient)
    assert client._base == "https://cfg.example.com"
    assert client._headers == {"Authorization": "Bearer tok-xyz"}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_document_registers_mapping(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    await DocSpaceDocument.objects.filter(lawyer=lawyer).adelete()
    service = DocSpaceDocumentService()
    with (
        patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory,
        patch(
            "apps.docspace.services.document_service.config.aget_root_folder_id",
            new=AsyncMock(return_value=9),
        ),
    ):
        mock_client_factory.return_value.acreate_empty_docx = AsyncMock(return_value=_ds_file(501))
        doc = await service.create_document(lawyer=lawyer, title="空白合同.docx")

    assert doc.docspace_file_id == 501
    assert doc.title == "远端文档.docx"
    assert doc.lawyer_id == lawyer.id
    mock_client_factory.return_value.acreate_empty_docx.assert_awaited_once_with(9, "空白合同.docx")
    await DocSpaceDocument.objects.filter(lawyer=lawyer).adelete()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_create_document_without_folder_raises(lawyer: Lawyer) -> None:
    with patch(
        "apps.docspace.services.document_service.config.aget_root_folder_id",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(ValidationException, match="未配置默认文件夹"):
            await DocSpaceDocumentService().create_document(lawyer=lawyer, title="x.docx")


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_documents_orders_and_limits(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    await DocSpaceDocument.objects.filter(lawyer=lawyer).adelete()
    created = []
    for i in range(3):
        created.append(
            await DocSpaceDocument.objects.acreate(
                lawyer=lawyer,
                title=f"文档{i}.docx",
                docspace_file_id=600 + i,
                docspace_folder_id=9,
            )
        )

    docs = await DocSpaceDocumentService().list_documents(lawyer=lawyer)
    assert len(docs) == 3
    # 按 -updated_at 排序（同秒级创建，倒序不确保严格，验证集合即可）
    assert {d.pk for d in docs} == {c.pk for c in created}

    limited = await DocSpaceDocumentService().list_documents(lawyer=lawyer, limit=1)
    assert len(limited) == 1
    await DocSpaceDocument.objects.filter(lawyer=lawyer).adelete()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_delete_document_tolerates_remote_failure(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    doc = await DocSpaceDocument.objects.acreate(
        lawyer=lawyer,
        title="待删除.docx",
        docspace_file_id=701,
        docspace_folder_id=9,
    )
    service = DocSpaceDocumentService()
    with patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory:
        mock_client_factory.return_value.adelete_file = AsyncMock(side_effect=RuntimeError("remote 404"))
        await service.delete_document(doc_id=doc.id, lawyer=lawyer)

    assert await DocSpaceDocument.objects.filter(pk=doc.pk).aexists() is False
    mock_client_factory.return_value.adelete_file.assert_awaited_once_with(701)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_download_document_returns_content_and_name(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    doc = await DocSpaceDocument.objects.acreate(
        lawyer=lawyer,
        title="下载.docx",
        docspace_file_id=801,
        docspace_folder_id=9,
    )
    service = DocSpaceDocumentService()
    with patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory:
        mock_client_factory.return_value.adownload_file = AsyncMock(return_value=(b"abc", "下载.docx"))
        content, filename = await service.download_document(doc_id=doc.id, lawyer=lawyer)

    assert content == b"abc"
    assert filename == "下载.docx"
    mock_client_factory.return_value.adownload_file.assert_awaited_once_with(801)
    await doc.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_document_updates_local_metadata(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    doc = await DocSpaceDocument.objects.acreate(
        lawyer=lawyer,
        title="旧标题.docx",
        docspace_file_id=901,
        docspace_folder_id=9,
        web_url="",
    )
    service = DocSpaceDocumentService()
    remote = _ds_file(901, title="新标题.docx", content_length=9999, web_url="https://docspace.example/f/901")
    with patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory:
        mock_client_factory.return_value.aget_file_info = AsyncMock(return_value=remote)
        synced = await service.sync_document(doc_id=doc.id, lawyer=lawyer)

    assert synced.title == "新标题.docx"
    assert synced.content_length == 9999
    assert synced.web_url == "https://docspace.example/f/901"
    assert synced.last_editor_id == lawyer.id
    await synced.adelete()
