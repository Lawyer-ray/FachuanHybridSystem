"""Business logic services."""

from typing import Any

from django.db import transaction

from apps.client.models import Client
from apps.client.services.client_identity_doc_service import ClientIdentityDocService


class ClientJsonImportPersister:
    def __init__(self, identity_doc_service: ClientIdentityDocService | None = None) -> None:
        self._identity_doc_service = identity_doc_service

    @property
    def identity_doc_service(self) -> ClientIdentityDocService:
        if self._identity_doc_service is None:
            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    @transaction.atomic
    def persist(self, *, client_data: dict[str, Any], identity_docs: list[dict[str, Any]]) -> Client:
        client = Client.objects.create(**client_data)

        for doc in identity_docs:
            self.identity_doc_service.add_identity_doc(
                client_id=client.pk,
                doc_type=doc["doc_type"],
                file_path=doc["file_path"],
            )

        return client
