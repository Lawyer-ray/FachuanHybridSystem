"""法院 Token 存储服务"""

from __future__ import annotations

import logging

from apps.automation.dtos import CourtTokenDTO

logger = logging.getLogger("apps.automation")


class CourtTokenStoreService:
    """实现 ICourtTokenStoreService，封装 CourtToken 模型的读写操作"""

    def get_latest_valid_token_internal(
        self,
        *,
        site_name: str,
        account: str | None = None,
        token_prefix: str | None = None,
    ) -> CourtTokenDTO | None:
        from django.utils import timezone

        from apps.automation.models import CourtToken

        qs = CourtToken.objects.filter(site_name=site_name, expires_at__gt=timezone.now())
        if account:
            qs = qs.filter(account=account)
        if token_prefix:
            qs = qs.filter(token__startswith=token_prefix)

        obj = qs.order_by("-expires_at").first()
        if obj is None:
            return None

        return CourtTokenDTO(
            site_name=obj.site_name,
            account=obj.account,
            token=obj.token,
            token_type=obj.token_type,
            expires_at=obj.expires_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
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
        from datetime import timedelta

        from django.utils import timezone

        from apps.automation.models import CourtToken

        expires_at = timezone.now() + timedelta(seconds=expires_in)
        CourtToken.objects.update_or_create(
            site_name=site_name,
            account=account,
            defaults={
                "token": token,
                "token_type": token_type,
                "expires_at": expires_at,
            },
        )
        logger.info(f"✅ Token 已保存: {site_name} - {account}")

    async def save_token(self, site_name: str, token: str, expires_in: int) -> None:
        from asgiref.sync import sync_to_async

        await sync_to_async(self.save_token_internal)(
            site_name=site_name,
            account="default",
            token=token,
            expires_in=expires_in,
        )

    async def delete_token(self, site_name: str) -> None:
        from asgiref.sync import sync_to_async

        from apps.automation.models import CourtToken

        await sync_to_async(CourtToken.objects.filter(site_name=site_name).delete)()
        logger.info(f"✅ Token 已删除: {site_name}")
