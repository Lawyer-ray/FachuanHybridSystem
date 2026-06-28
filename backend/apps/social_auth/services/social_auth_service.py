"""社交登录核心业务：根据 SocialProfile 查找或创建用户。"""

from __future__ import annotations

import secrets
import string

from apps.organization.models import Lawyer
from apps.social_auth.models import SocialAccount

from ..providers.base import SocialProfile

_RANDOM_PASSWORD_CHARS = string.ascii_letters + string.digits + "!@#$%^&*"
_RANDOM_PASSWORD_LENGTH = 32


def _generate_password() -> str:
    return "".join(secrets.choice(_RANDOM_PASSWORD_CHARS) for _ in range(_RANDOM_PASSWORD_LENGTH))


def _generate_username(provider_user_id: str) -> str:
    suffix = provider_user_id[-12:] if len(provider_user_id) > 12 else provider_user_id
    return f"soc_{suffix}"


async def _ensure_unique_username(base: str) -> str:  # pragma: no cover
    if not await Lawyer.objects.filter(username=base).aexists():
        return base
    for i in range(1, 1000):
        candidate = f"{base}_{i}"
        if not await Lawyer.objects.filter(username=candidate).aexists():
            return candidate
    raise ValueError("无法生成唯一用户名")


async def link_or_create_user(profile: SocialProfile) -> Lawyer:  # pragma: no cover
    """根据 SocialProfile 查找或创建用户。

    1. 通过 SocialAccount(provider, provider_uid) 查找已有关联
    2. 如果没有关联，创建新用户（自动激活，无需审批）
    3. 创建 SocialAccount 关联记录
    """
    existing = await SocialAccount.objects.select_related("user").filter(
        provider=profile.provider,
        provider_uid=profile.provider_user_id,
    ).afirst()
    if existing:
        if profile.display_name:
            existing.display_name = profile.display_name
        if profile.avatar_url:
            existing.avatar_url = profile.avatar_url
        existing.raw_profile = profile.raw_data
        await existing.asave()
        return existing.user

    username = await _ensure_unique_username(_generate_username(profile.provider_user_id))
    user: Lawyer = await Lawyer.objects.acreate_user(
        username=username,
        password=_generate_password(),
        email=None,
        real_name=profile.display_name or "",
        is_active=True,
        is_superuser=False,
        is_staff=False,
        is_admin=False,
    )

    await SocialAccount.objects.acreate(
        user=user,
        provider=profile.provider,
        provider_uid=profile.provider_user_id,
        display_name=profile.display_name or "",
        avatar_url=profile.avatar_url or "",
        raw_profile=profile.raw_data,
    )

    return user
