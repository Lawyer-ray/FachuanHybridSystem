"""DocSpaceDocumentService 单元测试。

覆盖 get_user_doc 的命中/404、上传后本地映射登记（新建 / web_url 补丁）、
未配置默认文件夹的 400 语义。上传的远端调用以 mock 替代。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async

from apps.core.exceptions import NotFoundError, ValidationException
from apps.docspace.services.document_service import DocSpaceDocumentService
from apps.organization.models import Lawyer


@pytest.fixture
def lawyer(db: None) -> Lawyer:
    created: Lawyer = Lawyer.objects.create_user(username="ds_lawyer", password="x", real_name="律师甲")
    return created


@pytest.fixture
def other_lawyer(db: None) -> Lawyer:
    created: Lawyer = Lawyer.objects.create_user(username="ds_lawyer_b", password="x", real_name="律师乙")
    return created


def _ds_file(file_id: int = 101, web_url: str = "https://docspace.example/f/1") -> SimpleNamespace:
    return SimpleNamespace(
        id=file_id,
        title="起诉状.docx",
        folder_id=9,
        file_ext=".docx",
        content_length=1024,
        web_url=web_url,
    )


# ── get_user_doc ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_user_doc_hit(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    doc = await DocSpaceDocument.objects.acreate(
        lawyer=lawyer,
        title="起诉状.docx",
        docspace_file_id=101,
        docspace_folder_id=9,
    )
    got = await DocSpaceDocumentService().get_user_doc(doc_id=doc.id, lawyer=lawyer)
    assert got.pk == doc.pk


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_user_doc_miss_raises_404(lawyer: Lawyer) -> None:
    with pytest.raises(NotFoundError, match="文档不存在"):
        await DocSpaceDocumentService().get_user_doc(doc_id=99999, lawyer=lawyer)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_get_user_doc_other_lawyer_doc_is_404(lawyer: Lawyer, other_lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    doc = await DocSpaceDocument.objects.acreate(
        lawyer=other_lawyer,
        title="别人的文档.docx",
        docspace_file_id=102,
        docspace_folder_id=9,
    )
    with pytest.raises(NotFoundError):
        await DocSpaceDocumentService().get_user_doc(doc_id=doc.id, lawyer=lawyer)


# ── 上传 / 新建：本地映射登记 ───────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_upload_registers_new_mapping(lawyer: Lawyer) -> None:
    service = DocSpaceDocumentService()
    with (
        patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory,
        patch("apps.docspace.services.document_service.config.aget_root_folder_id", new=AsyncMock(return_value=9)),
    ):
        mock_client_factory.return_value.aupload_file = AsyncMock(return_value=_ds_file(201))
        doc = await service.upload_file(lawyer=lawyer, content=b"x", filename="a.docx", folder_id=None)

    assert doc.docspace_file_id == 201
    assert doc.lawyer_id == lawyer.id
    assert doc.web_url == "https://docspace.example/f/1"
    mock_client_factory.return_value.aupload_file.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_upload_without_folder_config_raises_400(lawyer: Lawyer) -> None:
    service = DocSpaceDocumentService()
    with patch("apps.docspace.services.document_service.config.aget_root_folder_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValidationException, match="未配置默认文件夹"):
            await service.upload_file(lawyer=lawyer, content=b"x", filename="a.docx", folder_id=None)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_upload_existing_mapping_patches_web_url(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    existing = await DocSpaceDocument.objects.acreate(
        lawyer=lawyer,
        title="旧标题.docx",
        docspace_file_id=301,
        docspace_folder_id=9,
        web_url="",
    )
    service = DocSpaceDocumentService()
    with (
        patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory,
        patch("apps.docspace.services.document_service.config.aget_root_folder_id", new=AsyncMock(return_value=9)),
    ):
        mock_client_factory.return_value.aupload_file = AsyncMock(return_value=_ds_file(301))
        doc = await service.upload_file(lawyer=lawyer, content=b"x", filename="a.docx", folder_id=9)

    assert doc.pk == existing.pk
    await sync_to_async(existing.refresh_from_db)()
    assert existing.web_url == "https://docspace.example/f/1"


# ── 列表 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_list_documents_scoped_to_lawyer(lawyer: Lawyer, other_lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    await DocSpaceDocument.objects.acreate(lawyer=lawyer, title="a.docx", docspace_file_id=401, docspace_folder_id=9)
    await DocSpaceDocument.objects.acreate(
        lawyer=other_lawyer, title="b.docx", docspace_file_id=402, docspace_folder_id=9
    )

    docs = await DocSpaceDocumentService().list_documents(lawyer=lawyer)
    assert [d.title for d in docs] == ["a.docx"]


# ── 删除：远端失败仍删本地 ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_delete_document_tolerates_remote_failure(lawyer: Lawyer) -> None:
    from apps.docspace.models import DocSpaceDocument

    doc = await DocSpaceDocument.objects.acreate(
        lawyer=lawyer, title="a.docx", docspace_file_id=501, docspace_folder_id=9
    )
    service = DocSpaceDocumentService()
    with patch.object(DocSpaceDocumentService, "_aget_client", new=AsyncMock()) as mock_client_factory:
        mock_client_factory.return_value.adelete_file = AsyncMock(side_effect=RuntimeError("远端 500"))
        await service.delete_document(doc_id=doc.id, lawyer=lawyer)

    assert await DocSpaceDocument.objects.filter(pk=doc.pk).acount() == 0
