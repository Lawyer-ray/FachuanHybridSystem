"""Business logic services."""

import logging
from dataclasses import dataclass
from typing import Any

from .mapper import ClientJsonImportMapper
from .persister import ClientJsonImportPersister
from .validator import ClientJsonImportValidator

logger = logging.getLogger("apps.client")


@dataclass
class ClientJsonImportResult:
    success: bool
    client_id: int | None = None
    error_message: str | None = None


class ClientJsonImporter:
    def __init__(
        self,
        *,
        validator: ClientJsonImportValidator | None = None,
        mapper: ClientJsonImportMapper | None = None,
        persister: ClientJsonImportPersister | None = None,
    ) -> None:
        self._validator = validator
        self._mapper = mapper
        self._persister = persister

    @property
    def validator(self) -> ClientJsonImportValidator:
        if self._validator is None:
            self._validator = ClientJsonImportValidator()
        return self._validator

    @property
    def mapper(self) -> ClientJsonImportMapper:
        if self._mapper is None:
            self._mapper = ClientJsonImportMapper()
        return self._mapper

    @property
    def persister(self) -> ClientJsonImportPersister:
        if self._persister is None:
            self._persister = ClientJsonImportPersister()
        return self._persister

    def import_from_json(self, json_data: dict[str, Any], *, admin_user: str) -> ClientJsonImportResult:
        self.validator.validate(json_data)
        cmd = self.mapper.to_command(json_data, admin_user=admin_user)
        client = self.persister.persist(
            client_data=cmd.client_data,
            identity_docs=[{"doc_type": d.doc_type, "file_path": d.file_path} for d in cmd.identity_docs],
        )

        logger.info(
            "JSON 导入客户成功",
            extra={
                "client_id": client.pk,
                "client_name": client.name,
                "admin_user": admin_user,
                "action": "import_from_json",
            },
        )
        return ClientJsonImportResult(success=True, client_id=client.pk)
