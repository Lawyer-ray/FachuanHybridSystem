"""Module for selection strategy protocols."""

from typing import Protocol

from apps.core.dto import AccountCredentialDTO


class IAccountSelectionStrategy(Protocol):
    async def select_account(
        self, site_name: str, exclude_accounts: list[str] | None = None
    ) -> AccountCredentialDTO | None: ...
