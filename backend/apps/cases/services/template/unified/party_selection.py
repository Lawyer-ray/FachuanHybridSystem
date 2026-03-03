"""Business logic services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

from .repo import CasePartyRepository
from .wiring import get_client_service


@dataclass(frozen=True)
class SelectedParties:
    client: Any | None
    clients: list[Any] | None


class PartySelectionPolicy:
    def __init__(self, *, repo: CasePartyRepository | None = None, client_service: Any | None = None) -> None:
        self.repo = repo or CasePartyRepository()
        self._client_service = client_service

    @property
    def client_service(self) -> Any:
        if self._client_service is None:
            self._client_service = get_client_service()
        return self._client_service

    def select(
        self,
        *,
        case: Any,
        function_code: str | None,
        client_id: int | None,
        client_ids: list[int] | None,
        mode: str | None,
        legal_rep_cert_code: str,
        power_of_attorney_code: str,
    ) -> SelectedParties:
        if function_code == legal_rep_cert_code:
            if client_id is None:
                raise ValidationException(
                    message=_("法定代表人身份证明书需要指定当事人"),
                    code="INVALID_CLIENT",
                    errors={"client_id": str(_("必须提供 client_id"))},
                )
            client = self._get_our_legal_client(case=case, client_id=client_id)
            return SelectedParties(client=client, clients=None)

        if function_code == power_of_attorney_code:
            if mode == "combined" and client_ids:
                clients = [self._get_our_client(case=case, client_id=cid) for cid in client_ids]
                return SelectedParties(client=None, clients=clients)
            if client_id:
                client = self._get_our_client(case=case, client_id=client_id)
                return SelectedParties(client=client, clients=None)
            return SelectedParties(client=None, clients=None)

        return SelectedParties(client=None, clients=None)

    def _get_our_client(self, *, case: Any, client_id: int) -> Any:
        client_dto = self.client_service.get_client_internal(client_id)
        if not client_dto:
            raise ValidationException(
                message=_("当事人不存在"),
                code="INVALID_CLIENT",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"},
            )

        if not self.repo.is_our_party(case, client_id=client_id):
            raise ValidationException(
                message=_("当事人非我方当事人"),
                code="INVALID_OUR_CLIENT",
                errors={"client_id": f"ID 为 {client_id} 的当事人不是该案件的我方当事人"},
            )

        return client_dto

    def _get_our_legal_client(self, *, case: Any, client_id: int) -> Any:
        client = self._get_our_client(case=case, client_id=client_id)
        is_natural = self.client_service.is_natural_person_internal(client_id)
        if is_natural:
            raise ValidationException(
                message=_("当事人非法人"),
                code="INVALID_LEGAL_CLIENT",
                errors={"client_id": f"ID 为 {client_id} 的当事人不是法人"},
            )
        return client
