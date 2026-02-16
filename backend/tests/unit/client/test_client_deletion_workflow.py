import pytest
from django.db import transaction

from apps.client.models import PropertyClue, PropertyClueAttachment
from apps.client.workflows import ClientDeletionWorkflow
from tests.factories.client_factories import ClientFactory, ClientIdentityDocFactory


@pytest.mark.django_db(transaction=True)
def test_cleanup_files_on_commit_runs_after_commit():
    called = []

    def _deleter(p: str) -> None:
        called.append(p)

    workflow = ClientDeletionWorkflow(file_deleter=_deleter)
    client = ClientFactory()
    doc = ClientIdentityDocFactory(client=client, file_path="client_identity_docs/a.png")
    clue = PropertyClue.objects.create(client=client, clue_type=PropertyClue.BANK, content="x")
    attachment = PropertyClueAttachment.objects.create(
        property_clue=clue,
        file_path="property_clue_attachments/b.png",
        file_name="b.png",
    )

    with transaction.atomic():
        file_paths = workflow.collect_client_file_paths(client_id=client.id)
        assert set(file_paths) == {doc.file_path, attachment.file_path}
        workflow.cleanup_files_on_commit(file_paths=file_paths)
        assert called == []

    assert set(called) == {doc.file_path, attachment.file_path}
