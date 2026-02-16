"""Business logic services."""

from typing import Any, cast

from django.utils import timezone

from apps.automation.dtos import CourtTokenDTO
from apps.automation.models import CourtToken
from apps.automation.services.scraper.core.token_service import TokenService


class CourtTokenStoreService:
    def get_latest_valid_token_internal(
        self,
        *,
        site_name: str,
        account: str | None = None,
        token_prefix: str | None = None,
    ) -> CourtTokenDTO | None:
        qs = CourtToken.objects.filter(site_name=site_name, expires_at__gt=timezone.now())
        if account:
            qs = qs.filter(account=account)
        token_obj = qs.order_by("-created_at").first()
        if not token_obj:
            return None

        token_value = token_obj.token or ""
        if token_prefix and not token_value.startswith(token_prefix):
            return None

        return CourtTokenDTO(
            site_name=token_obj.site_name,
            account=token_obj.account,
            token=token_obj.token,
            token_type=token_obj.token_type,
            expires_at=token_obj.expires_at,
            created_at=cast(Any, token_obj.created_at),
            updated_at=cast(Any, token_obj.updated_at),
        )

    def save_token_internal(
        self,
        *,
        site_name: str,
        account: str,
        token: str,
        expires_in: int,
        token_type: str = "Bearer",
        credential_id: int | None = None,
    ) -> None:
        TokenService().save_token(
            site_name=site_name,
            account=account,
            token=token,
            expires_in=expires_in,
            token_type=token_type,
            credential_id=credential_id,  # type: ignore
        )
