"""Module for business client."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.protocols import IClientService


def build_client_service() -> IClientService:
    from apps.client.services import ClientServiceAdapter

    return ClientServiceAdapter()  # type: ignore
