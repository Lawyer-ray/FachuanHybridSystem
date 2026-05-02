"""Token 相关 Protocol 接口定义。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from apps.core.dto import AccountCredentialDTO

if TYPE_CHECKING:
    from apps.automation.dtos import CourtTokenDTO
    from apps.core.dto import CourtPleadingSignalsDTO


class IAutoTokenAcquisitionService(Protocol):
    """自动Token获取服务接口"""

    async def acquire_token_if_needed(self, site_name: str, credential_id: int | None = None) -> str: ...


class IAutoLoginService(Protocol):
    """自动登录服务接口"""

    async def login_and_get_token(self, credential: AccountCredentialDTO) -> str: ...


class ITokenService(Protocol):
    """Token 服务接口"""

    async def get_token(self, site_name: str) -> str | None: ...


class ICourtTokenStoreService(Protocol):
    def get_latest_valid_token_internal(
        self,
        *,
        site_name: str,
        account: str | None = None,
        token_prefix: str | None = None,
    ) -> CourtTokenDTO | None: ...

    def save_token_internal(
        self,
        *,
        site_name: str,
        account: str,
        token: str,
        expires_in: int,
        token_type: str = "Bearer",
        credential_id: int | None = None,
    ) -> None: ...

    async def save_token(self, site_name: str, token: str, expires_in: int) -> None: ...

    async def delete_token(self, site_name: str) -> None: ...


class ICourtPleadingSignalsService(Protocol):
    def get_signals_internal(self, case_id: int) -> CourtPleadingSignalsDTO: ...


class IBaoquanTokenService(Protocol):
    async def get_valid_baoquan_token(self, credential_id: int | None = None) -> str: ...
