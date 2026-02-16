import pytest


@pytest.mark.django_db
def test_rename_uploaded_file_uses_doc_type_then_client_name(settings, tmp_path):
    from apps.client.models import Client, ClientIdentityDoc
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

    settings.MEDIA_ROOT = tmp_path

    client = Client.objects.create(
        name="广东润知信息科技有限公司",
        client_type=Client.LEGAL,
    )
    rel_path = "client_docs/1/license.pdf"
    abs_path = tmp_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(b"fake-pdf")

    doc = ClientIdentityDoc.objects.create(
        client=client,
        doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
        file_path=rel_path,
    )

    ClientIdentityDocService().rename_uploaded_file(doc)
    doc.refresh_from_db()

    assert doc.file_path.endswith("营业执照（广东润知信息科技有限公司）.pdf")
    assert (tmp_path / doc.file_path).exists()

