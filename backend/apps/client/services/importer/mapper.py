"""当事人 JSON 导入映射器。"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClientIdentityDocCommand:
    doc_type: str
    file_path: str


@dataclass(frozen=True)
class ClientImportCommand:
    client_data: dict[str, Any]
    identity_docs: list[ClientIdentityDocCommand]
    admin_user: str


class ClientJsonImportMapper:
    _CLIENT_FIELDS: tuple[str, ...] = (
        "name",
        "phone",
        "address",
        "client_type",
        "id_number",
        "legal_representative",
        "is_our_client",
    )

    def to_command(self, json_data: dict[str, Any], admin_user: str) -> ClientImportCommand:
        client_data = self._extract_client_data(json_data)
        identity_docs = self._extract_identity_docs(json_data.get("identity_docs"))
        return ClientImportCommand(client_data=client_data, identity_docs=identity_docs, admin_user=admin_user)

    def _extract_client_data(self, json_data: dict[str, Any]) -> dict[str, Any]:
        client_data: dict[str, Any] = {f: json_data[f] for f in self._CLIENT_FIELDS if f in json_data}
        if "is_our_client" not in client_data:
            client_data["is_our_client"] = False
        return client_data

    def _extract_identity_docs(self, docs_data: Any | None) -> list[ClientIdentityDocCommand]:
        if not docs_data:
            return []
        if not isinstance(docs_data, list):
            return []

        cmds: list[ClientIdentityDocCommand] = []
        for doc in docs_data:
            if not isinstance(doc, dict):
                continue
            doc_type = doc.get("doc_type")
            file_path = doc.get("file_path")
            if not doc_type or not file_path:
                continue
            cmds.append(ClientIdentityDocCommand(doc_type=str(doc_type), file_path=str(file_path)))
        return cmds
